"""Compute which channels a member can see, for permission-aware AI retrieval.

Accepts duck-typed guild/member/channel objects (anything with the discord.py shape)
so this module stays free of a discord import and unit-testable with plain stand-in
objects, following the ``archive_bot_message`` precedent in
``deps/message_data_access.py``.

Thread semantics (discord.py resolves ``Thread.permissions_for`` from the PARENT
channel only — it never checks private-thread membership, so this module must):

- A **public thread** is readable by whoever can read its parent channel, even after
  it auto-archives. Messages archived from one carry ``parent_channel_id`` (see
  ``archival_parent_channel_id``), so retrieval can match on the parent and survives
  the thread dropping out of the ``guild.threads`` cache.
- A **private thread** is readable only by its members and ``manage_threads`` holders.
  It never inherits parent visibility; once uncached it is excluded for everyone
  (fail-closed).
"""

from typing import Any, Optional, Set

from deps.log import print_warning_log


def visible_channel_ids(guild: Any, member: Any) -> Set[int]:
    """Return the ids of channels and threads ``member`` can read history in.

    A channel counts as visible only when ``permissions_for(member)`` grants both
    ``view_channel`` and ``read_message_history`` — Discord requires both to read a
    channel's past messages, which is exactly what the archived AI context is.
    Administrators pass automatically via permission resolution. A private thread
    additionally requires actual thread membership or ``manage_threads``.

    Any channel whose check errors is skipped (fail-closed): an exception can only
    shrink the visible set, never widen it.
    """
    ids: Set[int] = set()
    for channel in guild.channels:
        try:
            perms = channel.permissions_for(member)
            if perms.view_channel and perms.read_message_history:
                ids.add(channel.id)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print_warning_log(f"visible_channel_ids: skipping channel {getattr(channel, 'id', '?')}: {exc}")
    for thread in guild.threads:
        try:
            perms = thread.permissions_for(member)
            if not (perms.view_channel and perms.read_message_history):
                continue
            if thread.is_private() and not perms.manage_threads:
                if not any(thread_member.id == member.id for thread_member in thread.members):
                    continue
            ids.add(thread.id)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print_warning_log(f"visible_channel_ids: skipping thread {getattr(thread, 'id', '?')}: {exc}")
    return ids


def archival_parent_channel_id(channel: Any) -> Optional[int]:
    """Return the parent channel id to store with a message archived from ``channel``.

    Only a PUBLIC thread inherits its parent channel's visibility, so only then is
    the parent id returned; retrieval then matches the message for anyone who can
    read the parent, even after the thread auto-archives. Returns None for regular
    channels (their own id is the visibility key), for private threads (they must
    never be readable via the parent), and for unrecognizable objects (fail-closed).
    """
    parent_id = getattr(channel, "parent_id", None)
    if parent_id is None:
        return None
    try:
        if channel.is_private():
            return None
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print_warning_log(f"archival_parent_channel_id: cannot classify {getattr(channel, 'id', '?')}: {exc}")
        return None
    return int(parent_id)
