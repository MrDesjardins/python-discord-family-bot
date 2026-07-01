"""Data access for the ``bot_state`` key/value table (small cross-restart state)."""

from typing import Optional

from deps.database import database_manager

# Known state keys.
STATE_DAILY_SUMMARY_DATE = "daily_summary_last_date"  # "YYYY-MM-DD" (guild tz) last posted


def get_state(key: str) -> Optional[str]:
    """Return the stored value for ``key`` (or None if it was never set)."""
    cur = database_manager.get_cursor()
    cur.execute("SELECT value FROM bot_state WHERE key = ?", (key,))
    row = cur.fetchone()
    return row[0] if row else None


def set_state(key: str, value: str) -> None:
    """Insert or update the value for ``key``."""
    cur = database_manager.get_cursor()
    cur.execute(
        "INSERT INTO bot_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    database_manager.get_conn().commit()
