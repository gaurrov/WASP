import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import WorkflowEvent


def record_event(
    db: Session,
    event_type: str,
    *,
    application_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    **payload: Any,
) -> None:
    """Append to the audit log in the caller's transaction, so the event commits with the change."""
    db.add(
        WorkflowEvent(
            application_id=application_id,
            event_type=event_type,
            actor_id=actor_id,
            from_status=from_status,
            to_status=to_status,
            payload=payload,
        )
    )
