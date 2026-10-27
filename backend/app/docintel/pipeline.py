from dataclasses import dataclass

from app.docintel.classify import classify
from app.docintel.fields import ExtractedField, extract_fields
from app.docintel.text import DocumentText, extract_text
from app.models.enums import DocumentType

EXTRACTOR_NAME = "rules-v1"


@dataclass
class ProcessingResult:
    text: DocumentText
    detected_type: DocumentType
    detection_confidence: float
    fields: list[ExtractedField]

    @property
    def pages(self) -> list[dict]:
        return [
            {"number": p.number, "width": p.width, "height": p.height, "ocr": p.ocr}
            for p in self.text.pages
        ]


def process(data: bytes, mime_type: str, declared_type: DocumentType) -> ProcessingResult:
    """Extract text, classify, and pull fields.

    Fields are extracted for the type the institution declared at upload; the classifier's
    opinion is stored alongside so a mismatch can be flagged rather than silently "corrected".
    """
    text = extract_text(data, mime_type)
    detected, confidence = classify(text)
    fields = extract_fields(declared_type, text)
    return ProcessingResult(text, detected, confidence, fields)
