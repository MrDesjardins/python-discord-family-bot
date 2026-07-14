"""Data access for archived Discord messages used as AI context."""

import datetime
from typing import Collection, List, Optional, Tuple

from deps.channel_visibility import archival_parent_channel_id
from deps.database import database_manager


def store_message(
    message_id: int,
    guild_id: Optional[int],
    channel_id: int,
    channel_name: Optional[str],
    author_id: int,
    author_name: Optional[str],
    content: str,
    created_at: datetime.datetime,
    parent_channel_id: Optional[int] = None,
) -> None:
    """Insert a message (idempotent on message_id). Embedding is filled in later.

    ``parent_channel_id`` is set for messages posted in a PUBLIC thread (see
    ``deps.channel_visibility.archival_parent_channel_id``) so retrieval can grant
    visibility via the parent channel even after the thread auto-archives.
    """
    if not content.strip():
        return
    cur = database_manager.get_cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO message
            (message_id, guild_id, channel_id, channel_name, author_id, author_name,
             content, created_at, parent_channel_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message_id,
            guild_id,
            channel_id,
            channel_name,
            author_id,
            author_name,
            content,
            created_at,
            parent_channel_id,
        ),
    )
    database_manager.get_conn().commit()


def archive_bot_message(message: object, guild_id: int) -> None:
    """Archive a message the bot itself posted (calendar reminder / reminder ping).

    Accepts anything with the discord.Message shape (``id``, ``channel``, ``author``,
    ``content``, ``created_at``) so the data-access layer stays free of a discord import
    and this stays unit-testable with a plain stand-in object. Routes through
    ``store_message`` so it shares the same idempotency and embedding pipeline as live
    archiving. Only the bot's *structured* posts are archived this way — AI mention
    replies and other bots are intentionally left out to avoid an AI echo chamber.
    """
    channel = message.channel  # type: ignore[attr-defined]
    author = message.author  # type: ignore[attr-defined]
    store_message(
        message_id=message.id,  # type: ignore[attr-defined]
        guild_id=guild_id,
        channel_id=channel.id,
        channel_name=getattr(channel, "name", None),
        author_id=author.id,
        author_name=getattr(author, "display_name", None),
        content=message.content or "",  # type: ignore[attr-defined]
        created_at=message.created_at,  # type: ignore[attr-defined]
        parent_channel_id=archival_parent_channel_id(channel),
    )


def get_messages_without_embedding(limit: int = 200) -> List[Tuple[int, str]]:
    """Return (message_id, content) for messages that still need an embedding."""
    cur = database_manager.get_cursor()
    cur.execute(
        "SELECT message_id, content FROM message WHERE embedding IS NULL ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    return [(row[0], row[1]) for row in cur.fetchall()]


def set_message_embedding(message_id: int, embedding_blob: bytes) -> None:
    """Store the float32 embedding bytes for a message."""
    cur = database_manager.get_cursor()
    cur.execute("UPDATE message SET embedding = ? WHERE message_id = ?", (embedding_blob, message_id))
    database_manager.get_conn().commit()


def get_embedded_messages_for_guild(
    guild_id: int,
    channel_ids: Collection[int],
) -> List[Tuple[int, str, str, datetime.datetime, bytes]]:
    """Return (message_id, author_name, content, created_at, embedding) for a guild.

    Only messages from ``channel_ids`` are returned — this is the permission filter
    for AI context (callers pass the asking member's visible channels, see
    ``deps/channel_visibility.py``). A message matches on its own channel id or on
    its ``parent_channel_id`` (set for public-thread messages, so they stay visible
    via the parent channel even after the thread auto-archives). An empty collection
    returns no rows (fail-closed).
    """
    if not channel_ids:
        return []
    ids = tuple(channel_ids)
    cur = database_manager.get_cursor()
    placeholders = ",".join("?" for _ in ids)
    cur.execute(
        f"""
        SELECT message_id, author_name, content, created_at, embedding
        FROM message
        WHERE guild_id = ? AND embedding IS NOT NULL
          AND (channel_id IN ({placeholders}) OR parent_channel_id IN ({placeholders}))
        """,
        (guild_id, *ids, *ids),
    )
    results: List[Tuple[int, str, str, datetime.datetime, bytes]] = []
    for row in cur.fetchall():
        created = row[3] if isinstance(row[3], datetime.datetime) else datetime.datetime.fromisoformat(row[3])
        results.append((row[0], row[1] or "unknown", row[2], created, row[4]))
    return results
