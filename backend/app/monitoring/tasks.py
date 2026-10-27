import logging
import time
import uuid
from datetime import UTC, datetime

import redis
from celery.signals import beat_init
from kombu.exceptions import OperationalError

from app.config import get_settings
from app.db import SessionLocal
from app.models import Application
from app.monitoring.scan import scan_all, scan_application
from app.worker import celery_app

log = logging.getLogger(__name__)

# Written by every scheduled scan so `python -m app.demo preflight` can tell beat is alive.
BEAT_HEARTBEAT_KEY = "wasp:beat:last_scan"


def request_scan(application_id: uuid.UUID | str) -> None:
    """Event-driven scan after something changed (new facts, workflow transition)."""
    try:
        scan_application_task.delay(str(application_id))
    except OperationalError:
        log.exception("Could not enqueue monitoring scan for %s", application_id)


@celery_app.task(name="app.monitoring.scan_application")
def scan_application_task(application_id: str) -> None:
    with SessionLocal() as db:
        app = db.get(Application, uuid.UUID(application_id))
        if app is not None:
            scan_application(db, app, datetime.now(UTC))
            db.commit()


@celery_app.task(name="app.monitoring.scan_all")
def scan_all_task() -> dict[str, int]:
    """Scheduled scan (Celery beat): time passing is what makes certificates expire."""
    with SessionLocal() as db:
        result = scan_all(db, datetime.now(UTC))
        db.commit()
    redis.Redis.from_url(get_settings().redis_url).set(BEAT_HEARTBEAT_KEY, time.time())
    log.info("Monitoring scan: %s", vars(result))
    return vars(result)


@beat_init.connect
def scan_on_beat_start(**_) -> None:
    """Interval schedules first fire one interval after start; scan right away instead, so
    alerts and the beat heartbeat are fresh as soon as the stack is up."""
    scan_all_task.delay()
