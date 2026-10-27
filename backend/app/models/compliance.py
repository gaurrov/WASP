import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, str_enum
from app.models.enums import AlertStatus, FindingStatus, ReviewOutcome, Severity


class Finding(IdMixin, TimestampMixin, Base):
    """Result of evaluating one rule version against one application's evidence."""

    __tablename__ = "findings"

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("compliance_rules.id"), index=True)
    status: Mapped[FindingStatus] = mapped_column(str_enum(FindingStatus))
    severity: Mapped[Severity] = mapped_column(str_enum(Severity), default=Severity.MEDIUM)
    reason: Mapped[str] = mapped_column(Text)
    # Provenance: which extracted facts and regulatory chunks this result rests on.
    # These ids drive incremental re-validation when a document is replaced.
    evidence_fact_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID), default=list)
    source_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID), default=list)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_current: Mapped[bool] = mapped_column(default=True, index=True)


class ReviewDecision(IdMixin, TimestampMixin, Base):
    __tablename__ = "review_decisions"

    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id"), index=True)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    outcome: Mapped[ReviewOutcome] = mapped_column(str_enum(ReviewOutcome))
    comment: Mapped[str | None] = mapped_column(Text)


class Alert(IdMixin, TimestampMixin, Base):
    """A monitored obligation (expiring certificate, overdue response, review SLA).

    Created and updated by the monitoring scan; one row per obligation (dedup_key), so repeated
    scans update it. It resolves only when the scan sees the condition cleared in the data, or
    when a reviewer records an alternative outcome.
    """

    __tablename__ = "alerts"

    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("applications.id"))
    finding_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("findings.id"))
    alert_type: Mapped[str] = mapped_column(String(64))  # e.g. "certificate_expiry"
    # institution + obligation + evidence + type; repeated scans update instead of duplicating.
    dedup_key: Mapped[str] = mapped_column(String(255), unique=True)
    severity: Mapped[Severity] = mapped_column(str_enum(Severity))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[AlertStatus] = mapped_column(
        str_enum(AlertStatus), default=AlertStatus.ACTIVE, index=True
    )
    # Who must act: "institution" (its users) or "reviewer" (the AICTE reviewer pool).
    audience: Mapped[str] = mapped_column(String(16), default="institution", index=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowEvent(IdMixin, Base):
    """Append-only audit log of state transitions and significant actions."""

    __tablename__ = "workflow_events"

    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
