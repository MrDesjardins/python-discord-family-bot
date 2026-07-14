"""Unit tests for the member channel-visibility helpers."""

import types

from deps.channel_visibility import archival_parent_channel_id, visible_channel_ids
from tests.discord_fakes import make_channel, make_guild, make_member, make_thread

MEMBER = make_member()


def test_visible_channel_included() -> None:
    guild = make_guild(channels=[make_channel(10)])
    assert visible_channel_ids(guild, MEMBER) == {10}


def test_hidden_channel_excluded() -> None:
    guild = make_guild(channels=[make_channel(10), make_channel(20, view=False)])
    assert visible_channel_ids(guild, MEMBER) == {10}


def test_view_without_history_excluded() -> None:
    guild = make_guild(channels=[make_channel(20, history=False)])
    assert visible_channel_ids(guild, MEMBER) == set()


def test_public_threads_follow_parent_permissions() -> None:
    guild = make_guild(
        channels=[make_channel(10)],
        threads=[make_thread(30, parent_id=10), make_thread(40, parent_id=20, view=False)],
    )
    assert visible_channel_ids(guild, MEMBER) == {10, 30}


def test_private_thread_excluded_for_non_member() -> None:
    """Parent visibility is NOT enough: discord.py's permissions_for ignores membership."""
    guild = make_guild(threads=[make_thread(30, parent_id=10, private=True, member_ids=[999])])
    assert visible_channel_ids(guild, MEMBER) == set()


def test_private_thread_included_for_thread_member() -> None:
    guild = make_guild(threads=[make_thread(30, parent_id=10, private=True, member_ids=[999, MEMBER.id])])
    assert visible_channel_ids(guild, MEMBER) == {30}


def test_private_thread_included_for_manage_threads() -> None:
    guild = make_guild(threads=[make_thread(30, parent_id=10, private=True, manage_threads=True)])
    assert visible_channel_ids(guild, MEMBER) == {30}


def test_channel_raising_is_skipped_others_kept() -> None:
    def _boom(_member):
        raise RuntimeError("partial member")

    broken = types.SimpleNamespace(id=50, permissions_for=_boom)
    guild = make_guild(channels=[broken, make_channel(10)])
    assert visible_channel_ids(guild, MEMBER) == {10}


def test_thread_missing_private_shape_is_skipped() -> None:
    """A thread whose private/membership attributes error out is excluded (fail-closed)."""
    perms = types.SimpleNamespace(view_channel=True, read_message_history=True, manage_threads=False)
    odd_thread = types.SimpleNamespace(id=30, permissions_for=lambda member: perms)  # no is_private
    guild = make_guild(threads=[odd_thread])
    assert visible_channel_ids(guild, MEMBER) == set()


def test_empty_guild_gives_empty_set() -> None:
    assert visible_channel_ids(make_guild(), MEMBER) == set()


def test_archival_parent_for_public_thread() -> None:
    assert archival_parent_channel_id(make_thread(30, parent_id=10)) == 10


def test_archival_parent_none_for_private_thread() -> None:
    assert archival_parent_channel_id(make_thread(30, parent_id=10, private=True)) is None


def test_archival_parent_none_for_regular_channel() -> None:
    assert archival_parent_channel_id(make_channel(10)) is None


def test_archival_parent_none_when_unclassifiable() -> None:
    """A thread-shaped object whose is_private() errors gets no parent inheritance."""
    odd = types.SimpleNamespace(id=30, parent_id=10)  # no is_private
    assert archival_parent_channel_id(odd) is None
