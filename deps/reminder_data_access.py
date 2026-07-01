"""Data access for reminders."""

import datetime
from typing import List, Optional

from deps.database import database_manager
from deps.models import Reminder

SELECT_REMINDER = (
    "SELECT id, guild_id, channel_id, message_id, author_id, content, created_at, "
    "is_recurring, remind_time, remind_at, is_active, acknowledged, last_reminded_date FROM reminder"
)


def create_recurring_reminder(
    guild_id: int,
    channel_id: int,
    author_id: int,
    content: str,
    remind_time: str,
) -> int:
    """Create a daily reminder that repeats until the message is acknowledged."""
    cur = database_manager.get_cursor()
    cur.execute(
        """
        INSERT INTO reminder
            (guild_id, channel_id, author_id, content, created_at, is_recurring, remind_time, is_active)
        VALUES (?, ?, ?, ?, ?, 1, ?, 1)
        """,
        (guild_id, channel_id, author_id, content, datetime.datetime.now(datetime.timezone.utc), remind_time),
    )
    database_manager.get_conn().commit()
    return int(cur.lastrowid or 0)


def create_onetime_reminder(
    guild_id: int,
    channel_id: int,
    author_id: int,
    content: str,
    remind_at_utc: datetime.datetime,
) -> int:
    """Create a one-time reminder that fires once at ``remind_at_utc``."""
    cur = database_manager.get_cursor()
    cur.execute(
        """
        INSERT INTO reminder
            (guild_id, channel_id, author_id, content, created_at, is_recurring, remind_at, is_active)
        VALUES (?, ?, ?, ?, ?, 0, ?, 1)
        """,
        (guild_id, channel_id, author_id, content, datetime.datetime.now(datetime.timezone.utc), remind_at_utc),
    )
    database_manager.get_conn().commit()
    return int(cur.lastrowid or 0)


def set_reminder_message_id(reminder_id: int, message_id: int) -> None:
    """Attach the posted Discord message id (used for emoji acknowledgement)."""
    cur = database_manager.get_cursor()
    cur.execute("UPDATE reminder SET message_id = ? WHERE id = ?", (message_id, reminder_id))
    database_manager.get_conn().commit()


def get_active_reminders() -> List[Reminder]:
    """Return all active reminders across every guild."""
    cur = database_manager.get_cursor()
    cur.execute(f"{SELECT_REMINDER} WHERE is_active = 1")
    return [Reminder.from_db_row(row) for row in cur.fetchall()]


def get_active_reminders_for_guild(guild_id: int) -> List[Reminder]:
    """Return active reminders for one guild."""
    cur = database_manager.get_cursor()
    cur.execute(f"{SELECT_REMINDER} WHERE is_active = 1 AND guild_id = ?", (guild_id,))
    return [Reminder.from_db_row(row) for row in cur.fetchall()]


def get_reminder_by_message_id(message_id: int) -> Optional[Reminder]:
    """Look up a reminder by the Discord message that was posted for it."""
    cur = database_manager.get_cursor()
    cur.execute(f"{SELECT_REMINDER} WHERE message_id = ?", (message_id,))
    row = cur.fetchone()
    return Reminder.from_db_row(row) if row else None


def acknowledge_reminder(reminder_id: int) -> None:
    """Mark a recurring reminder acknowledged (an emoji was added) and stop it."""
    cur = database_manager.get_cursor()
    cur.execute("UPDATE reminder SET acknowledged = 1, is_active = 0 WHERE id = ?", (reminder_id,))
    database_manager.get_conn().commit()


def mark_recurring_reminded(reminder_id: int, date_str: str) -> None:
    """Record that a recurring reminder pinged on ``date_str`` (guild-local)."""
    cur = database_manager.get_cursor()
    cur.execute("UPDATE reminder SET last_reminded_date = ? WHERE id = ?", (date_str, reminder_id))
    database_manager.get_conn().commit()


def deactivate_reminder(reminder_id: int) -> None:
    """Deactivate a reminder (one-time fired, or cancelled)."""
    cur = database_manager.get_cursor()
    cur.execute("UPDATE reminder SET is_active = 0 WHERE id = ?", (reminder_id,))
    database_manager.get_conn().commit()
