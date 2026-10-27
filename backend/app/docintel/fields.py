"""Tier-1 field extraction: labelled-field regexes per document type, with provenance.

Each pattern has a named group `v` holding the value. The words under that group give the
evidence bbox and the confidence (mean OCR word confidence; ~1.0 for native PDF text).
A value that matches but doesn't parse (e.g. an OCR-garbled date) is kept with low confidence
so it gets routed to a human instead of silently dropped.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.docintel.dates import DATE_PATTERN, parse_date
from app.docintel.text import BBox, DocumentText, Line, union_bbox
from app.models.enums import DocumentType

UNPARSEABLE_CONFIDENCE_CAP = 0.4
# Strict date formats first, then a loose date-shaped fallback (e.g. OCR's "25°07 /2021")
# that fails to parse and is therefore kept with capped confidence for human review.
D = rf"(?:{DATE_PATTERN}|\d{{1,2}}\W{{1,3}}\d{{1,2}}\s?\W{{1,3}}\d{{4}})"
NAME = r"(?:(?:Dr|Mr|Ms|Mrs|Prof)\.\s?)?[A-Z][A-Za-z.]*(?:\s[A-Z][A-Za-z.]*)*"


@dataclass
class ExtractedField:
    name: str
    value: Any
    raw: str
    confidence: float
    page: int | None
    bbox: BBox | None


def _text(raw: str) -> str | None:
    return raw.strip(" .,:;-") or None


def _proper(raw: str) -> str | None:
    """Title-case ALL-CAPS headings ("ANNA UNIVERSITY" -> "Anna University")."""
    text = _text(raw)
    if not text or not text.isupper():
        return text
    small = {"of", "and", "the"}
    words = [w.lower() if w.lower() in small else w.capitalize() for w in text.split()]
    return " ".join(words)


def _date(raw: str) -> str | None:
    parsed = parse_date(raw)
    return parsed.isoformat() if parsed else None


def _number(raw: str) -> float | int | None:
    try:
        n = float(raw.replace(",", ""))
    except ValueError:
        return None
    return int(n) if n.is_integer() else n


@dataclass(frozen=True)
class FieldSpec:
    name: str
    pattern: str
    parse: Callable[[str], Any] = _text
    flags: int = re.IGNORECASE

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.pattern, self.flags)


CERT_NO = r"(?P<v>[A-Z0-9][A-Z0-9/-]{3,})"

SPECS: dict[DocumentType, list[FieldSpec]] = {
    DocumentType.FIRE_NOC: [
        FieldSpec(
            "certificate_number", rf"(?:NOC|Certificate)\s*(?:No|Number)\.?\s*[:-]?\s*{CERT_NO}"
        ),
        FieldSpec(
            "issued_on", rf"(?:Date of Issue|Issued on|Issue Date)\s*[:-]?\s*(?P<v>{D})", _date
        ),
        FieldSpec(
            "valid_until",
            r"(?:Valid\s*(?:up\s*to|till|until)|Validity|Expiry Date|Expires on)"
            rf"\s*[:-]?\s*(?P<v>{D})",
            _date,
        ),
        FieldSpec("issuing_authority", r"(?:Issued by|Issuing Authority)\s*[:-]?\s*(?P<v>.+)$"),
        FieldSpec(
            "institution_name",
            r"Name of (?:the )?(?:Institution|Premises|Occupant)\s*[:-]\s*(?P<v>.+)$",
        ),
    ],
    DocumentType.BUILDING_CERTIFICATE: [
        FieldSpec("certificate_number", rf"Certificate\s*(?:No|Number)\.?\s*[:-]?\s*{CERT_NO}"),
        FieldSpec(
            "issued_on", rf"(?:Date of Issue|Issued on|Issue Date)\s*[:-]?\s*(?P<v>{D})", _date
        ),
        FieldSpec(
            "built_up_area_sqm",
            r"Built[- ]?up Area\s*[:-]?\s*(?P<v>[\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|m2|square met)",
            _number,
        ),
        FieldSpec(
            "institution_name",
            r"Name of (?:the )?(?:Institution|Owner|Applicant)\s*[:-]\s*(?P<v>.+)$",
        ),
    ],
    DocumentType.LAND_DOCUMENT: [
        FieldSpec("survey_number", r"Survey\s*(?:No|Number)\.?\s*[:-]?\s*(?P<v>[\w/-]+)"),
        FieldSpec("area_acres", r"Area\s*[:-]?\s*(?P<v>\d+(?:\.\d+)?)\s*acres?", _number),
        FieldSpec(
            "owner_name",
            r"(?:Owner|Lessee|Purchaser|In favour of)\s*[:-]\s*(?P<v>.+)$",
        ),
        FieldSpec(
            "document_date",
            rf"(?:Date of Registration|Registered on|Dated)\s*[:-]?\s*(?P<v>{D})",
            _date,
        ),
    ],
    DocumentType.QUALIFICATION_CERTIFICATE: [
        FieldSpec(
            "holder_name",
            # Tolerates OCR damage: "certily that", "cartity hat", "Mr, T. Suresh)".
            r"(?i:c\w+\s+t?hat)\s+(?P<v>(?:(?:Dr|Mr|Ms|Mrs|Prof)[.,]\s?)?\S+(?:\s\S+){0,3}?)"
            r"(?=\s+(?i:has|was|is)\b|\s*$)",
            flags=0,
        ),
        FieldSpec("degree", r"degre\w*\s+o\w\s+(?P<v>(?:doctor|master|bachelor)\s+of\s+[a-z]+)"),
        FieldSpec(
            "university",
            r"(?P<v>(?:[a-z.]+\s){0,3}university(?:\s+of\s+[a-z]+)?)",
            _proper,
        ),
        FieldSpec("awarded_on", rf"(?:\bon|\bdated?)\s*[:-]?\s*(?P<v>{D})", _date),
    ],
    DocumentType.APPOINTMENT_LETTER: [
        FieldSpec("employee_name", rf"(?:Dear|To|Name)\s*[:,]?\s+(?P<v>{NAME})", flags=0),
        FieldSpec(
            "designation",
            r"(?:post of|designation\s*[:-])\s*(?P<v>(?:assistant |associate )?professor)",
        ),
        FieldSpec(
            "date_of_joining",
            rf"(?:date of joining|joined on|join duty on)\s*[:-]?\s*(?P<v>{D})",
            _date,
        ),
    ],
    DocumentType.LAB_INVENTORY: [
        FieldSpec("lab_name", r"(?:laboratory|lab)\s*(?:name)?\s*[:-]\s*(?P<v>.+)$"),
        FieldSpec(
            "total_items", r"total\s*(?:items|equipment|quantity)\s*[:-]?\s*(?P<v>\d+)", _number
        ),
    ],
}

FACULTY_ROW = re.compile(
    r"^(?P<sno>\d{1,3})\.?\s+(?P<name>.+?)\s+"
    r"(?P<designation>(?i:assistant professor|associate professor|professor))\s+"
    r"(?P<qualification>\S+)"
)


def _from_match(name: str, line: Line, m: re.Match[str], parse: Callable) -> ExtractedField:
    words = line.words_in_span(*m.span("v"))
    raw = m["v"].strip()
    confidence = sum(w.confidence for w in words) / len(words) if words else 0.0
    value = parse(raw)
    if value is None:
        value, confidence = raw, min(confidence, UNPARSEABLE_CONFIDENCE_CAP)
    return ExtractedField(name, value, raw, round(confidence, 3), line.page, union_bbox(words))


def _faculty_rows(text: DocumentText) -> list[ExtractedField]:
    members: list[ExtractedField] = []
    for line in text.lines:
        if not (m := FACULTY_ROW.match(line.text)):
            continue
        words = line.words_in_span(m.start("name"), m.end("qualification"))
        member = {
            "name": m["name"].strip(),
            "designation": m["designation"].title(),
            "qualification": m["qualification"],
        }
        confidence = sum(w.confidence for w in words) / len(words)
        members.append(
            ExtractedField(
                "faculty_member",
                member,
                line.text,
                round(confidence, 3),
                line.page,
                union_bbox(words),
            )
        )
    if not members:
        return []
    count = ExtractedField(
        "faculty_count",
        len(members),
        f"{len(members)} rows",
        min(f.confidence for f in members),
        members[0].page,
        None,
    )
    return [count, *members]


def extract_fields(doc_type: DocumentType, text: DocumentText) -> list[ExtractedField]:
    if doc_type == DocumentType.FACULTY_LIST:
        return _faculty_rows(text)
    fields: list[ExtractedField] = []
    for spec in SPECS.get(doc_type, []):
        pattern = spec.compiled()
        for line in text.lines:
            if m := pattern.search(line.text):
                fields.append(_from_match(spec.name, line, m, spec.parse))
                break  # first occurrence wins; the most prominent mention is usually first
    return fields
