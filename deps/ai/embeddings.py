"""Local, open-source message embeddings (sentence-transformers).

Vectors are stored as raw float32 bytes in SQLite. Retrieval combines semantic
similarity with a recency weight so that recent family chatter is favored.
"""

from __future__ import annotations

import datetime
import math
from typing import List, Optional, Tuple

import numpy as np

from deps.config import get_config
from deps.log import print_error_log, print_log

_model = None  # lazily loaded SentenceTransformer


def _get_model():
    """Load (once) and return the sentence-transformers model."""
    global _model  # pylint: disable=global-statement
    if _model is None:
        # Imported lazily: loading the model is expensive and only needed when AI is used.
        from sentence_transformers import SentenceTransformer  # pylint: disable=import-outside-toplevel

        model_name = get_config().ai.embedding_model
        print_log(f"embeddings: loading model {model_name}")
        _model = SentenceTransformer(model_name)
    return _model


def embed_text(text: str) -> np.ndarray:
    """Return a normalized float32 embedding vector for ``text``."""
    model = _get_model()
    vector = model.encode([text], normalize_embeddings=True)[0]
    return np.asarray(vector, dtype=np.float32)


def embed_texts(texts: List[str]) -> np.ndarray:
    """Return a (n, d) matrix of normalized float32 embeddings."""
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True)
    return np.asarray(vectors, dtype=np.float32)


def to_blob(vector: np.ndarray) -> bytes:
    """Serialize a vector to bytes for storage."""
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    """Deserialize bytes back into a float32 vector."""
    return np.frombuffer(blob, dtype=np.float32)


def _recency_weight(created_at: datetime.datetime, now: datetime.datetime, halflife_days: float) -> float:
    """Exponential decay in [0, 1]; halves every ``halflife_days``."""
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=datetime.timezone.utc)
    age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    return math.pow(0.5, age_days / halflife_days)


def rank_messages(
    query_vector: np.ndarray,
    rows: List[Tuple[int, str, str, datetime.datetime, bytes]],
    top_k: int,
    similarity_weight: float = 0.7,
    halflife_days: float = 14.0,
    now: Optional[datetime.datetime] = None,
) -> List[Tuple[int, str, str, datetime.datetime, float]]:
    """Rank ``rows`` by similarity * recency and return the top ``top_k``.

    ``rows`` are (message_id, author_name, content, created_at, embedding_blob).
    Returned tuples drop the blob and add the combined score.
    """
    if not rows:
        return []
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)

    try:
        matrix = np.vstack([from_blob(row[4]) for row in rows])
    except ValueError as exc:
        # Mismatched embedding dimensions (e.g. model changed). Skip retrieval gracefully.
        print_error_log(f"rank_messages: could not stack embeddings: {exc}")
        return []

    # Embeddings are normalized, so the dot product is cosine similarity in [-1, 1].
    cosine = matrix @ np.asarray(query_vector, dtype=np.float32)
    # Map to [0, 1] so it combines cleanly with the recency weight.
    similarities = (cosine + 1.0) / 2.0

    scored: List[Tuple[int, str, str, datetime.datetime, float]] = []
    for (message_id, author_name, content, created_at, _blob), sim in zip(rows, similarities):
        recency = _recency_weight(created_at, now, halflife_days)
        combined = similarity_weight * float(sim) + (1.0 - similarity_weight) * recency
        scored.append((message_id, author_name, content, created_at, combined))

    scored.sort(key=lambda item: item[4], reverse=True)
    return scored[:top_k]
