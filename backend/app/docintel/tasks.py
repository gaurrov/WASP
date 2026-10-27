import logging
import uuid
from datetime import UTC, datetime

from kombu.exceptions import OperationalError
from sqlalchemy import delete

from app.audit import record_event
from app.config import get_settings
from app.db import SessionLocal
from app.docintel.pipeline import EXTRACTOR_NAME, process
from app.models import Document, ExtractedFact
from app.models.enums import ApplicationStatus, ProcessingStatus
from app.rules.tasks import enqueue_evaluation
from app.storage import get_s3
from app.worker import celery_app

log = logging.getLogger(__name__)


def enqueue_processing(document_id: uuid.UUID) -> None:
    """Queue extraction. A broker outage must not fail the upload: the document stays
    `pending` and can be retried via the reprocess endpoint."""
    try:
        process_document.delay(str(document_id))
    except OperationalError:  # broker unreachable
        log.exception("Could not enqueue processing for %s", document_id)


@celery_app.task(name="app.docintel.process_document")
def process_document(document_id: str) -> None:
    """Idempotent: re-running replaces this document's facts rather than duplicating them."""
    with SessionLocal() as db:
        document = db.get(Document, uuid.UUID(document_id))
        if document is None:
            log.warning("process_document: %s not found", document_id)
            return
        document.processing_status = ProcessingStatus.PROCESSING
        document.processing_error = None
        db.commit()

        try:
            obj = get_s3().get_object(Bucket=get_settings().s3_bucket, Key=document.storage_key)
            result = process(obj["Body"].read(), document.mime_type, document.doc_type)
        except Exception as exc:
            log.exception("process_document failed for %s", document_id)
            db.rollback()
            document.processing_status = ProcessingStatus.FAILED
            document.processing_error = f"{type(exc).__name__}: {exc}"[:2000]
            db.commit()
            return

        db.execute(delete(ExtractedFact).where(ExtractedFact.document_id == document.id))
        db.add_all(
            ExtractedFact(
                document_id=document.id,
                application_id=document.application_id,
                field_name=f.name,
                value=f.value,
                raw_text=f.raw,
                confidence=f.confidence,
                page=f.page,
                bbox=list(f.bbox) if f.bbox else None,
                extractor=EXTRACTOR_NAME + ("+ocr" if result.text.ocr_used else ""),
            )
            for f in result.fields
        )
        document.detected_doc_type = result.detected_type
        document.detection_confidence = result.detection_confidence
        document.ocr_used = result.text.ocr_used
        document.pages = result.pages
        document.page_count = len(result.pages)
        document.processing_status = ProcessingStatus.DONE
        document.processed_at = datetime.now(UTC)
        record_event(
            db,
            "document_processed",
            application_id=document.application_id,
            document_id=document_id,
            facts=len(result.fields),
            detected_doc_type=result.detected_type.value,
            ocr_used=result.text.ocr_used,
        )
        db.commit()
        # Facts changed, so findings for an application under review are stale.
        if document.application.status != ApplicationStatus.DRAFT:
            enqueue_evaluation(document.application_id)
