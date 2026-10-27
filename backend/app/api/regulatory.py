import hashlib
import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.applications import safe_filename, sniff_mime
from app.audit import record_event
from app.auth import require_roles
from app.config import get_settings
from app.db import get_db
from app.models import ComplianceRule, RegulatoryChunk, RegulatorySource, User
from app.models.enums import ProcessingStatus, RuleStatus, Severity, UserRole
from app.rag.search import hybrid_search
from app.rag.tasks import ingest_source
from app.storage import get_s3

router = APIRouter(tags=["regulatory"])

DB = Annotated[Session, Depends(get_db)]
Staff = Annotated[User, Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))]
Admin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
MAX_SOURCE_BYTES = 100 * 1024 * 1024


class SourceOut(BaseModel):
    id: uuid.UUID
    title: str
    source_type: str
    version: str
    published_on: date | None
    effective_from: date | None
    effective_to: date | None
    source_url: str | None
    sha256: str
    ingest_status: ProcessingStatus
    ingest_error: str | None
    chunk_count: int
    created_at: datetime


class HitOut(BaseModel):
    chunk_id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    source_version: str
    section: str | None
    heading: str | None
    page: int | None
    text: str
    score: float
    matched_by: list[str]


class RuleOut(BaseModel):
    id: uuid.UUID
    rule_code: str
    version: int
    title: str
    evaluator: str
    severity: Severity
    internal: bool
    status: RuleStatus
    params: dict
    citation_query: str | None
    norm_note: str | None
    source_id: uuid.UUID | None
    source_section: str | None
    source_page: int | None


class VerifyRule(BaseModel):
    chunk_id: uuid.UUID  # the clause the admin read and confirmed


def to_hits(hits) -> list[HitOut]:
    return [
        HitOut(
            chunk_id=h.chunk.id,
            source_id=h.source.id,
            source_title=h.source.title,
            source_version=h.source.version,
            section=h.chunk.section,
            heading=h.chunk.heading,
            page=h.chunk.page,
            text=h.chunk.text,
            score=round(h.score, 4),
            matched_by=h.matched_by,
        )
        for h in hits
    ]


@router.get("/regulatory/sources", response_model=list[SourceOut])
def list_sources(_: Staff, db: DB) -> list[RegulatorySource]:
    return list(db.scalars(select(RegulatorySource).order_by(RegulatorySource.created_at.desc())))


@router.post("/regulatory/sources", response_model=SourceOut, status_code=201)
def upload_source(
    user: Admin,
    db: DB,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=3)],
    version: Annotated[str, Form(min_length=1)],
    source_type: Annotated[str, Form()] = "handbook",
    effective_from: Annotated[date | None, Form()] = None,
    effective_to: Annotated[date | None, Form()] = None,
    source_url: Annotated[str | None, Form()] = None,
) -> RegulatorySource:
    data = file.file.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 100 MB limit")
    if sniff_mime(data[:16]) != "application/pdf":
        raise HTTPException(status_code=415, detail="Regulatory sources must be PDFs")
    if db.scalar(
        select(RegulatorySource).where(
            RegulatorySource.title == title, RegulatorySource.version == version
        )
    ):
        raise HTTPException(status_code=409, detail="A source with this title and version exists")

    source_id = uuid.uuid4()
    key = f"regulatory/{source_id}/{safe_filename(file.filename)}"
    get_s3().put_object(
        Bucket=get_settings().s3_bucket, Key=key, Body=data, ContentType="application/pdf"
    )
    source = RegulatorySource(
        id=source_id,
        title=title,
        version=version,
        source_type=source_type,
        effective_from=effective_from,
        effective_to=effective_to,
        source_url=source_url,
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=key,
    )
    db.add(source)
    record_event(
        db,
        "regulatory_source_uploaded",
        actor_id=user.id,
        source_id=str(source_id),
        title=title,
        version=version,
    )
    db.commit()
    ingest_source.delay(str(source_id))
    db.refresh(source)
    return source


@router.post("/regulatory/sources/{source_id}/reingest", status_code=202)
def reingest_source(source_id: uuid.UUID, _: Admin, db: DB) -> dict[str, str]:
    if db.get(RegulatorySource, source_id) is None:
        raise HTTPException(status_code=404, detail="Source not found")
    ingest_source.delay(str(source_id))
    return {"status": "queued"}


@router.get("/regulatory/search", response_model=list[HitOut])
def search(_: Staff, db: DB, q: str, k: int = 5, on_date: date | None = None) -> list[HitOut]:
    return to_hits(hybrid_search(db, q, k=min(k, 20), on_date=on_date))


@router.get("/rules", response_model=list[RuleOut])
def list_rules(_: Staff, db: DB) -> list[ComplianceRule]:
    return list(
        db.scalars(
            select(ComplianceRule).order_by(ComplianceRule.rule_code, ComplianceRule.version)
        )
    )


@router.get("/rules/{rule_id}/candidates", response_model=list[HitOut])
def rule_candidates(rule_id: uuid.UUID, _: Staff, db: DB) -> list[HitOut]:
    """Handbook passages most likely to contain this rule's norm, for a reviewer to confirm."""
    rule = db.get(ComplianceRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if not rule.citation_query:
        return []
    return to_hits(hybrid_search(db, rule.citation_query, k=6))


@router.post("/rules/{rule_id}/verify", response_model=RuleOut)
def verify_rule(rule_id: uuid.UUID, body: VerifyRule, user: Admin, db: DB) -> ComplianceRule:
    """Record that an admin read the clause and confirmed the rule's norm matches it."""
    rule = db.get(ComplianceRule, rule_id)
    chunk = db.get(RegulatoryChunk, body.chunk_id)
    if rule is None or chunk is None:
        raise HTTPException(status_code=404, detail="Rule or clause not found")
    if rule.internal:
        raise HTTPException(status_code=409, detail="Internal rules have no regulatory citation")
    rule.source_id, rule.source_section, rule.source_page = (
        chunk.source_id,
        chunk.section,
        chunk.page,
    )
    rule.status = RuleStatus.APPROVED
    rule.verified_by = user.id
    record_event(
        db,
        "rule_verified",
        actor_id=user.id,
        rule_code=rule.rule_code,
        version=rule.version,
        source_id=str(chunk.source_id),
        section=chunk.section,
        page=chunk.page,
    )
    db.commit()
    return rule
