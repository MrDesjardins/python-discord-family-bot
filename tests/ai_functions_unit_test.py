"""Unit tests for AI context building (data access and embedding model mocked)."""

import datetime

import numpy as np
import pytest

from deps.ai import ai_functions


def test_build_context_passes_visible_channels_to_data_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """The asker's visible-channel set reaches the data-access filter verbatim."""
    seen = {}
    now = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)
    vector = np.array([1.0, 0.0], dtype=np.float32)

    def fake_get(guild_id, channel_ids, target_channel_id=None, exclude_message_id=None):
        seen["args"] = (guild_id, channel_ids)
        seen["target_channel_id"] = target_channel_id
        seen["exclude_message_id"] = exclude_message_id
        return [(1, "mom", "hello", now, vector.tobytes())]

    def fake_search(guild_id, channel_ids, search_terms, **kwargs):
        seen.setdefault("searches", []).append((guild_id, channel_ids, search_terms, kwargs))
        if search_terms:
            return []
        return [(2, "dad", "latest retirement discussion", now, 10, "retirement-house")]

    monkeypatch.setattr(ai_functions, "get_embedded_messages_for_guild", fake_get)
    monkeypatch.setattr(ai_functions, "get_relevant_messages_for_guild", fake_search)
    monkeypatch.setattr(ai_functions, "embed_text", lambda text: vector)

    context, used = ai_functions._build_context(1, "question", {10, 30}, 10, 99)  # pylint: disable=protected-access

    assert seen["args"] == (1, {10, 30})
    assert seen["target_channel_id"] == 10
    assert seen["exclude_message_id"] == 99
    assert seen["searches"] == [
        (
            1,
            {10, 30},
            ["question"],
            {"target_channel_id": 10, "limit": 25, "exclude_message_id": 99},
        ),
        (1, {10, 30}, [], {"target_channel_id": 10, "limit": 16, "exclude_message_id": 99}),
    ]
    assert used == 2
    assert "mom: hello" in context
    assert "#unknown" in context
    assert "#retirement-house" in context


def test_build_context_prefers_exact_channel_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exact text matches in the asking channel are used without embedding dependency."""
    now = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)
    seen = {}

    def fake_search(guild_id, channel_ids, search_terms, **kwargs):
        seen.setdefault("args", []).append((guild_id, channel_ids, search_terms, kwargs))
        if search_terms:
            return [(42, "patrick", "Dover and Hooksett listings on Zillow and Redfin", now, 10, "retirement-house")]
        return []

    monkeypatch.setattr(ai_functions, "get_relevant_messages_for_guild", fake_search)
    monkeypatch.setattr(ai_functions, "get_embedded_messages_for_guild", lambda *args: [])
    monkeypatch.setattr(ai_functions, "embed_text", lambda _text: pytest.fail("exact matches need no embedding"))

    context, used = ai_functions._build_context(
        7, "top cities Zillow Redfin", {10, 30}, 10
    )  # pylint: disable=protected-access

    assert seen["args"] == [
        (
            7,
            {10, 30},
            ["cities", "zillow", "redfin"],
            {"target_channel_id": 10, "limit": 25, "exclude_message_id": None},
        ),
        (7, {10, 30}, [], {"target_channel_id": 10, "limit": 16, "exclude_message_id": None}),
    ]
    assert used == 1
    assert "#retirement-house" in context
    assert "Dover and Hooksett" in context


def test_build_context_empty_visible_set_yields_no_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-closed: a member who can see no channels gets no archived context."""

    def fake_get(guild_id, channel_ids):  # pylint: disable=unused-argument
        assert channel_ids == set(), "retrieval must receive the empty visible set unchanged"
        return []

    monkeypatch.setattr(ai_functions, "get_embedded_messages_for_guild", fake_get)
    monkeypatch.setattr(ai_functions, "embed_text", lambda text: pytest.fail("must not embed with no rows"))

    assert ai_functions._build_context(1, "question", set()) == ("", 0)  # pylint: disable=protected-access
