import uuid
from datetime import datetime
from typing import Annotated, Any

import pymupdf
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.applications import load_application
from app.audit import record_event
from app.auth import CurrentUser, require_roles
from app.config import get_settings
from app.db import get_db
from app.docintel.tasks import enqueue_processing
from app.docintel.text import FILETYPES
from app.models import Document, ExtractedFact, User
from app.models.enums import DocumentType, ProcessingStatus, UserRole
from app.storage import get_s3

router = APIRouter(prefix="/documents", tags=["documents"])

DB = Annotated[Session, Depends(get_db)]
RENDER_DPI = 110


class FactOut(BaseModel):
    id: uuid.UUID
    field_name: str
    value: Any
    raw_text: str | None
    confidence: float
    low_confidence: bool
    page: int | None
    bbox: list[float] | None
    extractor: str


class PageOut(BaseModel):
    number: int
    width: float
    height: float
    ocr: bool


class DocumentDetail(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    doc_type: DocumentType
    filename: str
    mime_type: str
    version: int
    processing_status: ProcessingStatus
    processing_error: str | None
    processed_at: datetime | None
    detected_doc_type: DocumentType | None
    detection_confidence: float | None
    type_mismatch: bool
    ocr_used: bool | None
    pages: list[PageOut]
    facts: list[FactOut]


def load_document(db: Session, document_id: uuid.UUID, user: User) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    load_application(db, document.application_id, user)  # enforces tenant/role visibility
    return document


def fetch_bytes(document: Document) -> bytes:
    obj = get_s3().get_object(Bucket=get_settings().s3_bucket, Key=document.storage_key)
    return obj["Body"].read()


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, user: CurrentUser, db: DB) -> DocumentDetail:
    document = load_document(db, document_id, user)
    threshold = get_settings().low_confidence_threshold
    facts = db.scalars(
        select(ExtractedFact)
        .where(ExtractedFact.document_id == document.id)
        .order_by(ExtractedFact.page, ExtractedFact.created_at)
    )
    detected = document.detected_doc_type
    return DocumentDetail(
        id=document.id,
        application_id=document.application_id,
        doc_type=document.doc_type,
        filename=document.filename,
        mime_type=document.mime_type,
        version=document.version,
        processing_status=document.processing_status,
        processing_error=document.processing_error,
        processed_at=document.processed_at,
        detected_doc_type=detected,
        detection_confidence=document.detection_confidence,
        # Only call it a mismatch when the classifier is reasonably sure.
        type_mismatch=bool(
            detected
            and detected not in (document.doc_type, DocumentType.UNCLASSIFIED)
            and (document.detection_confidence or 0) >= 0.6
        ),
        ocr_used=document.ocr_used,
        pages=[PageOut(**p) for p in document.pages or []],
        facts=[
            FactOut(
                id=f.id,
                field_name=f.field_name,
                value=f.value,
                raw_text=f.raw_text,
                confidence=f.confidence,
                low_confidence=f.confidence < threshold,
                page=f.page,
                bbox=f.bbox,
                extractor=f.extractor,
            )
            for f in facts
        ],
    )


@router.get("/{document_id}/content")
def download_document(document_id: uuid.UUID, user: CurrentUser, db: DB) -> StreamingResponse:
    document = load_document(db, document_id, user)
    obj = get_s3().get_object(Bucket=get_settings().s3_bucket, Key=document.storage_key)
    return StreamingResponse(
        obj["Body"].iter_chunks(),
        media_type=document.mime_type,
        headers={"Content-Disposition": f'inline; filename="{document.filename}"'},
    )


@router.get("/{document_id}/pages/{page}.png")
def render_page(document_id: uuid.UUID, page: int, user: CurrentUser, db: DB) -> Response:
    """Render one page as PNG, so the evidence viewer can overlay fact bounding boxes."""
    document = load_document(db, document_id, user)
    with pymupdf.open(stream=fetch_bytes(document), filetype=FILETYPES[document.mime_type]) as doc:
        if not 1 <= page <= doc.page_count:
            raise HTTPException(status_code=404, detail="Page not found")
        png = doc[page - 1].get_pixmap(dpi=RENDER_DPI).tobytes("png")
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/{document_id}/reprocess", status_code=202)
def reprocess_document(
    document_id: uuid.UUID,
    user: Annotated[User, Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))],
    db: DB,
) -> dict[str, str]:
    document = load_document(db, document_id, user)
    if document.processing_status == ProcessingStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="Document is already being processed")
    document.processing_status = ProcessingStatus.PENDING
    record_event(
        db,
        "document_reprocess_requested",
        application_id=document.application_id,
        actor_id=user.id,
        document_id=str(document.id),
    )
    db.commit()
    enqueue_processing(document.id)
    return {"status": "queued"}
