"""Data access for mirrored Google Calendar events."""

import datetime
from typing import List

from deps.database import database_manager
from deps.models import CalendarEvent

SELECT_CALENDAR_EVENT = (
    "SELECT event_id, calendar_id, summary, description, location, start_utc, end_utc, html_link, reminded "
    "FROM calendar_event"
)


def upsert_event(event: CalendarEvent) -> None:
    """Insert or update an event. Preserves the ``reminded`` flag on update.

    Start time changes reset ``reminded`` so a rescheduled event reminds again.
    """
    cur = database_manager.get_cursor()
    cur.execute("SELECT start_utc, reminded FROM calendar_event WHERE event_id = ?", (event.event_id,))
    existing = cur.fetchone()
    reminded = 0
    if existing is not None:
        prev_start = (
            existing[0] if isinstance(existing[0], datetime.datetime) else datetime.datetime.fromisoformat(existing[0])
        )
        if prev_start == event.start_utc:
            reminded = int(existing[1])  # unchanged time: keep prior reminded state
    cur.execute(
        """
        INSERT INTO calendar_event
            (event_id, calendar_id, summary, description, location, start_utc, end_utc, html_link, reminded, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            calendar_id = excluded.calendar_id,
            summary     = excluded.summary,
            description = excluded.description,
            location    = excluded.location,
            start_utc   = excluded.start_utc,
            end_utc     = excluded.end_utc,
            html_link   = excluded.html_link,
            reminded    = excluded.reminded,
            updated_at  = excluded.updated_at
        """,
        (
            event.event_id,
            event.calendar_id,
            event.summary,
            event.description,
            event.location,
            event.start_utc,
            event.end_utc,
            event.html_link,
            reminded,
            datetime.datetime.now(datetime.timezone.utc),
        ),
    )
    database_manager.get_conn().commit()


def get_events_needing_reminder(now_utc: datetime.datetime, lead_minutes: int) -> List[CalendarEvent]:
    """Return not-yet-reminded events starting within the next ``lead_minutes``.

    Events whose start has already passed are excluded (no point reminding late).
    """
    window_end = now_utc + datetime.timedelta(minutes=lead_minutes)
    cur = database_manager.get_cursor()
    cur.execute(
        f"{SELECT_CALENDAR_EVENT} WHERE reminded = 0 AND start_utc > ? AND start_utc <= ? ORDER BY start_utc",
        (now_utc, window_end),
    )
    return [CalendarEvent.from_db_row(row) for row in cur.fetchall()]


def get_events_in_range(start_utc: datetime.datetime, end_utc: datetime.datetime) -> List[CalendarEvent]:
    """Return events that start within ``[start_utc, end_utc)`` (used for the daily summary)."""
    cur = database_manager.get_cursor()
    cur.execute(
        f"{SELECT_CALENDAR_EVENT} WHERE start_utc >= ? AND start_utc < ? ORDER BY start_utc",
        (start_utc, end_utc),
    )
    return [CalendarEvent.from_db_row(row) for row in cur.fetchall()]


def mark_event_reminded(event_id: str) -> None:
    """Mark an event as reminded so it is not pinged again."""
    cur = database_manager.get_cursor()
    cur.execute("UPDATE calendar_event SET reminded = 1 WHERE event_id = ?", (event_id,))
    database_manager.get_conn().commit()


def get_all_events() -> List[CalendarEvent]:
    """Return every mirrored event (used by tests/inspection)."""
    cur = database_manager.get_cursor()
    cur.execute(f"{SELECT_CALENDAR_EVENT} ORDER BY start_utc")
    return [CalendarEvent.from_db_row(row) for row in cur.fetchall()]


def delete_past_events(before_utc: datetime.datetime) -> int:
    """Delete events that ended/started before ``before_utc``. Returns rows deleted."""
    cur = database_manager.get_cursor()
    cur.execute("DELETE FROM calendar_event WHERE start_utc < ?", (before_utc,))
    database_manager.get_conn().commit()
    return cur.rowcount
