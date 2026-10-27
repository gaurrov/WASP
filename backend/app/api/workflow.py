import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.applications import load_application
from app.audit import record_event
from app.auth import CurrentUser, require_roles
from app.db import get_db
from app.models import Application, Finding, ReviewDecision, User, WorkflowEvent
from app.models.enums import FindingStatus, ReviewOutcome, UserRole
from app.rules.engine import active_rules
from app.workflow import runner
from app.workflow.reviews import latest_reviews
from app.workflow.tasks import send_event

router = APIRouter(tags=["workflow"])

DB = Annotated[Session, Depends(get_db)]
Staff = Annotated[User, Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))]
OPEN = {FindingStatus.FAIL, FindingStatus.NEEDS_REVIEW, FindingStatus.UNABLE_TO_DETERMINE}


class EventOut(BaseModel):
    event_type: str
    from_status: str | None
    to_status: str | None
    actor: str | None
    payload: dict[str, Any]
    created_at: datetime


class WorkflowOut(BaseModel):
    started: bool
    finished: bool
    waiting_for: str | None
    round: int
    rechecked: list[str]
    total_rules: int
    clarification: dict[str, Any] | None
    decision: dict[str, Any] | None
    unreviewed_findings: int
    confirmed_deficiencies: int
    events: list[EventOut]


class ReviewIn(BaseModel):
    outcome: Literal["confirm", "override"]
    comment: str | None = Field(default=None, max_length=2000)


class ClarificationIn(BaseModel):
    message: str = Field(min_length=5, max_length=4000)
    finding_ids: list[uuid.UUID] = Field(min_length=1)


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=5, max_length=4000)


def review_state(db: Session, application: Application) -> tuple[int, int]:
    """(open findings without a review, open findings a reviewer confirmed as deficiencies)."""
    open_findings = list(
        db.scalars(
            select(Finding).where(
                Finding.application_id == application.id,
                Finding.is_current,
                Finding.status.in_(OPEN),
            )
        )
    )
    reviews = latest_reviews(db, [f.id for f in open_findings])
    unreviewed = sum(f.id not in reviews for f in open_findings)
    confirmed = sum(
        f.id in reviews and reviews[f.id].outcome == ReviewOutcome.CONFIRM for f in open_findings
    )
    return unreviewed, confirmed


def require_waiting_for_reviewer(application: Application) -> None:
    if runner.status(application.id).waiting_for != "reviewer":
        raise HTTPException(status_code=409, detail="This application is not awaiting review")


@router.get("/applications/{application_id}/workflow", response_model=WorkflowOut)
def get_workflow(application_id: uuid.UUID, user: CurrentUser, db: DB) -> WorkflowOut:
    application = load_application(db, application_id, user)
    case = runner.status(application.id)
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    events = db.scalars(
        select(WorkflowEvent)
        .where(WorkflowEvent.application_id == application.id)
        .order_by(WorkflowEvent.created_at)
    )
    unreviewed, confirmed = review_state(db, application)
    return WorkflowOut(
        started=case.started,
        finished=case.finished,
        waiting_for=case.waiting_for,
        round=case.round,
        rechecked=case.rechecked,
        total_rules=len(active_rules(db, application)),
        clarification=application.clarification,
        decision=application.decision,
        unreviewed_findings=unreviewed,
        confirmed_deficiencies=confirmed,
        events=[
            EventOut(
                event_type=e.event_type,
                from_status=e.from_status,
                to_status=e.to_status,
                actor=names.get(e.actor_id),
                payload=e.payload,
                created_at=e.created_at,
            )
            for e in events
        ],
    )


@router.post("/findings/{finding_id}/review", status_code=201)
def review_finding(finding_id: uuid.UUID, body: ReviewIn, user: Staff, db: DB) -> dict[str, str]:
    finding = db.get(Finding, finding_id)
    if finding is None or not finding.is_current:
        raise HTTPException(status_code=404, detail="Finding not found")
    application = load_application(db, finding.application_id, user)
    require_waiting_for_reviewer(application)
    if finding.status not in OPEN:
        raise HTTPException(status_code=409, detail="Only open findings need a review")
    if body.outcome == "override" and not (body.comment and len(body.comment.strip()) >= 5):
        raise HTTPException(status_code=422, detail="Overriding a finding requires a justification")
    db.add(
        ReviewDecision(
            finding_id=finding.id,
            application_id=application.id,
            reviewer_id=user.id,
            outcome=ReviewOutcome(body.outcome),
            comment=body.comment,
        )
    )
    record_event(
        db,
        "finding_reviewed",
        application_id=application.id,
        actor_id=user.id,
        finding_id=str(finding.id),
        outcome=body.outcome,
        comment=body.comment,
    )
    db.commit()
    return {"status": "recorded"}


@router.post("/applications/{application_id}/clarification", status_code=202)
def request_clarification(
    application_id: uuid.UUID, body: ClarificationIn, user: Staff, db: DB
) -> dict[str, str]:
    application = load_application(db, application_id, user)
    require_waiting_for_reviewer(application)
    current = set(
        db.scalars(
            select(Finding.id).where(Finding.application_id == application.id, Finding.is_current)
        )
    )
    if not set(body.finding_ids) <= current:
        raise HTTPException(status_code=422, detail="Unknown finding for this application")
    send_event(
        application.id,
        {
            "type": "request_clarification",
            "message": body.message,
            "finding_ids": [str(f) for f in body.finding_ids],
            "actor_id": str(user.id),
        },
    )
    return {"status": "queued"}


@router.post("/applications/{application_id}/decision", status_code=202)
def decide(application_id: uuid.UUID, body: DecisionIn, user: Staff, db: DB) -> dict[str, str]:
    application = load_application(db, application_id, user)
    require_waiting_for_reviewer(application)
    if body.decision == "approve":
        unreviewed, confirmed = review_state(db, application)
        if unreviewed:
            raise HTTPException(
                status_code=409,
                detail=f"Review all open findings before approving ({unreviewed} remaining)",
            )
        if confirmed:
            raise HTTPException(
                status_code=409,
                detail=f"{confirmed} confirmed deficiency(ies): request clarification or reject",
            )
    send_event(
        application.id,
        {
            "type": "decide",
            "decision": body.decision,
            "reason": body.reason,
            "actor_id": str(user.id),
        },
    )
    return {"status": "queued"}
