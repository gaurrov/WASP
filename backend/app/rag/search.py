"""Hybrid retrieval over regulatory chunks: Postgres full-text + pgvector, fused with RRF.

Keyword search catches exact clause numbers and terms of art ("1:2:6", "NOC"); vector search
catches paraphrases. Reciprocal-rank fusion combines them without needing comparable scores.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import RegulatoryChunk, RegulatorySource
from app.models.enums import ProcessingStatus
from app.rag.embed import embed_query

CANDIDATES = 25
RRF_K = 60


@dataclass
class Hit:
    chunk: RegulatoryChunk
    source: RegulatorySource
    score: float
    matched_by: list[str]


def _base(on_date: date | None, source_id: uuid.UUID | None) -> Select:
    q = (
        select(RegulatoryChunk, RegulatorySource)
        .join(RegulatorySource, RegulatorySource.id == RegulatoryChunk.source_id)
        .where(RegulatorySource.ingest_status == ProcessingStatus.DONE)
    )
    if source_id:
        q = q.where(RegulatorySource.id == source_id)
    if on_date:
        # Only sources in force on that date; never silently apply a newer or older edition.
        q = q.where(
            or_(
                RegulatorySource.effective_from.is_(None),
                RegulatorySource.effective_from <= on_date,
            ),
            or_(RegulatorySource.effective_to.is_(None), RegulatorySource.effective_to >= on_date),
        )
    return q


def hybrid_search(
    db: Session,
    query: str,
    k: int = 5,
    on_date: date | None = None,
    source_id: uuid.UUID | None = None,
) -> list[Hit]:
    if not db.scalar(
        select(exists().where(RegulatorySource.ingest_status == ProcessingStatus.DONE))
    ):
        return []  # no handbook loaded: skip loading the embedding model entirely
    ranked: dict[uuid.UUID, Hit] = {}

    def add(rows, method: str) -> None:
        for rank, (chunk, source) in enumerate(rows):
            hit = ranked.setdefault(chunk.id, Hit(chunk, source, 0.0, []))
            hit.score += 1 / (RRF_K + rank + 1)
            hit.matched_by.append(method)

    tsquery = func.websearch_to_tsquery("english", query)
    add(
        db.execute(
            _base(on_date, source_id)
            .where(RegulatoryChunk.tsv.op("@@")(tsquery))
            .order_by(func.ts_rank_cd(RegulatoryChunk.tsv, tsquery).desc())
            .limit(CANDIDATES)
        ).all(),
        "keyword",
    )

    vector = embed_query(query)
    if vector is not None:
        add(
            db.execute(
                _base(on_date, source_id)
                .where(RegulatoryChunk.embedding.is_not(None))
                .order_by(RegulatoryChunk.embedding.cosine_distance(vector))
                .limit(CANDIDATES)
            ).all(),
            "semantic",
        )

    return sorted(ranked.values(), key=lambda h: h.score, reverse=True)[:k]
