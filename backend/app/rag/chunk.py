"""Split a regulatory PDF into clause-level chunks that keep their section number and page.

Regulations are cited by clause, so chunks follow the document's own numbering ("2.3.1",
"Chapter III", "Appendix 6") instead of fixed-size windows. Long clauses are split with overlap.
"""

import re
from dataclasses import dataclass

from app.docintel.text import DocumentText

MAX_CHARS = 1500
OVERLAP_CHARS = 200

# Dotted clause numbers or named divisions. Bare numbers ("20 Assistant Professor") are too
# often table rows to treat as headings.
HEADING = re.compile(
    r"^(?P<num>(?:chapter|appendix|annexure|annex|schedule)\s+[ivxlc\d]+[a-z]?"
    r"|\d{1,2}(?:\.\d{1,2}){1,3})[.)]?\s+(?P<title>\S.{1,150})$",
    re.IGNORECASE,
)


@dataclass
class Chunk:
    section: str | None
    heading: str | None
    text: str
    page: int


def _split_long(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    parts, start = [], 0
    while start < len(text):
        end = min(start + MAX_CHARS, len(text))
        if end < len(text):  # break on a sentence or line boundary when possible
            cut = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
            if cut > start + MAX_CHARS // 2:
                end = cut + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - OVERLAP_CHARS, start + 1)
    return parts


def chunk_document(text: DocumentText) -> list[Chunk]:
    chunks: list[Chunk] = []
    section: str | None = None
    heading: str | None = None
    page = 1
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            for part in _split_long(body):
                chunks.append(Chunk(section, heading, part, page))
        buffer.clear()

    for line in text.lines:
        if m := HEADING.match(line.text.strip()):
            flush()
            section, heading, page = m["num"].title(), m["title"].strip(), line.page
            buffer.append(line.text)
        else:
            if not buffer:
                page = line.page
            buffer.append(line.text)
    flush()
    return chunks
