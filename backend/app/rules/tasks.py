import logging
import uuid

from kombu.exceptions import OperationalError
from sqlalchemy import select

from app.audit import record_event
from app.db import SessionLocal
from app.models import Application, Document
from app.models.enums import ApplicationStatus, FindingStatus, ProcessingStatus
from app.rules.engine import evaluate
from app.worker import celery_app

log = logging.getLogger(__name__)

EVALUABLE = {
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.PROCESSING,
    ApplicationStatus.NEEDS_REVIEW,
    ApplicationStatus.READY_FOR_DECISION,
}
CLEAN = {FindingStatus.PASS, FindingStatus.NOT_APPLICABLE}


def enqueue_evaluation(application_id: uuid.UUID) -> None:
    try:
        evaluate_application.delay(str(application_id))
    except OperationalError:
        log.exception("Could not enqueue evaluation for %s", application_id)


@celery_app.task(bind=True, name="app.rules.evaluate_application", max_retries=200)
def evaluate_application(self, application_id: str) -> None:
    with SessionLocal() as db:
        application = db.get(Application, uuid.UUID(application_id))
        if application is None or application.status not in EVALUABLE:
            return
        pending = db.scalar(
            select(Document.id).where(
                Document.application_id == application.id,
                Document.is_current,
                Document.processing_status.in_(
                    [ProcessingStatus.PENDING, ProcessingStatus.PROCESSING]
                ),
            )
        )
        if pending is not None:  # rules need extracted facts; wait for the documents
            if application.status != ApplicationStatus.PROCESSING:
                application.status = ApplicationStatus.PROCESSING
                db.commit()
            raise self.retry(countdown=3)

        findings = evaluate(db, application)
        previous = application.status
        clean = all(f.status in CLEAN for f in findings)
        application.status = (
            ApplicationStatus.READY_FOR_DECISION if clean else ApplicationStatus.NEEDS_REVIEW
        )
        record_event(
            db,
            "application_evaluated",
            application_id=application.id,
            from_status=previous,
            to_status=application.status,
            findings={s.value: sum(f.status == s for f in findings) for s in FindingStatus},
        )
        db.commit()
