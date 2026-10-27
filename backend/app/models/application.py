import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin, str_enum
from app.models.enums import ApplicationStatus, DocumentType, ProcessingStatus


class Application(IdMixin, TimestampMixin, Base):
    __tablename__ = "applications"

    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    application_type: Mapped[str] = mapped_column(String(64))  # e.g. "extension_of_approval"
    academic_year: Mapped[str] = mapped_column(String(16))  # e.g. "2026-27"
    status: Mapped[ApplicationStatus] = mapped_column(
        str_enum(ApplicationStatus), default=ApplicationStatus.DRAFT, index=True
    )
    # Declared values from the application form, compared against extracted evidence.
    declared: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    documents: Mapped[list["Document"]] = relationship(back_populates="application")


class Document(IdMixin, TimestampMixin, Base):
    """One uploaded file version. Re-uploads create a new row that supersedes the old one."""

    __tablename__ = "documents"

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    doc_type: Mapped[DocumentType] = mapped_column(
        str_enum(DocumentType), default=DocumentType.UNCLASSIFIED
    )
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(128))
    page_count: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    is_current: Mapped[bool] = mapped_column(default=True)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        str_enum(ProcessingStatus), default=ProcessingStatus.PENDING
    )
    processing_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # What the classifier thinks this is; compared with the institution's declared doc_type.
    detected_doc_type: Mapped[DocumentType | None] = mapped_column(str_enum(DocumentType))
    detection_confidence: Mapped[float | None] = mapped_column(Float)
    ocr_used: Mapped[bool | None] = mapped_column()
    # [{number, width, height, ocr}] in PDF points, for overlaying evidence boxes.
    pages: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    application: Mapped[Application] = relationship(back_populates="documents")
    facts: Mapped[list["ExtractedFact"]] = relationship(back_populates="document")


class ExtractedFact(IdMixin, TimestampMixin, Base):
    """A single extracted value with provenance, so every finding can point back to a page."""

    __tablename__ = "extracted_facts"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[Any] = mapped_column(JSONB)
    raw_text: Mapped[str | None] = mapped_column(Text)  # the matched text before normalization
    confidence: Mapped[float] = mapped_column(Float)
    page: Mapped[int | None] = mapped_column(Integer)
    # [x0, y0, x1, y1] in PDF points, when the extractor can locate the value.
    bbox: Mapped[list[float] | None] = mapped_column(JSONB)
    extractor: Mapped[str] = mapped_column(String(64))  # e.g. "pymupdf", "paddleocr+llm"

    document: Mapped[Document] = relationship(back_populates="facts")
