from dataclasses import dataclass, field
from datetime import date

from app.checklists import APPLICATION_TYPES, ChecklistItem
from app.models import Application, Document, ExtractedFact
from app.models.enums import DocumentType, FindingStatus


@dataclass
class EvalContext:
    """Everything an evaluator may look at. Evaluators are pure functions of this context."""

    application: Application
    documents: list[Document]
    facts: list[ExtractedFact]
    today: date
    low_confidence_threshold: float

    @property
    def checklist(self) -> tuple[ChecklistItem, ...]:
        return APPLICATION_TYPES[self.application.application_type].checklist

    def documents_of(self, doc_type: DocumentType) -> list[Document]:
        return [d for d in self.documents if d.doc_type == doc_type]

    def facts_named(self, name: str, doc_type: DocumentType | None = None) -> list[ExtractedFact]:
        doc_types = {d.id: d.doc_type for d in self.documents}
        return [
            f
            for f in self.facts
            if f.field_name == name and (doc_type is None or doc_types[f.document_id] == doc_type)
        ]

    def fact(self, name: str, doc_type: DocumentType | None = None) -> ExtractedFact | None:
        found = self.facts_named(name, doc_type)
        return found[0] if found else None

    def is_low(self, fact: ExtractedFact) -> bool:
        return fact.confidence < self.low_confidence_threshold


@dataclass
class Result:
    status: FindingStatus
    reason: str
    evidence: list[ExtractedFact] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    # Facts the conclusion actually rests on (default: all evidence). Only these can downgrade
    # the result to needs_review when they're low-confidence; e.g. three faculty with no
    # certificate is a definite failure even if a fourth name was read badly.
    decisive: list[ExtractedFact] | None = None
