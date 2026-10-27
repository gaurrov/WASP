import uuid
from datetime import date
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.models.base import Base, IdMixin, TimestampMixin, str_enum
from app.models.enums import ProcessingStatus, RuleStatus, Severity


class RegulatorySource(IdMixin, TimestampMixin, Base):
    """An official document (APH, circular, amendment) at a specific version."""

    __tablename__ = "regulatory_sources"
    __table_args__ = (UniqueConstraint("title", "version"),)

    title: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(32))  # handbook | regulation | circular
    version: Mapped[str] = mapped_column(String(64))
    published_on: Mapped[date | None] = mapped_column(Date)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(512))
    ingest_status: Mapped[ProcessingStatus] = mapped_column(
        str_enum(ProcessingStatus), default=ProcessingStatus.PENDING
    )
    ingest_error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    chunks: Mapped[list["RegulatoryChunk"]] = relationship(back_populates="source")


class RegulatoryChunk(IdMixin, Base):
    """A clause-level chunk, searchable by both vector similarity and full-text (hybrid RAG)."""

    __tablename__ = "regulatory_chunks"
    __table_args__ = (
        Index("ix_regulatory_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_regulatory_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("regulatory_sources.id", ondelete="CASCADE"), index=True
    )
    section: Mapped[str | None] = mapped_column(String(64))  # e.g. "Chapter III, 3.2(b)"
    heading: Mapped[str | None] = mapped_column(String(512))
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(get_settings().embedding_dim))
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(heading, '') || ' ' || text)", persisted=True),
    )

    source: Mapped[RegulatorySource] = relationship(back_populates="chunks")


class ComplianceRule(IdMixin, TimestampMixin, Base):
    """An executable, versioned rule. Versions are immutable; changes create a new version."""

    __tablename__ = "compliance_rules"
    __table_args__ = (UniqueConstraint("rule_code", "version"),)

    rule_code: Mapped[str] = mapped_column(String(64), index=True)  # e.g. "FACULTY-001"
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regulatory_sources.id"))
    source_section: Mapped[str | None] = mapped_column(String(64))
    # Which applications the rule applies to, e.g. {"application_type": [...], "level": [...]}.
    applicability: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evaluator: Mapped[str] = mapped_column(String(255))  # dotted path to a Python function
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    required_evidence: Mapped[list[str]] = mapped_column(JSONB, default=list)
    severity: Mapped[Severity] = mapped_column(str_enum(Severity), default=Severity.MEDIUM)
    # Internal rules check data consistency (e.g. declared vs evidenced faculty count) and need
    # no regulatory citation. Regulatory rules stay DRAFT until a reviewer verifies the clause.
    internal: Mapped[bool] = mapped_column(default=False)
    citation_query: Mapped[str | None] = mapped_column(Text)  # used to retrieve the clause
    norm_note: Mapped[str | None] = mapped_column(Text)  # where the numbers came from
    source_page: Mapped[int | None] = mapped_column(Integer)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[RuleStatus] = mapped_column(str_enum(RuleStatus), default=RuleStatus.DRAFT)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
