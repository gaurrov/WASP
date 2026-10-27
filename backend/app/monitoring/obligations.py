"""Derive the obligations that should be alerted on *right now* from the current data.

Each detector is a function of (application, now) that returns zero or more Obligations. The
scan turns them into alerts; an obligation that stops being returned (e.g. a renewed certificate
was uploaded) is how an alert gets resolved. Detectors never send anything themselves.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Application, Document, ExtractedFact, WorkflowEvent
from app.models.enums import ApplicationStatus, Severity

# Applications whose obligations are monitored: under review, waiting, or approved.
MONITORED = {
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.PROCESSING,
    ApplicationStatus.NEEDS_REVIEW,
    ApplicationStatus.CLARIFICATION_REQUESTED,
    ApplicationStatus.READY_FOR_DECISION,
    ApplicationStatus.APPROVED,
}
AWAITING_REVIEW = {ApplicationStatus.NEEDS_REVIEW, ApplicationStatus.READY_FOR_DECISION}
CERTIFICATE_LABELS = {"fire_noc": "Fire safety NOC"}


@dataclass
class Obligation:
    dedup_key: str
    institution_id: uuid.UUID
    application_id: uuid.UUID
    alert_type: str
    audience: str  # "institution" | "reviewer"
    severity: Severity
    title: str
    message: str
    due_at: datetime
    details: dict[str, Any] = field(default_factory=dict)


def _start_of_day(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


def certificate_expiry(db: Session, app: Application, now: datetime) -> list[Obligation]:
    """Certificates whose extracted validity date is within the warning window or past."""
    settings = get_settings()
    rows = db.execute(
        select(ExtractedFact, Document)
        .join(Document, Document.id == ExtractedFact.document_id)
        .where(
            Document.application_id == app.id,
            Document.is_current,
            ExtractedFact.field_name == "valid_until",
        )
    ).all()
    obligations = []
    for fact, document in rows:
        try:
            valid_until = date.fromisoformat(fact.value)
        except (TypeError, ValueError):
            continue  # unreadable dates are already a finding for the reviewer
        days = (valid_until - now.date()).days
        if days > settings.expiry_warning_days:
            continue
        label = CERTIFICATE_LABELS.get(document.doc_type.value, document.doc_type.value)
        if days < 0:
            severity, when = Severity.CRITICAL, f"expired on {valid_until:%d %b %Y}"
        elif days <= settings.expiry_urgent_days:
            severity, when = Severity.HIGH, f"expires in {days} days ({valid_until:%d %b %Y})"
        else:
            severity, when = Severity.MEDIUM, f"expires in {days} days ({valid_until:%d %b %Y})"
        obligations.append(
            Obligation(
                dedup_key=f"cert-expiry:{app.id}:{document.doc_type.value}",
                institution_id=app.institution_id,
                application_id=app.id,
                alert_type="certificate_expiry",
                audience="institution",
                severity=severity,
                title=f"{label} {when}",
                message=(
                    f"Upload a renewed {label} to this application. The alert closes "
                    "automatically once a document with a later validity date is processed."
                ),
                due_at=_start_of_day(valid_until),
                details={
                    "document_id": str(document.id),
                    "fact_id": str(fact.id),
                    "valid_until": valid_until.isoformat(),
                    "days_remaining": days,
                },
            )
        )
    return obligations


def clarification_response(db: Session, app: Application, now: datetime) -> list[Obligation]:
    """An open clarification request is a task for the institution with a response deadline."""
    if app.status != ApplicationStatus.CLARIFICATION_REQUESTED or not app.clarification:
        return []
    requested_at = datetime.fromisoformat(app.clarification["requested_at"])
    due = requested_at + timedelta(days=get_settings().clarification_response_days)
    overdue = now > due
    return [
        Obligation(
            dedup_key=f"clarification:{app.id}:{requested_at.isoformat()}",
            institution_id=app.institution_id,
            application_id=app.id,
            alert_type="clarification_response",
            audience="institution",
            severity=Severity.HIGH if overdue else Severity.LOW,
            title=(
                f"Clarification response overdue since {due:%d %b %Y}"
                if overdue
                else f"Respond to AICTE's clarification request by {due:%d %b %Y}"
            ),
            message=app.clarification["message"],
            due_at=due,
            details={"requested_at": requested_at.isoformat()},
        )
    ]


def review_sla(db: Session, app: Application, now: datetime) -> list[Obligation]:
    """Applications waiting for a reviewer longer than the SLA (alerted 2 days before)."""
    if app.status not in AWAITING_REVIEW:
        return []
    since = db.scalar(
        select(WorkflowEvent.created_at)
        .where(
            WorkflowEvent.application_id == app.id,
            WorkflowEvent.to_status.in_([s.value for s in AWAITING_REVIEW]),
        )
        .order_by(WorkflowEvent.created_at.desc())
        .limit(1)
    )
    if since is None:
        return []
    due = since + timedelta(days=get_settings().review_sla_days)
    if now < due - timedelta(days=2):
        return []
    overdue = now > due
    return [
        Obligation(
            dedup_key=f"review-sla:{app.id}:{since.isoformat()}",
            institution_id=app.institution_id,
            application_id=app.id,
            alert_type="review_sla",
            audience="reviewer",
            severity=Severity.HIGH if overdue else Severity.MEDIUM,
            title=(
                f"Review overdue since {due:%d %b %Y}"
                if overdue
                else f"Review due by {due:%d %b %Y}"
            ),
            message="This application is waiting for a reviewer's decision or clarification.",
            due_at=due,
            details={"waiting_since": since.isoformat()},
        )
    ]


DETECTORS = [certificate_expiry, clarification_response, review_sla]


def obligations_for(db: Session, app: Application, now: datetime) -> list[Obligation]:
    if app.status not in MONITORED:
        return []
    return [o for detect in DETECTORS for o in detect(db, app, now)]
