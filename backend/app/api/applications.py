import hashlib
import re
import uuid
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Annotated

import pymupdf
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import record_event
from app.auth import CurrentUser, require_roles
from app.checklists import APPLICATION_TYPES
from app.config import get_settings
from app.db import get_db
from app.models import Application, Document, Institution, User
from app.models.enums import ApplicationStatus, DocumentType, ProcessingStatus, UserRole
from app.storage import get_s3

router = APIRouter(tags=["applications"])

DB = Annotated[Session, Depends(get_db)]
InstitutionUser = Annotated[User, Depends(require_roles(UserRole.INSTITUTION))]

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
# Sniff file signatures instead of trusting the client's Content-Type.
MAGIC_BYTES = {
    b"%PDF-": "application/pdf",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
}
EDITABLE_STATUSES = {ApplicationStatus.DRAFT, ApplicationStatus.CLARIFICATION_REQUESTED}


# --- Schemas -----------------------------------------------------------------------------


class ChecklistItemOut(BaseModel):
    doc_type: DocumentType
    label: str
    required: bool
    multiple: bool


class ApplicationTypeOut(BaseModel):
    code: str
    label: str
    checklist: list[ChecklistItemOut]


class DeclaredValues(BaseModel):
    """Values the institution declares on the form; later checked against document evidence."""

    programme: str = Field(min_length=1, max_length=255)
    sanctioned_intake: int = Field(ge=0, le=10_000)
    faculty_count: int = Field(ge=0, le=10_000)


class ApplicationCreate(BaseModel):
    application_type: str
    academic_year: str
    declared: DeclaredValues

    @field_validator("application_type")
    @classmethod
    def known_type(cls, v: str) -> str:
        if v not in APPLICATION_TYPES:
            raise ValueError(f"Unknown application type: {v}")
        return v

    @field_validator("academic_year")
    @classmethod
    def year_format(cls, v: str) -> str:
        m = re.fullmatch(r"(\d{4})-(\d{2})", v)
        if not m or (int(m[1]) + 1) % 100 != int(m[2]):
            raise ValueError("Academic year must look like 2026-27")
        return v


class DocumentOut(BaseModel):
    id: uuid.UUID
    doc_type: DocumentType
    filename: str
    mime_type: str
    sha256: str
    page_count: int | None
    version: int
    supersedes_id: uuid.UUID | None
    processing_status: ProcessingStatus
    created_at: datetime


class ChecklistStatus(ChecklistItemOut):
    document_count: int
    satisfied: bool


class ApplicationSummary(BaseModel):
    id: uuid.UUID
    institution_id: uuid.UUID
    institution_name: str
    application_type: str
    application_type_label: str
    academic_year: str
    status: ApplicationStatus
    submitted_at: datetime | None
    created_at: datetime
    document_count: int


class ApplicationDetail(ApplicationSummary):
    declared: DeclaredValues
    documents: list[DocumentOut]
    checklist: list[ChecklistStatus]
    missing_required: list[DocumentType]


# --- Helpers -----------------------------------------------------------------------------


def load_application(db: Session, application_id: uuid.UUID, user: User) -> Application:
    """Fetch an application the user may see. Returns 404 (not 403) to avoid leaking existence."""
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if user.role == UserRole.INSTITUTION and application.institution_id != user.institution_id:
        raise HTTPException(status_code=404, detail="Application not found")
    if user.role == UserRole.REVIEWER and application.status == ApplicationStatus.DRAFT:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


def require_editable(application: Application) -> None:
    if application.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Application is {application.status.value} and cannot be modified",
        )


def current_documents(db: Session, application_id: uuid.UUID) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.application_id == application_id, Document.is_current)
            .order_by(Document.created_at)
        )
    )


def to_summary(application: Application, institution_name: str, doc_count: int) -> dict:
    return {
        "id": application.id,
        "institution_id": application.institution_id,
        "institution_name": institution_name,
        "application_type": application.application_type,
        "application_type_label": APPLICATION_TYPES[application.application_type].label,
        "academic_year": application.academic_year,
        "status": application.status,
        "submitted_at": application.submitted_at,
        "created_at": application.created_at,
        "document_count": doc_count,
    }


def build_detail(db: Session, application: Application) -> ApplicationDetail:
    docs = current_documents(db, application.id)
    counts: dict[DocumentType, int] = {}
    for d in docs:
        counts[d.doc_type] = counts.get(d.doc_type, 0) + 1

    checklist = [
        ChecklistStatus(
            doc_type=item.doc_type,
            label=item.label,
            required=item.required,
            multiple=item.multiple,
            document_count=counts.get(item.doc_type, 0),
            satisfied=not item.required or counts.get(item.doc_type, 0) > 0,
        )
        for item in APPLICATION_TYPES[application.application_type].checklist
    ]
    institution = db.get(Institution, application.institution_id)
    return ApplicationDetail(
        **to_summary(application, institution.name, len(docs)),
        declared=DeclaredValues(**application.declared),
        documents=[DocumentOut.model_validate(d, from_attributes=True) for d in docs],
        checklist=checklist,
        missing_required=[c.doc_type for c in checklist if not c.satisfied],
    )


def sniff_mime(head: bytes) -> str | None:
    return next((mime for magic, mime in MAGIC_BYTES.items() if head.startswith(magic)), None)


def safe_filename(name: str | None) -> str:
    base = PurePath((name or "upload").replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip() or "upload"
    return base[-120:]


def count_pages(data: bytes, mime: str) -> int | None:
    if mime != "application/pdf":
        return 1
    try:
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            return pdf.page_count
    except Exception:  # corrupt PDFs are caught again (and flagged) by M2 processing
        return None


# --- Endpoints ---------------------------------------------------------------------------


@router.get("/application-types", response_model=list[ApplicationTypeOut])
def list_application_types(_: CurrentUser) -> list[ApplicationTypeOut]:
    return [
        ApplicationTypeOut(
            code=t.code,
            label=t.label,
            checklist=[ChecklistItemOut(**vars(i)) for i in t.checklist],
        )
        for t in APPLICATION_TYPES.values()
    ]


@router.post("/applications", response_model=ApplicationDetail, status_code=201)
def create_application(body: ApplicationCreate, user: InstitutionUser, db: DB) -> ApplicationDetail:
    application = Application(
        institution_id=user.institution_id,
        application_type=body.application_type,
        academic_year=body.academic_year,
        declared=body.declared.model_dump(),
        status=ApplicationStatus.DRAFT,
    )
    db.add(application)
    db.flush()
    record_event(
        db,
        "application_created",
        application_id=application.id,
        actor_id=user.id,
        to_status=ApplicationStatus.DRAFT,
    )
    db.commit()
    return build_detail(db, application)


@router.get("/applications", response_model=list[ApplicationSummary])
def list_applications(user: CurrentUser, db: DB) -> list[dict]:
    doc_count = (
        select(func.count(Document.id))
        .where(Document.application_id == Application.id, Document.is_current)
        .scalar_subquery()
    )
    query = (
        select(Application, Institution.name, doc_count)
        .join(Institution, Institution.id == Application.institution_id)
        .order_by(Application.created_at.desc())
    )
    if user.role == UserRole.INSTITUTION:
        query = query.where(Application.institution_id == user.institution_id)
    elif user.role == UserRole.REVIEWER:
        query = query.where(Application.status != ApplicationStatus.DRAFT)
    return [to_summary(a, name, n) for a, name, n in db.execute(query)]


@router.get("/applications/{application_id}", response_model=ApplicationDetail)
def get_application(application_id: uuid.UUID, user: CurrentUser, db: DB) -> ApplicationDetail:
    return build_detail(db, load_application(db, application_id, user))


@router.post(
    "/applications/{application_id}/documents", response_model=DocumentOut, status_code=201
)
def upload_document(
    application_id: uuid.UUID,
    user: InstitutionUser,
    db: DB,
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[DocumentType | None, Form()] = None,
    replaces_id: Annotated[uuid.UUID | None, Form()] = None,
) -> Document:
    application = load_application(db, application_id, user)
    require_editable(application)

    replaced: Document | None = None
    if replaces_id is not None:
        replaced = db.get(Document, replaces_id)
        if replaced is None or replaced.application_id != application.id or not replaced.is_current:
            raise HTTPException(status_code=404, detail="Document to replace not found")
        doc_type = doc_type or replaced.doc_type
    if doc_type is None:
        raise HTTPException(status_code=422, detail="doc_type is required")

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")
    mime = sniff_mime(data[:16])
    if mime is None:
        raise HTTPException(status_code=415, detail="Only PDF, PNG and JPEG files are accepted")

    sha256 = hashlib.sha256(data).hexdigest()
    duplicate = db.scalar(
        select(Document).where(
            Document.application_id == application.id,
            Document.sha256 == sha256,
            Document.is_current,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail=f"This file was already uploaded as '{duplicate.filename}'",
        )

    doc_id = uuid.uuid4()
    filename = safe_filename(file.filename)
    key = f"applications/{application.id}/{doc_id}/{filename}"
    get_s3().put_object(
        Bucket=get_settings().s3_bucket,
        Key=key,
        Body=data,
        ContentType=mime,
        Metadata={"sha256": sha256},
    )

    document = Document(
        id=doc_id,
        application_id=application.id,
        institution_id=application.institution_id,
        doc_type=doc_type,
        filename=filename,
        storage_key=key,
        sha256=sha256,
        mime_type=mime,
        page_count=count_pages(data, mime),
        uploaded_by=user.id,
    )
    if replaced is not None:
        replaced.is_current = False
        document.version = replaced.version + 1
        document.supersedes_id = replaced.id
    db.add(document)
    record_event(
        db,
        "document_uploaded",
        application_id=application.id,
        actor_id=user.id,
        document_id=str(doc_id),
        doc_type=doc_type.value,
        sha256=sha256,
        replaces_id=str(replaced.id) if replaced else None,
    )
    db.commit()
    return document


@router.delete("/applications/{application_id}/documents/{document_id}", status_code=204)
def delete_document(
    application_id: uuid.UUID, document_id: uuid.UUID, user: InstitutionUser, db: DB
) -> None:
    application = load_application(db, application_id, user)
    # After submission documents are evidence: replace them (keeps history), don't delete.
    if application.status != ApplicationStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Documents can only be deleted from drafts")
    document = db.get(Document, document_id)
    if document is None or document.application_id != application.id:
        raise HTTPException(status_code=404, detail="Document not found")
    get_s3().delete_object(Bucket=get_settings().s3_bucket, Key=document.storage_key)
    db.delete(document)
    record_event(
        db,
        "document_deleted",
        application_id=application.id,
        actor_id=user.id,
        document_id=str(document_id),
    )
    db.commit()


@router.get("/documents/{document_id}/content")
def download_document(document_id: uuid.UUID, user: CurrentUser, db: DB) -> StreamingResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    load_application(db, document.application_id, user)  # enforces tenant/role visibility
    obj = get_s3().get_object(Bucket=get_settings().s3_bucket, Key=document.storage_key)
    return StreamingResponse(
        obj["Body"].iter_chunks(),
        media_type=document.mime_type,
        headers={"Content-Disposition": f'inline; filename="{document.filename}"'},
    )


@router.post("/applications/{application_id}/submit", response_model=ApplicationDetail)
def submit_application(
    application_id: uuid.UUID, user: InstitutionUser, db: DB
) -> ApplicationDetail:
    application = load_application(db, application_id, user)
    require_editable(application)
    # Missing documents don't block submission: completeness becomes a reviewable finding (M3).
    previous = application.status
    application.status = ApplicationStatus.SUBMITTED
    application.submitted_at = datetime.now(UTC)
    record_event(
        db,
        "application_submitted",
        application_id=application.id,
        actor_id=user.id,
        from_status=previous,
        to_status=ApplicationStatus.SUBMITTED,
    )
    db.commit()
    return build_detail(db, application)
