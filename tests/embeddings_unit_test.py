"""Unit tests for the recency-weighted ranking math (no model load, no DB)."""

import datetime

import numpy as np

from deps.ai.embeddings import from_blob, rank_messages, to_blob


def test_blob_roundtrip():
    vector = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    assert np.allclose(from_blob(to_blob(vector)), vector)


def test_rank_prefers_similar_and_recent():
    now = datetime.datetime(2026, 6, 29, tzinfo=datetime.timezone.utc)
    query = np.array([1.0, 0.0], dtype=np.float32)
    rows = [
        (1, "mom", "relevant+recent", now - datetime.timedelta(days=1), to_blob(np.array([1.0, 0.0]))),
        (2, "dad", "relevant+old", now - datetime.timedelta(days=120), to_blob(np.array([1.0, 0.0]))),
        (3, "kid", "irrelevant+recent", now - datetime.timedelta(days=1), to_blob(np.array([0.0, 1.0]))),
    ]
    ranked = rank_messages(query, rows, top_k=3, now=now)
    assert ranked[0][0] == 1
    assert {r[0] for r in ranked} == {1, 2, 3}


def test_recency_weight_changes_order():
    now = datetime.datetime(2026, 6, 29, tzinfo=datetime.timezone.utc)
    query = np.array([1.0, 0.0], dtype=np.float32)
    # Two equally-similar messages; the more recent must rank first.
    rows = [
        (1, "a", "old", now - datetime.timedelta(days=60), to_blob(np.array([1.0, 0.0]))),
        (2, "b", "new", now - datetime.timedelta(hours=1), to_blob(np.array([1.0, 0.0]))),
    ]
    ranked = rank_messages(query, rows, top_k=2, similarity_weight=0.5, halflife_days=14.0, now=now)
    assert ranked[0][0] == 2


def test_top_k_limits_results():
    now = datetime.datetime(2026, 6, 29, tzinfo=datetime.timezone.utc)
    query = np.array([1.0, 0.0], dtype=np.float32)
    rows = [(i, "x", "m", now, to_blob(np.array([1.0, 0.0]))) for i in range(10)]
    assert len(rank_messages(query, rows, top_k=3, now=now)) == 3


def test_empty_rows_returns_empty():
    query = np.array([1.0, 0.0], dtype=np.float32)
    assert rank_messages(query, [], top_k=5) == []
