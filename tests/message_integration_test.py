"""Integration test: channel visibility + message data access filter together."""

import datetime

import numpy as np

from deps.ai.embeddings import to_blob
from deps.channel_visibility import archival_parent_channel_id, visible_channel_ids
from deps.message_data_access import (
    get_embedded_messages_for_guild,
    get_messages_without_embedding,
    set_message_embedding,
    store_message,
)
from tests.discord_fakes import make_channel, make_guild, make_member, make_thread

NOW = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)


def _embed_all() -> None:
    for message_id, _content in get_messages_without_embedding():
        set_message_embedding(message_id, to_blob(np.array([0.1, 0.2], dtype=np.float32)))


def test_ai_retrieval_respects_member_visibility(db):  # pylint: disable=unused-argument
    """A member only retrieves archived messages from channels they can see."""
    guild = make_guild(channels=[make_channel(10), make_channel(20, view=False)])
    member = make_member()

    store_message(1, 1, 10, "general", 100, "mom", "pizza night on friday", NOW)
    store_message(2, 1, 20, "parents-only", 101, "dad", "birthday surprise details", NOW)
    _embed_all()

    visible = visible_channel_ids(guild, member)
    assert visible == {10}

    rows = get_embedded_messages_for_guild(1, visible)
    assert [(mid, content) for mid, _author, content, _created, _blob in rows] == [(1, "pizza night on friday")]


def test_public_thread_messages_survive_thread_archival(db):  # pylint: disable=unused-argument
    """A public thread's messages stay retrievable via the parent channel once the
    thread has auto-archived (gone from guild.threads), because archiving stored
    the parent channel id."""
    thread = make_thread(30, parent_id=10)
    store_message(1, 1, 30, "trip-plans", 100, "mom", "let's go camping", NOW, archival_parent_channel_id(thread))
    _embed_all()

    # Thread no longer in guild.threads (auto-archived) — parent channel still visible.
    guild = make_guild(channels=[make_channel(10)])
    visible = visible_channel_ids(guild, make_member())
    assert visible == {10}

    assert [mid for mid, *_ in get_embedded_messages_for_guild(1, visible)] == [1]


def test_private_thread_messages_hidden_from_non_members(db):  # pylint: disable=unused-argument
    """A private thread's messages never inherit parent visibility: a member who can
    see the parent channel but is not in the thread retrieves nothing from it."""
    private_thread = make_thread(30, parent_id=10, private=True, member_ids=[101])
    store_message(
        1, 1, 30, "gift-plans", 101, "dad", "secret gift plans", NOW, archival_parent_channel_id(private_thread)
    )
    _embed_all()

    guild = make_guild(channels=[make_channel(10)], threads=[private_thread])

    kid_visible = visible_channel_ids(guild, make_member(100, "kid"))
    assert kid_visible == {10}
    assert get_embedded_messages_for_guild(1, kid_visible) == []

    dad_visible = visible_channel_ids(guild, make_member(101, "dad"))
    assert dad_visible == {10, 30}
    assert [mid for mid, *_ in get_embedded_messages_for_guild(1, dad_visible)] == [1]
