import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ReviewDecision


def latest_reviews(db: Session, finding_ids: list[uuid.UUID]) -> dict[uuid.UUID, ReviewDecision]:
    latest: dict[uuid.UUID, ReviewDecision] = {}
    for r in db.scalars(
        select(ReviewDecision)
        .where(ReviewDecision.finding_id.in_(finding_ids))
        .order_by(ReviewDecision.created_at)
    ):
        latest[r.finding_id] = r
    return latest
