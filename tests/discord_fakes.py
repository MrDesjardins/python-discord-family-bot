"""Shared discord.py-shaped stand-ins for unit/integration tests.

``deps/channel_visibility.py`` is deliberately duck-typed, so tests fake guilds,
channels, threads, and members with SimpleNamespace. Keep all those builders here
so the fake permission shape cannot drift between test files.
"""

import types
from typing import Iterable


def make_member(member_id: int = 100, display_name: str = "kid") -> types.SimpleNamespace:
    """A member-shaped object (only ``id``/``display_name`` are needed by the code under test)."""
    return types.SimpleNamespace(id=member_id, display_name=display_name)


def make_channel(channel_id: int, view: bool = True, history: bool = True) -> types.SimpleNamespace:
    """A guild-channel-shaped object with fixed permissions for any member."""
    perms = types.SimpleNamespace(view_channel=view, read_message_history=history, manage_threads=False)
    return types.SimpleNamespace(id=channel_id, permissions_for=lambda member: perms)


def make_thread(
    thread_id: int,
    parent_id: int,
    view: bool = True,
    history: bool = True,
    private: bool = False,
    member_ids: Iterable[int] = (),
    manage_threads: bool = False,
) -> types.SimpleNamespace:
    """A thread-shaped object: parent-derived permissions plus private-thread membership."""
    perms = types.SimpleNamespace(view_channel=view, read_message_history=history, manage_threads=manage_threads)
    return types.SimpleNamespace(
        id=thread_id,
        parent_id=parent_id,
        permissions_for=lambda member: perms,
        is_private=lambda: private,
        members=[types.SimpleNamespace(id=mid) for mid in member_ids],
    )


def make_guild(channels: Iterable = (), threads: Iterable = ()) -> types.SimpleNamespace:
    """A guild-shaped object exposing ``channels`` and ``threads``."""
    return types.SimpleNamespace(channels=list(channels), threads=list(threads))
