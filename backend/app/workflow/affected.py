"""Which rules can a document change affect? The core of incremental re-validation.

A rule is re-checked when (a) it has no declared evidence (it looks at the document set as a
whole, e.g. completeness), (b) a changed document is of a type its evidence comes from, or
(c) one of its current findings cites a fact from a changed document.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, ComplianceRule, Document, ExtractedFact, Finding


def document_snapshot(db: Session, application: Application) -> dict[str, str]:
    """{document id: doc type} for the current documents; compared between evaluations."""
    return {
        str(d.id): d.doc_type.value
        for d in db.scalars(
            select(Document).where(Document.application_id == application.id, Document.is_current)
        )
    }


def changed_documents(previous: dict[str, str], current: dict[str, str]) -> dict[str, str]:
    """Added, replaced (new id) or removed documents, with their types."""
    changed = {i: t for i, t in current.items() if i not in previous}
    changed |= {i: t for i, t in previous.items() if i not in current}
    return changed


def affected_rule_codes(
    db: Session, application: Application, rules: list[ComplianceRule], changed: dict[str, str]
) -> set[str]:
    changed_types = set(changed.values())
    affected = {
        rule.rule_code
        for rule in rules
        if not (types := {e.split(".")[0] for e in rule.required_evidence}) or types & changed_types
    }

    # Rules whose current finding cites a fact from a changed (e.g. replaced) document.
    current = db.execute(
        select(Finding.evidence_fact_ids, ComplianceRule.rule_code)
        .join(ComplianceRule, ComplianceRule.id == Finding.rule_id)
        .where(Finding.application_id == application.id, Finding.is_current)
    ).all()
    fact_ids = {fid for ids, _ in current for fid in ids}
    fact_doc = dict(
        db.execute(
            select(ExtractedFact.id, ExtractedFact.document_id).where(
                ExtractedFact.id.in_(fact_ids)
            )
        ).all()
    )
    for ids, code in current:
        if any(str(fact_doc.get(fid)) in changed for fid in ids):
            affected.add(code)
    return affected
