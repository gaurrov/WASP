import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.audit import record_event
from app.auth import CurrentUser, require_roles
from app.checklists import APPLICATION_TYPES
from app.config import get_settings
from app.db import get_db
from app.models import Alert, Application, Institution, User
from app.models.enums import AlertStatus, Severity, UserRole
from app.monitoring.scan import OPEN, scan_all

router = APIRouter(tags=["alerts"])

DB = Annotated[Session, Depends(get_db)]
Staff = Annotated[User, Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))]
Admin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


class AlertOut(BaseModel):
    id: uuid.UUID
    alert_type: str
    audience: str
    severity: Severity
    status: AlertStatus
    title: str
    message: str
    due_at: datetime | None
    details: dict[str, Any]
    institution_name: str
    application_id: uuid.UUID | None
    application_label: str | None
    created_at: datetime
    acknowledged_at: datetime | None
    escalated_at: datetime | None
    resolved_at: datetime | None
    resolution_note: str | None


class ResolveIn(BaseModel):
    note: str = Field(min_length=5, max_length=2000)


class ScanIn(BaseModel):
    # Dev-only: evaluate obligations as if it were this moment (demo "time travel").
    as_of: datetime | None = None


def visible(query: Select, user: User) -> Select:
    """Institutions see their own institution-facing alerts; staff see everything."""
    if user.role == UserRole.INSTITUTION:
        return query.where(
            Alert.institution_id == user.institution_id, Alert.audience == "institution"
        )
    return query


def load_alert(db: Session, alert_id: uuid.UUID, user: User) -> Alert:
    alert = db.scalar(visible(select(Alert).where(Alert.id == alert_id), user))
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    user: CurrentUser,
    db: DB,
    status: Literal["open", "resolved", "all"] = "open",
    application_id: uuid.UUID | None = None,
) -> list[AlertOut]:
    q = visible(
        select(Alert, Institution.name, Application)
        .join(Institution, Institution.id == Alert.institution_id)
        .outerjoin(Application, Application.id == Alert.application_id),
        user,
    )
    if status == "open":
        q = q.where(Alert.status.in_(OPEN))
    elif status == "resolved":
        q = q.where(Alert.status == AlertStatus.RESOLVED)
    if application_id:
        q = q.where(Alert.application_id == application_id)

    rank = {s: i for i, s in enumerate(reversed(list(Severity)))}
    rows = sorted(
        db.execute(q).all(),
        key=lambda r: (rank[r[0].severity], r[0].due_at or datetime.max.replace(tzinfo=UTC)),
    )
    return [
        AlertOut(
            **{f: getattr(a, f) for f in AlertOut.model_fields if hasattr(a, f)},
            institution_name=name,
            application_label=(
                f"{APPLICATION_TYPES[app.application_type].label} {app.academic_year}"
                if app
                else None
            ),
        )
        for a, name, app in rows
    ]


@router.get("/alerts/summary")
def alerts_summary(user: CurrentUser, db: DB) -> dict[str, int]:
    rows = db.execute(
        visible(select(Alert.severity, func.count()).where(Alert.status.in_(OPEN)), user).group_by(
            Alert.severity
        )
    ).all()
    counts = {s.value: n for s, n in rows}
    return {
        "open": sum(counts.values()),
        "critical": counts.get("critical", 0),
        "high": counts.get("high", 0),
    }


@router.post("/alerts/{alert_id}/acknowledge", response_model=dict)
def acknowledge(alert_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, str]:
    alert = load_alert(db, alert_id, user)
    if alert.status not in OPEN:
        raise HTTPException(status_code=409, detail="Alert is not open")
    alert.acknowledged_at, alert.acknowledged_by = datetime.now(UTC), user.id
    if alert.status in (AlertStatus.ACTIVE, AlertStatus.REOPENED):
        alert.status = AlertStatus.ACKNOWLEDGED  # overdue/escalated stay visible as such
    record_event(
        db,
        "alert_acknowledged",
        application_id=alert.application_id,
        actor_id=user.id,
        alert_id=str(alert.id),
        title=alert.title,
    )
    db.commit()
    return {"status": alert.status.value}


@router.post("/alerts/{alert_id}/resolve", response_model=dict)
def resolve(alert_id: uuid.UUID, body: ResolveIn, user: Staff, db: DB) -> dict[str, str]:
    """Record an alternative outcome (e.g. renewal verified offline). Normally alerts resolve
    themselves when the data changes; this is the accountable manual path."""
    alert = load_alert(db, alert_id, user)
    if alert.status not in OPEN:
        raise HTTPException(status_code=409, detail="Alert is not open")
    alert.status, alert.resolved_at, alert.resolved_by = (
        AlertStatus.RESOLVED,
        datetime.now(UTC),
        user.id,
    )
    alert.resolution_note = body.note
    record_event(
        db,
        "alert_resolved",
        application_id=alert.application_id,
        actor_id=user.id,
        alert_id=str(alert.id),
        title=alert.title,
        note=body.note,
        automatic=False,
    )
    db.commit()
    return {"status": alert.status.value}


@router.post("/monitoring/scan", response_model=dict)
def run_scan(body: ScanIn, user: Admin, db: DB) -> dict[str, Any]:
    if body.as_of and get_settings().env != "dev":
        raise HTTPException(status_code=403, detail="Simulated time is only allowed in dev")
    now = body.as_of or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    result = scan_all(db, now)
    record_event(
        db,
        "monitoring_scan",
        actor_id=user.id,
        as_of=now.isoformat(),
        simulated=body.as_of is not None,
        **vars(result),
    )
    db.commit()
    return {"as_of": now.isoformat(), **vars(result)}
