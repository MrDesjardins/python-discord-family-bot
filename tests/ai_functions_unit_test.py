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

    def fake_get(guild_id, channel_ids):
        seen["args"] = (guild_id, channel_ids)
        return [(1, "mom", "hello", now, vector.tobytes())]

    monkeypatch.setattr(ai_functions, "get_embedded_messages_for_guild", fake_get)
    monkeypatch.setattr(ai_functions, "embed_text", lambda text: vector)

    context, used = ai_functions._build_context(1, "question", {10, 30})  # pylint: disable=protected-access

    assert seen["args"] == (1, {10, 30})
    assert used == 1
    assert "mom: hello" in context


def test_build_context_empty_visible_set_yields_no_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-closed: a member who can see no channels gets no archived context."""

    def fake_get(guild_id, channel_ids):  # pylint: disable=unused-argument
        assert channel_ids == set(), "retrieval must receive the empty visible set unchanged"
        return []

    monkeypatch.setattr(ai_functions, "get_embedded_messages_for_guild", fake_get)
    monkeypatch.setattr(ai_functions, "embed_text", lambda text: pytest.fail("must not embed with no rows"))

    assert ai_functions._build_context(1, "question", set()) == ("", 0)  # pylint: disable=protected-access
