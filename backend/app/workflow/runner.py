"""Drive a case's graph: start it, feed it external events, and report where it's waiting."""

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from app.config import get_settings
from app.monitoring.tasks import request_scan
from app.workflow.graph import build

log = logging.getLogger(__name__)


def _conninfo() -> str:
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")


@contextmanager
def _graph() -> Iterator[Any]:
    with psycopg.connect(_conninfo(), autocommit=True, prepare_threshold=0) as conn:
        yield build().compile(checkpointer=PostgresSaver(conn))


def setup_checkpointer() -> None:
    """Create LangGraph's checkpoint tables (idempotent)."""
    with psycopg.connect(_conninfo(), autocommit=True) as conn:
        PostgresSaver(conn).setup()


def _config(application_id: uuid.UUID | str) -> dict:
    return {"configurable": {"thread_id": str(application_id)}}


@contextmanager
def _case_lock(application_id: uuid.UUID | str) -> Iterator[None]:
    """One event at a time per case: a document finishing extraction and a reviewer clicking a
    button must not advance the same graph concurrently."""
    with psycopg.connect(_conninfo(), autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(hashtext(%s))", (str(application_id),))
        try:
            yield
        finally:
            conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (str(application_id),))


@dataclass
class CaseStatus:
    started: bool
    finished: bool
    waiting_for: str | None  # "extraction" | "reviewer" | "institution" | None
    round: int
    rechecked: list[str]


def advance(application_id: uuid.UUID | str, event: dict | None = None) -> CaseStatus:
    """Start the case (no checkpoint yet) or resume it with `event`. Events that arrive after
    the case finished are ignored."""
    with _case_lock(application_id), _graph() as graph:
        config = _config(application_id)
        state = graph.get_state(config)
        if not state.values:
            graph.invoke({"application_id": str(application_id)}, config)
        elif state.next:
            graph.invoke(Command(resume=event or {"type": "noop"}), config)
        else:
            log.info("Case %s already finished; ignoring %s", application_id, event)
        case = _status(graph, config)
    # Workflow transitions open or close obligations (clarification deadlines, review SLAs).
    request_scan(application_id)
    return case


def status(application_id: uuid.UUID | str) -> CaseStatus:
    with _graph() as graph:
        return _status(graph, _config(application_id))


def _status(graph: Any, config: dict) -> CaseStatus:
    state = graph.get_state(config)
    interrupts = [i.value for task in state.tasks for i in task.interrupts]
    return CaseStatus(
        started=bool(state.values),
        finished=bool(state.values) and not state.next,
        waiting_for=interrupts[0]["waiting_for"] if interrupts else None,
        round=state.values.get("round", 0),
        rechecked=state.values.get("rechecked", []),
    )
