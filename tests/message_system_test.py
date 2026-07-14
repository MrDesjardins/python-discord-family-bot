"""System test: message archive + embedding storage on a copied DB."""

import datetime
import types

import numpy as np

from deps.ai.embeddings import from_blob, to_blob
from deps.message_data_access import (
    archive_bot_message,
    get_embedded_messages_for_guild,
    get_messages_without_embedding,
    set_message_embedding,
    store_message,
)


def test_message_archive_and_embedding_crud(system_db):  # pylint: disable=unused-argument
    """Store messages, backfill embeddings, and read them back via real SQL."""
    now = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)

    store_message(1, 1, 10, "general", 100, "mom", "we should plan a trip", now)
    store_message(2, 1, 10, "general", 101, "dad", "great idea", now)
    # Idempotent: storing the same message id again does not duplicate.
    store_message(1, 1, 10, "general", 100, "mom", "we should plan a trip", now)
    # Empty content is skipped.
    store_message(3, 1, 10, "general", 102, "kid", "   ", now)

    pending = get_messages_without_embedding()
    assert {mid for mid, _ in pending} == {1, 2}

    for message_id, _content in pending:
        set_message_embedding(message_id, to_blob(np.array([0.1, 0.2, 0.3], dtype=np.float32)))

    assert get_messages_without_embedding() == []

    rows = get_embedded_messages_for_guild(1, {10})
    assert len(rows) == 2
    # Embedding round-trips through the database blob column.
    _mid, _author, _content, _created, blob = rows[0]
    assert np.allclose(from_blob(blob), np.array([0.1, 0.2, 0.3], dtype=np.float32))


def test_archive_bot_message_stores_calendar_and_reminder_posts(system_db):  # pylint: disable=unused-argument
    """A bot-posted message (discord.Message-shaped stand-in) is archived like any other."""
    now = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)
    fake_message = types.SimpleNamespace(
        id=900,
        content="📅 In 30 min: Dentist",
        created_at=now,
        channel=types.SimpleNamespace(id=10, name="calendar"),
        author=types.SimpleNamespace(id=999, display_name="FamilyBot"),
    )

    archive_bot_message(fake_message, guild_id=1)

    pending = get_messages_without_embedding()
    assert 900 in {mid for mid, _ in pending}
    set_message_embedding(900, to_blob(np.array([0.4, 0.5, 0.6], dtype=np.float32)))

    rows = {
        mid: (author, content) for mid, author, content, _created, _blob in get_embedded_messages_for_guild(1, {10})
    }
    assert rows[900] == ("FamilyBot", "📅 In 30 min: Dentist")


def test_get_embedded_messages_filters_by_channel(system_db):  # pylint: disable=unused-argument
    """Retrieval only returns messages from the given channels; empty set returns nothing."""
    now = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)
    store_message(1, 1, 10, "general", 100, "mom", "open to everyone", now)
    store_message(2, 1, 20, "parents-only", 101, "dad", "secret gift plans", now)
    for message_id, _content in get_messages_without_embedding():
        set_message_embedding(message_id, to_blob(np.array([0.1, 0.2, 0.3], dtype=np.float32)))

    assert {mid for mid, *_ in get_embedded_messages_for_guild(1, {10})} == {1}
    assert {mid for mid, *_ in get_embedded_messages_for_guild(1, {10, 20})} == {1, 2}
    assert get_embedded_messages_for_guild(1, set()) == []


def test_get_embedded_messages_matches_parent_channel(system_db):  # pylint: disable=unused-argument
    """A public-thread message (parent_channel_id set) is retrievable via the parent
    channel id even when the thread id itself is not in the visible set; a private
    thread message (parent NULL) is only reachable via its own thread id."""
    now = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)
    store_message(1, 1, 30, "trip-plans", 100, "mom", "camping this summer", now, parent_channel_id=10)
    store_message(2, 1, 40, "gift-plans", 101, "dad", "secret gift plans", now, parent_channel_id=None)
    for message_id, _content in get_messages_without_embedding():
        set_message_embedding(message_id, to_blob(np.array([0.1, 0.2, 0.3], dtype=np.float32)))

    # Parent channel visible, neither thread id in the set: public thread matches via parent.
    assert {mid for mid, *_ in get_embedded_messages_for_guild(1, {10})} == {1}
    # Private thread reachable only by members whose set contains the thread id itself.
    assert {mid for mid, *_ in get_embedded_messages_for_guild(1, {10, 40})} == {1, 2}
