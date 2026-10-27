from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery("wasp", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    include=["app.docintel.tasks", "app.rag.tasks", "app.workflow.tasks", "app.monitoring.tasks"],
    # Tests run tasks inline so the whole upload → extraction path is exercised synchronously.
    task_always_eager=settings.celery_eager,
    task_eager_propagates=True,
    task_acks_late=True,  # re-deliver if a worker dies mid-task; tasks must be idempotent
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    # Separate queues so slow OCR never blocks alert delivery (see docs/PLAN.md).
    task_routes={
        "app.docintel.*": {"queue": "documents"},
        "app.rag.*": {"queue": "documents"},
        "app.monitoring.*": {"queue": "monitoring"},
    },
    # Run by the `beat` service. Time passing is what makes certificates expire.
    beat_schedule={
        "monitoring-scan": {
            "task": "app.monitoring.scan_all",
            "schedule": settings.monitoring_interval_seconds,
        }
    },
)


@celery_app.task(name="app.ping")
def ping() -> str:
    return "pong"
