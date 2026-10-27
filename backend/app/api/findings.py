import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.applications import load_application
from app.audit import record_event
from app.auth import CurrentUser, require_roles
from app.config import get_settings
from app.db import get_db
from app.models import (
    ComplianceRule,
    Document,
    ExtractedFact,
    Finding,
    RegulatoryChunk,
    RegulatorySource,
    User,
)
from app.models.enums import ApplicationStatus, FindingStatus, RuleStatus, Severity, UserRole
from app.workflow.reviews import latest_reviews
from app.workflow.tasks import send_event

router = APIRouter(tags=["findings"])

DB = Annotated[Session, Depends(get_db)]
Staff = Annotated[User, Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))]
SNIPPET_CHARS = 700


class RuleRef(BaseModel):
    id: uuid.UUID
    code: str
    version: int
    title: str
    internal: bool
    status: RuleStatus
    norm_note: str | None
    source_section: str | None
    source_page: int | None


class EvidenceOut(BaseModel):
    fact_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    field_name: str
    value: Any
    raw_text: str | None
    confidence: float
    low_confidence: bool
    page: int | None


class CitationOut(BaseModel):
    chunk_id: uuid.UUID
    source_title: str
    source_version: str
    section: str | None
    heading: str | None
    page: int | None
    text: str
    verified: bool  # the clause an admin approved, vs. a retrieved candidate


class ReviewOut(BaseModel):
    outcome: str
    comment: str | None
    reviewer: str
    created_at: datetime


class FindingOut(BaseModel):
    id: uuid.UUID
    status: FindingStatus
    severity: Severity
    reason: str
    details: dict[str, Any]
    provisional: bool
    created_at: datetime
    rule: RuleRef
    evidence: list[EvidenceOut]
    citations: list[CitationOut]
    review: ReviewOut | None


STATUS_ORDER = {
    FindingStatus.FAIL: 0,
    FindingStatus.NEEDS_REVIEW: 1,
    FindingStatus.UNABLE_TO_DETERMINE: 2,
    FindingStatus.PASS: 3,
    FindingStatus.NOT_APPLICABLE: 4,
}
SEVERITY_ORDER = {s: i for i, s in enumerate(reversed(list(Severity)))}


@router.get("/applications/{application_id}/findings", response_model=list[FindingOut])
def list_findings(application_id: uuid.UUID, user: CurrentUser, db: DB) -> list[FindingOut]:
    application = load_application(db, application_id, user)
    findings = list(
        db.scalars(
            select(Finding).where(Finding.application_id == application.id, Finding.is_current)
        )
    )
    rules = {r.id: r for r in db.scalars(select(ComplianceRule))}
    fact_ids = {fid for f in findings for fid in f.evidence_fact_ids}
    chunk_ids = {cid for f in findings for cid in f.source_chunk_ids}
    facts = {
        fact.id: (fact, filename)
        for fact, filename in db.execute(
            select(ExtractedFact, Document.filename)
            .join(Document, Document.id == ExtractedFact.document_id)
            .where(ExtractedFact.id.in_(fact_ids))
        )
    }
    chunks = {
        chunk.id: (chunk, source)
        for chunk, source in db.execute(
            select(RegulatoryChunk, RegulatorySource)
            .join(RegulatorySource, RegulatorySource.id == RegulatoryChunk.source_id)
            .where(RegulatoryChunk.id.in_(chunk_ids))
        )
    }
    threshold = get_settings().low_confidence_threshold
    reviews = latest_reviews(db, [f.id for f in findings])
    reviewers = {u.id: u.full_name for u in db.scalars(select(User))}

    out = []
    for f in findings:
        rule = rules[f.rule_id]
        evidence = [
            EvidenceOut(
                fact_id=fact.id,
                document_id=fact.document_id,
                filename=filename,
                field_name=fact.field_name,
                value=fact.value,
                raw_text=fact.raw_text,
                confidence=fact.confidence,
                low_confidence=fact.confidence < threshold,
                page=fact.page,
            )
            for fid in f.evidence_fact_ids
            if fid in facts
            for fact, filename in [facts[fid]]
        ]
        citations = [
            CitationOut(
                chunk_id=chunk.id,
                source_title=source.title,
                source_version=source.version,
                section=chunk.section,
                heading=chunk.heading,
                page=chunk.page,
                text=chunk.text[:SNIPPET_CHARS],
                verified=rule.source_id == source.id
                and (
                    chunk.section == rule.source_section
                    if rule.source_section
                    else chunk.page == rule.source_page
                ),
            )
            for cid in f.source_chunk_ids
            if cid in chunks
            for chunk, source in [chunks[cid]]
        ]
        out.append(
            FindingOut(
                id=f.id,
                status=f.status,
                severity=f.severity,
                reason=f.reason,
                details=f.details,
                provisional=f.details.get("provisional", False),
                created_at=f.created_at,
                rule=RuleRef(
                    id=rule.id,
                    code=rule.rule_code,
                    version=rule.version,
                    title=rule.title,
                    internal=rule.internal,
                    status=rule.status,
                    norm_note=rule.norm_note,
                    source_section=rule.source_section,
                    source_page=rule.source_page,
                ),
                evidence=evidence,
                citations=citations,
                review=ReviewOut(
                    outcome=r.outcome.value,
                    comment=r.comment,
                    reviewer=reviewers.get(r.reviewer_id, "unknown"),
                    created_at=r.created_at,
                )
                if (r := reviews.get(f.id))
                else None,
            )
        )
    out.sort(key=lambda x: (STATUS_ORDER[x.status], SEVERITY_ORDER[x.severity], x.rule.code))
    return out


@router.post("/applications/{application_id}/evaluate", status_code=202)
def reevaluate(application_id: uuid.UUID, user: Staff, db: DB) -> dict[str, str]:
    application = load_application(db, application_id, user)
    if application.status == ApplicationStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Drafts are evaluated after submission")
    record_event(db, "evaluation_requested", application_id=application.id, actor_id=user.id)
    db.commit()
    send_event(application.id, {"type": "reevaluate", "actor_id": str(user.id)})
    return {"status": "queued"}
