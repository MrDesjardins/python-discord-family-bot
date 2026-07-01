"""System test: calendar event CRUD on a file-based copy of a seeded DB."""

import datetime

from deps.calendar_data_access import (
    delete_past_events,
    get_all_events,
    get_events_needing_reminder,
    mark_event_reminded,
    upsert_event,
)
from deps.models import CalendarEvent


def test_calendar_crud_on_seeded_copy(system_db):
    """INSERT, UPDATE and DELETE of calendar events against a real copied database."""
    # Seed contains one event ('seed-evt').
    assert {e.event_id for e in get_all_events()} == {"seed-evt"}

    now = datetime.datetime.now(datetime.timezone.utc)
    # INSERT a new near-term event.
    upsert_event(
        CalendarEvent(
            event_id="evt-new",
            calendar_id="cal1",
            summary="Soon",
            description=None,
            location="Home",
            start_utc=now + datetime.timedelta(minutes=10),
            end_utc=now + datetime.timedelta(minutes=40),
            html_link=None,
        )
    )
    assert {e.event_id for e in get_all_events()} == {"seed-evt", "evt-new"}

    # UPDATE: marking reminded persists.
    assert [e.event_id for e in get_events_needing_reminder(now, 30)] == ["evt-new"]
    mark_event_reminded("evt-new")
    cur = system_db.get_cursor()
    cur.execute("SELECT reminded FROM calendar_event WHERE event_id = 'evt-new'")
    assert cur.fetchone()[0] == 1

    # DELETE: purge events older than now (the seed event is 1 day in the future, so add a past one).
    upsert_event(
        CalendarEvent(
            event_id="evt-past",
            calendar_id="cal1",
            summary="Past",
            description=None,
            location=None,
            start_utc=now - datetime.timedelta(days=2),
            end_utc=None,
            html_link=None,
        )
    )
    deleted = delete_past_events(now - datetime.timedelta(days=1))
    assert deleted == 1
    assert "evt-past" not in {e.event_id for e in get_all_events()}
