from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery("wasp", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,  # re-deliver if a worker dies mid-task; tasks must be idempotent
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    # Separate queues so slow OCR never blocks alert delivery (see docs/PLAN.md).
    task_routes={
        "app.docintel.*": {"queue": "documents"},
        "app.monitoring.*": {"queue": "monitoring"},
    },
)


@celery_app.task(name="app.ping")
def ping() -> str:
    return "pong"
