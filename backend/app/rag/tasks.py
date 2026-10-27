import logging
import uuid

from celery.signals import worker_process_init
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.db import SessionLocal
from app.docintel.text import extract_text
from app.models import RegulatoryChunk, RegulatorySource
from app.models.enums import ProcessingStatus
from app.rag.chunk import chunk_document
from app.rag.embed import embed_passages, embed_query
from app.storage import get_s3
from app.worker import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.rag.ingest_source")
def ingest_source(source_id: str) -> None:
    """Parse, chunk and embed a regulatory source. Idempotent: replaces existing chunks."""
    with SessionLocal() as db:
        source = db.get(RegulatorySource, uuid.UUID(source_id))
        if source is None:
            return
        source.ingest_status = ProcessingStatus.PROCESSING
        source.ingest_error = None
        db.commit()
        try:
            obj = get_s3().get_object(Bucket=get_settings().s3_bucket, Key=source.storage_key)
            chunks = chunk_document(extract_text(obj["Body"].read(), "application/pdf"))
            vectors = embed_passages(
                [f"{c.section or ''} {c.heading or ''}\n{c.text}".strip() for c in chunks]
            )
        except Exception as exc:
            log.exception("ingest_source failed for %s", source_id)
            db.rollback()
            source.ingest_status = ProcessingStatus.FAILED
            source.ingest_error = f"{type(exc).__name__}: {exc}"[:2000]
            db.commit()
            return

        db.execute(delete(RegulatoryChunk).where(RegulatoryChunk.source_id == source.id))
        db.add_all(
            RegulatoryChunk(
                source_id=source.id,
                section=c.section,
                heading=c.heading[:512] if c.heading else None,
                text=c.text,
                page=c.page,
                embedding=vectors[i] if vectors else None,
            )
            for i, c in enumerate(chunks)
        )
        db.flush()
        source.chunk_count = db.scalar(
            select(func.count()).where(RegulatoryChunk.source_id == source.id)
        )
        source.ingest_status = ProcessingStatus.DONE
        db.commit()
        log.info("Ingested %s: %d chunks", source.title, source.chunk_count)


@worker_process_init.connect
def warm_embedding_model(**_) -> None:
    """Load the model as each worker process starts (it takes ~30 s cold), so the first
    evaluation during a demo doesn't pay for it. Skipped when no handbook is loaded."""
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(RegulatorySource)):
            embed_query("warm up")
