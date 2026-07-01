"""Data access for archived Discord messages used as AI context."""

import datetime
from typing import List, Optional, Tuple

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
) -> None:
    """Insert a message (idempotent on message_id). Embedding is filled in later."""
    if not content.strip():
        return
    cur = database_manager.get_cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO message
            (message_id, guild_id, channel_id, channel_name, author_id, author_name, content, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (message_id, guild_id, channel_id, channel_name, author_id, author_name, content, created_at),
    )
    database_manager.get_conn().commit()


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
) -> List[Tuple[int, str, str, datetime.datetime, bytes]]:
    """Return (message_id, author_name, content, created_at, embedding) for a guild."""
    cur = database_manager.get_cursor()
    cur.execute(
        """
        SELECT message_id, author_name, content, created_at, embedding
        FROM message
        WHERE guild_id = ? AND embedding IS NOT NULL
        """,
        (guild_id,),
    )
    results: List[Tuple[int, str, str, datetime.datetime, bytes]] = []
    for row in cur.fetchall():
        created = row[3] if isinstance(row[3], datetime.datetime) else datetime.datetime.fromisoformat(row[3])
        results.append((row[0], row[1] or "unknown", row[2], created, row[4]))
    return results
