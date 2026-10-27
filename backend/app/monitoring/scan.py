"""Reconcile alerts with current obligations and drive the alert lifecycle.

    (new) ─▶ ACTIVE ─▶ OVERDUE ─▶ ESCALATED         ACKNOWLEDGED (by a user) ─▶ OVERDUE …
               │          │            │
               └──────────┴────────────┴──▶ RESOLVED ─▶ REOPENED (condition came back)

Only the scan resolves alerts automatically, and only when the condition is gone from the data.
Re-running a scan at the same time is a no-op (no duplicate alerts, no duplicate events).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_event
from app.config import get_settings
from app.models import Alert, Application
from app.models.enums import AlertStatus, Severity
from app.monitoring.obligations import Obligation, obligations_for

OPEN = {
    AlertStatus.ACTIVE,
    AlertStatus.ACKNOWLEDGED,
    AlertStatus.OVERDUE,
    AlertStatus.ESCALATED,
    AlertStatus.REOPENED,
}


@dataclass
class ScanResult:
    raised: int = 0
    updated: int = 0
    overdue: int = 0
    escalated: int = 0
    resolved: int = 0
    reopened: int = 0

    def __iadd__(self, other: "ScanResult") -> "ScanResult":
        for k in vars(self):
            setattr(self, k, getattr(self, k) + getattr(other, k))
        return self


SEVERITY_RANK = {s: i for i, s in enumerate(Severity)}


def _event(db: Session, alert: Alert, kind: str, **payload) -> None:
    record_event(
        db,
        f"alert_{kind}",
        application_id=alert.application_id,
        alert_id=str(alert.id),
        alert_type=alert.alert_type,
        title=alert.title,
        severity=alert.severity.value,
        **payload,
    )


def _should_reopen(alert: Alert, ob: Obligation) -> bool:
    """Auto-resolved alerts reopen whenever the condition is back. One a reviewer resolved by
    hand (an accepted alternative outcome) reopens only if the situation got worse."""
    if alert.resolved_by is None:
        return True
    worse = SEVERITY_RANK[ob.severity] > SEVERITY_RANK[alert.severity]
    return worse or ob.due_at != alert.due_at


def _advance(db: Session, alert: Alert, now: datetime, result: ScanResult) -> None:
    """Time-based transitions for an open alert."""
    if alert.due_at is None or now <= alert.due_at:
        return
    escalate_at = alert.due_at + timedelta(days=get_settings().escalate_after_days)
    if now > escalate_at and alert.status != AlertStatus.ESCALATED:
        alert.status, alert.escalated_at = AlertStatus.ESCALATED, now
        result.escalated += 1
        _event(db, alert, "escalated")
    elif alert.status in (AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED, AlertStatus.REOPENED):
        alert.status = AlertStatus.OVERDUE
        result.overdue += 1
        _event(db, alert, "overdue")


def _apply(alert: Alert, ob: Obligation) -> bool:
    """Copy the obligation's current facts onto the alert; True if anything visible changed."""
    changed = (alert.severity, alert.title, alert.due_at) != (ob.severity, ob.title, ob.due_at)
    alert.severity, alert.title, alert.message = ob.severity, ob.title, ob.message
    alert.due_at, alert.details, alert.audience = ob.due_at, ob.details, ob.audience
    return changed


def scan_application(db: Session, app: Application, now: datetime) -> ScanResult:
    result = ScanResult()
    obligations = {o.dedup_key: o for o in obligations_for(db, app, now)}
    existing = {
        a.dedup_key: a for a in db.scalars(select(Alert).where(Alert.application_id == app.id))
    }

    for key, ob in obligations.items():
        alert = existing.get(key)
        if alert is None:
            alert = Alert(
                institution_id=ob.institution_id,
                application_id=ob.application_id,
                alert_type=ob.alert_type,
                dedup_key=key,
                status=AlertStatus.ACTIVE,
            )
            _apply(alert, ob)
            db.add(alert)
            db.flush()
            result.raised += 1
            _event(db, alert, "raised", due_at=ob.due_at.isoformat())
        elif alert.status == AlertStatus.RESOLVED:
            if not _should_reopen(alert, ob):
                continue
            _apply(alert, ob)
            alert.status, alert.resolved_at, alert.resolved_by = AlertStatus.REOPENED, None, None
            alert.resolution_note = None
            result.reopened += 1
            _event(db, alert, "reopened")
        elif _apply(alert, ob):
            result.updated += 1
        alert.last_seen_at = now
        _advance(db, alert, now, result)

    for key, alert in existing.items():
        if key not in obligations and alert.status in OPEN:
            alert.status, alert.resolved_at = AlertStatus.RESOLVED, now
            alert.resolution_note = "Resolved automatically: the condition is no longer present."
            result.resolved += 1
            _event(db, alert, "resolved", automatic=True)
    return result


def scan_all(db: Session, now: datetime) -> ScanResult:
    total = ScanResult()
    for app in db.scalars(select(Application)):
        total += scan_application(db, app, now)
    return total
