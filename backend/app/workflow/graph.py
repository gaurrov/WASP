"""The case workflow for one application, as a LangGraph state machine.

    START → wait_for_extraction ⟲ → evaluate → human_review
               ↑                                   ├─ decide → finalize → END
               │                                   ├─ clarification → request_clarification
               │                                   │      → await_institution ⟲ (until resubmitted)
               └── resubmitted / reevaluate ───────┘

Pauses (`interrupt`) wait for the outside world: extraction to finish, a reviewer to act, or the
institution to resubmit. State is checkpointed in Postgres, so a case can wait for days and
resume in any worker process. On resume LangGraph re-runs the paused node from the top, so nodes
that pause do nothing else; side effects live in separate nodes that run exactly once per pass.

The database (applications, findings, events) remains the source of truth; graph state only
holds what the workflow needs to route and to compute what changed between evaluations.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import select

from app.audit import record_event
from app.db import SessionLocal
from app.models import Application, Document, Finding
from app.models.enums import ApplicationStatus, FindingStatus, ProcessingStatus
from app.rules.engine import active_rules, evaluate
from app.workflow.affected import affected_rule_codes, changed_documents, document_snapshot

CLEAN = {FindingStatus.PASS, FindingStatus.NOT_APPLICABLE}


class CaseState(TypedDict, total=False):
    application_id: str
    evaluated_documents: dict[str, str]  # {doc id: doc type} at the last evaluation
    round: int
    rechecked: list[str]
    extraction_pending: bool
    event: dict[str, Any]  # the last external event that resumed the graph


def _application(db, state: CaseState) -> Application:
    return db.get(Application, uuid.UUID(state["application_id"]))


# --- Nodes ---------------------------------------------------------------------------------


def wait_for_extraction(state: CaseState) -> CaseState:
    with SessionLocal() as db:
        application = _application(db, state)
        pending = db.scalar(
            select(Document.id).where(
                Document.application_id == application.id,
                Document.is_current,
                Document.processing_status.in_(
                    [ProcessingStatus.PENDING, ProcessingStatus.PROCESSING]
                ),
            )
        )
        if pending is None:
            return {"extraction_pending": False}
        if application.status != ApplicationStatus.PROCESSING:
            application.status = ApplicationStatus.PROCESSING
            db.commit()
    interrupt({"waiting_for": "extraction"})
    return {"extraction_pending": True}  # re-check on the next pass


def evaluate_rules(state: CaseState) -> CaseState:
    with SessionLocal() as db:
        application = _application(db, state)
        current = document_snapshot(db, application)
        rules = active_rules(db, application)
        previous = state.get("evaluated_documents")
        forced = state.get("event", {}).get("type") == "reevaluate"
        if previous is None or forced:
            only = None  # first evaluation, or reviewer asked for a full re-run
        else:
            only = affected_rule_codes(db, application, rules, changed_documents(previous, current))

        findings = evaluate(db, application, only=only)
        db.flush()
        rechecked = sorted({r.rule_code for r in rules} if only is None else only)
        statuses = list(
            db.scalars(
                select(Finding.status).where(
                    Finding.application_id == application.id, Finding.is_current
                )
            )
        )
        previous_status = application.status
        application.status = (
            ApplicationStatus.READY_FOR_DECISION
            if all(s in CLEAN for s in statuses)
            else ApplicationStatus.NEEDS_REVIEW
        )
        round_no = state.get("round", 0) + 1
        record_event(
            db,
            "application_evaluated",
            application_id=application.id,
            from_status=previous_status,
            to_status=application.status,
            round=round_no,
            rechecked=rechecked,
            carried_over=len(rules) - len(rechecked),
            findings={s.value: statuses.count(s) for s in FindingStatus if statuses.count(s)},
            new_findings=len(findings),
        )
        db.commit()
    return {"evaluated_documents": current, "rechecked": rechecked, "round": round_no}


def human_review(state: CaseState) -> CaseState:
    event = interrupt({"waiting_for": "reviewer"})
    return {"event": event}


def request_clarification(state: CaseState) -> CaseState:
    event = state["event"]
    with SessionLocal() as db:
        application = _application(db, state)
        previous = application.status
        application.status = ApplicationStatus.CLARIFICATION_REQUESTED
        application.clarification = {
            "message": event["message"],
            "finding_ids": event["finding_ids"],
            "requested_by": event["actor_id"],
            "requested_at": datetime.now(UTC).isoformat(),
        }
        record_event(
            db,
            "clarification_requested",
            application_id=application.id,
            actor_id=uuid.UUID(event["actor_id"]),
            from_status=previous,
            to_status=application.status,
            message=event["message"],
            finding_ids=event["finding_ids"],
        )
        db.commit()
    return {}


def await_institution(state: CaseState) -> CaseState:
    event = interrupt({"waiting_for": "institution"})
    return {"event": event}


def finalize(state: CaseState) -> CaseState:
    event = state["event"]
    approved = event["decision"] == "approve"
    with SessionLocal() as db:
        application = _application(db, state)
        previous = application.status
        application.status = ApplicationStatus.APPROVED if approved else ApplicationStatus.REJECTED
        application.decision = {
            "decision": event["decision"],
            "reason": event["reason"],
            "decided_by": event["actor_id"],
            "decided_at": datetime.now(UTC).isoformat(),
        }
        record_event(
            db,
            "application_decided",
            application_id=application.id,
            actor_id=uuid.UUID(event["actor_id"]),
            from_status=previous,
            to_status=application.status,
            decision=event["decision"],
            reason=event["reason"],
        )
        db.commit()
    return {}


# --- Routing -------------------------------------------------------------------------------


def after_extraction(state: CaseState) -> Literal["wait_for_extraction", "evaluate"]:
    return "wait_for_extraction" if state.get("extraction_pending") else "evaluate"


def after_review(
    state: CaseState,
) -> Literal["finalize", "request_clarification", "wait_for_extraction", "human_review"]:
    match state["event"].get("type"):
        case "decide":
            return "finalize"
        case "request_clarification":
            return "request_clarification"
        case "reevaluate" | "documents_changed":
            return "wait_for_extraction"
        case _:  # anything else (e.g. a stray event) keeps waiting for the reviewer
            return "human_review"


def after_institution(state: CaseState) -> Literal["wait_for_extraction", "await_institution"]:
    # Re-uploads during clarification process in the background; only resubmission continues.
    resubmitted = state["event"].get("type") == "resubmitted"
    return "wait_for_extraction" if resubmitted else "await_institution"


def build() -> StateGraph:
    g = StateGraph(CaseState)
    g.add_node("wait_for_extraction", wait_for_extraction)
    g.add_node("evaluate", evaluate_rules)
    g.add_node("human_review", human_review)
    g.add_node("request_clarification", request_clarification)
    g.add_node("await_institution", await_institution)
    g.add_node("finalize", finalize)

    g.add_edge(START, "wait_for_extraction")
    g.add_conditional_edges("wait_for_extraction", after_extraction)
    g.add_edge("evaluate", "human_review")
    g.add_conditional_edges("human_review", after_review)
    g.add_edge("request_clarification", "await_institution")
    g.add_conditional_edges("await_institution", after_institution)
    g.add_edge("finalize", END)
    return g
