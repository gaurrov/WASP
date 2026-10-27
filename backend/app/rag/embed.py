"""Local text embeddings (fastembed / ONNX). Optional: retrieval falls back to full-text search
when the model can't be loaded (e.g. first run offline), so the system degrades, not breaks."""

import logging
from functools import lru_cache

from app.config import get_settings

log = logging.getLogger(__name__)

# bge models are trained with this prefix on queries (not on passages).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache
def _model():
    settings = get_settings()
    try:
        from fastembed import TextEmbedding

        return TextEmbedding(settings.embedding_model, cache_dir=settings.model_cache_dir)
    except Exception:
        log.exception("Embedding model unavailable; using full-text search only")
        return None


def embed_passages(texts: list[str]) -> list[list[float]] | None:
    model = _model()
    if model is None or not texts:
        return None
    return [v.tolist() for v in model.embed(texts, batch_size=32)]


def embed_query(text: str) -> list[float] | None:
    model = _model()
    if model is None:
        return None
    return next(iter(model.embed([QUERY_PREFIX + text]))).tolist()
