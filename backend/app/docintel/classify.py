"""Tier-1 document classification: weighted keyword scoring on the first page.

Good enough for well-titled documents; an LLM/ML classifier can replace this behind the same
signature once we have labelled real documents to evaluate against.
"""

import re

from app.docintel.text import DocumentText
from app.models.enums import DocumentType

KEYWORDS: dict[DocumentType, list[tuple[str, float]]] = {
    DocumentType.FIRE_NOC: [
        (r"fire", 2),
        (r"no objection certificate|\bnoc\b", 3),
        (r"fire (and|&) rescue|fire service", 3),
    ],
    DocumentType.BUILDING_CERTIFICATE: [
        (r"completion certificate", 4),
        (r"occupancy", 2),
        (r"built[- ]up area", 2),
        (r"building", 1),
    ],
    DocumentType.LAND_DOCUMENT: [
        (r"sale deed|lease deed|land", 3),
        (r"survey (no|number)", 3),
        (r"acres?\b|hectares?\b", 1),
    ],
    DocumentType.FACULTY_LIST: [
        (r"faculty (list|details|members)", 4),
        (r"designation", 1),
        (r"s\.? ?no", 1),
    ],
    DocumentType.QUALIFICATION_CERTIFICATE: [
        (r"degree of|conferred|awarded", 3),
        (r"university", 2),
        (r"doctor of philosophy|master of|bachelor of", 3),
    ],
    DocumentType.APPOINTMENT_LETTER: [
        (r"appointment|appointed", 4),
        (r"date of joining|join(ing)? duty", 2),
        (r"pay (scale|level)", 1),
    ],
    DocumentType.LAB_INVENTORY: [
        (r"inventory|equipment", 3),
        (r"laborator(y|ies)|\blab\b", 2),
        (r"quantity|qty", 1),
    ],
}


def classify(text: DocumentText) -> tuple[DocumentType, float]:
    """Return the best type and a confidence: its share of the top-two scores."""
    if not text.pages:
        return DocumentType.UNCLASSIFIED, 0.0
    first_page = text.page_text(1).lower()
    scores = {
        doc_type: sum(weight for pattern, weight in rules if re.search(pattern, first_page))
        for doc_type, rules in KEYWORDS.items()
    }
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (best, top), (_, second) = ranked[0], ranked[1]
    if top == 0:
        return DocumentType.UNCLASSIFIED, 0.0
    return best, round(top / (top + second), 2)
