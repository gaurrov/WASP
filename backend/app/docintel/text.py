"""Turn a PDF or image into lines of positioned words, using native text or OCR per page.

All coordinates are PDF points in the page's own space (origin top-left), so the frontend can
overlay evidence boxes on a rendered page regardless of where the text came from.
"""

from dataclasses import dataclass, field

import pymupdf
import pytesseract
from PIL import Image

NATIVE_CONFIDENCE = 0.99  # text embedded in the PDF is exact; only extraction rules can be wrong
MIN_NATIVE_CHARS = 20  # fewer characters than this on a page means it's a scan: OCR it
OCR_DPI = 300

BBox = tuple[float, float, float, float]

FILETYPES = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}


@dataclass
class Word:
    text: str
    bbox: BBox
    confidence: float  # 0..1


@dataclass
class Line:
    page: int  # 1-based
    words: list[Word]
    text: str = field(init=False)
    _starts: list[int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._starts, pos = [], 0
        for w in self.words:
            self._starts.append(pos)
            pos += len(w.text) + 1
        self.text = " ".join(w.text for w in self.words)

    def words_in_span(self, start: int, end: int) -> list[Word]:
        """Words overlapping the character span [start, end) of self.text."""
        return [
            w
            for w, s in zip(self.words, self._starts, strict=True)
            if s < end and s + len(w.text) > start
        ]


@dataclass
class PageText:
    number: int
    width: float
    height: float
    ocr: bool
    lines: list[Line]


@dataclass
class DocumentText:
    pages: list[PageText]

    @property
    def lines(self) -> list[Line]:
        return [line for page in self.pages for line in page.lines]

    @property
    def ocr_used(self) -> bool:
        return any(p.ocr for p in self.pages)

    def page_text(self, number: int) -> str:
        return "\n".join(line.text for line in self.pages[number - 1].lines)


def union_bbox(words: list[Word]) -> BBox | None:
    if not words:
        return None
    return (
        min(w.bbox[0] for w in words),
        min(w.bbox[1] for w in words),
        max(w.bbox[2] for w in words),
        max(w.bbox[3] for w in words),
    )


def _visual_lines(words: list[Word], page: int) -> list[Line]:
    """Group words into rows by vertical overlap, then order each row left to right.

    PDF text blocks and OCR line numbers both split table rows into cells; reading order by
    position keeps "Label: value" pairs and table rows on one line.
    """
    rows: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.bbox[1] + w.bbox[3]) / 2):
        center = (w.bbox[1] + w.bbox[3]) / 2
        if rows:
            last = rows[-1]
            top, bottom = min(x.bbox[1] for x in last), max(x.bbox[3] for x in last)
            if top <= center <= bottom:
                last.append(w)
                continue
        rows.append([w])
    return [Line(page, sorted(row, key=lambda w: w.bbox[0])) for row in rows]


def _native_lines(page: pymupdf.Page, number: int) -> list[Line]:
    words = [
        Word(text, (x0, y0, x1, y1), NATIVE_CONFIDENCE)
        for x0, y0, x1, y1, text, *_ in page.get_text("words")
    ]
    return _visual_lines(words, number)


def _ocr_lines(page: pymupdf.Page, number: int) -> list[Line]:
    pix = page.get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csGRAY)
    image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, config="--psm 3")
    scale_x, scale_y = page.rect.width / pix.width, page.rect.height / pix.height

    words: list[Word] = []
    for i, text in enumerate(data["text"]):
        conf = float(data["conf"][i])
        if not text.strip() or conf < 0:  # conf -1 marks layout boxes, not words
            continue
        left, top = data["left"][i] * scale_x, data["top"][i] * scale_y
        bbox = (
            left,
            top,
            left + data["width"][i] * scale_x,
            top + data["height"][i] * scale_y,
        )
        words.append(Word(text.strip(), bbox, conf / 100))
    return _visual_lines(words, number)


def extract_text(data: bytes, mime_type: str) -> DocumentText:
    pages: list[PageText] = []
    with pymupdf.open(stream=data, filetype=FILETYPES[mime_type]) as doc:
        for index, page in enumerate(doc):
            number = index + 1
            native = page.get_text("text").strip()
            use_ocr = len(native) < MIN_NATIVE_CHARS
            lines = _ocr_lines(page, number) if use_ocr else _native_lines(page, number)
            pages.append(PageText(number, page.rect.width, page.rect.height, use_ocr, lines))
    return DocumentText(pages)
