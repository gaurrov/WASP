import logging
import uuid

from kombu.exceptions import OperationalError

from app.worker import celery_app
from app.workflow.runner import advance

log = logging.getLogger(__name__)


def send_event(application_id: uuid.UUID, event: dict | None = None) -> None:
    """Start or resume the case workflow in a worker. `event=None` starts it."""
    try:
        advance_case.delay(str(application_id), event)
    except OperationalError:
        log.exception("Could not enqueue workflow event %s for %s", event, application_id)


@celery_app.task(name="app.workflow.advance_case")
def advance_case(application_id: str, event: dict | None = None) -> None:
    advance(application_id, event)
