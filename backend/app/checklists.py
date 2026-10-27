"""Required-document checklists per application type.

ILLUSTRATIVE ONLY: these are placeholders for the demo. Replace them with the checklist from the
applicable AICTE Approval Process Handbook (and cite the clause) when rules land in M3.
"""

from dataclasses import dataclass

from app.models.enums import DocumentType


@dataclass(frozen=True)
class ChecklistItem:
    doc_type: DocumentType
    label: str
    required: bool = True
    multiple: bool = False  # e.g. one certificate per faculty member


@dataclass(frozen=True)
class ApplicationType:
    code: str
    label: str
    checklist: tuple[ChecklistItem, ...]


APPLICATION_TYPES: dict[str, ApplicationType] = {
    t.code: t
    for t in [
        ApplicationType(
            code="extension_of_approval",
            label="Extension of Approval",
            checklist=(
                ChecklistItem(DocumentType.FACULTY_LIST, "Faculty list (declaration)"),
                ChecklistItem(
                    DocumentType.QUALIFICATION_CERTIFICATE,
                    "Faculty qualification certificates",
                    multiple=True,
                ),
                ChecklistItem(
                    DocumentType.APPOINTMENT_LETTER, "Faculty appointment letters", multiple=True
                ),
                ChecklistItem(DocumentType.FIRE_NOC, "Fire safety NOC"),
                ChecklistItem(DocumentType.BUILDING_CERTIFICATE, "Building completion certificate"),
                ChecklistItem(DocumentType.LAND_DOCUMENT, "Land ownership / lease document"),
                ChecklistItem(DocumentType.LAB_INVENTORY, "Laboratory equipment inventory"),
                ChecklistItem(
                    DocumentType.OTHER, "Other supporting documents", required=False, multiple=True
                ),
            ),
        ),
    ]
}
