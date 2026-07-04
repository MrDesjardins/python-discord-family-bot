"""System test: calendar event CRUD on a file-based copy of a seeded DB."""

import datetime

from deps.calendar_data_access import (
    delete_past_events,
    delete_stale_events,
    get_all_events,
    get_events_in_range,
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


def test_get_events_in_range_selects_only_the_window(system_db):  # pylint: disable=unused-argument
    """get_events_in_range returns events whose start falls inside [start, end)."""
    base = datetime.datetime(2030, 5, 10, 12, 0, tzinfo=datetime.timezone.utc)
    for offset_hours, event_id in ((-2, "before"), (1, "inside"), (26, "after")):
        upsert_event(
            CalendarEvent(
                event_id=event_id,
                calendar_id="cal1",
                summary=event_id,
                description=None,
                location=None,
                start_utc=base + datetime.timedelta(hours=offset_hours),
                end_utc=None,
                html_link=None,
            )
        )
    window_start = base
    window_end = base + datetime.timedelta(hours=24)
    assert [e.event_id for e in get_events_in_range(window_start, window_end)] == ["inside"]


def test_delete_stale_events_prunes_only_missing_rows_in_window(system_db):  # pylint: disable=unused-argument
    """delete_stale_events removes in-window rows a sync no longer returned, nothing else."""
    base = datetime.datetime(2031, 3, 2, 8, 0, tzinfo=datetime.timezone.utc)
    for offset_hours, event_id in ((-3, "before-window"), (2, "kept"), (5, "moved-away"), (30, "after-window")):
        upsert_event(
            CalendarEvent(
                event_id=event_id,
                calendar_id="cal1",
                summary=event_id,
                description=None,
                location=None,
                start_utc=base + datetime.timedelta(hours=offset_hours),
                end_utc=None,
                html_link=None,
            )
        )

    # The sync window is [base, base+24h) and only 'kept' came back from Google.
    deleted = delete_stale_events(["kept"], base, base + datetime.timedelta(hours=24))
    assert deleted == 1
    remaining = {e.event_id for e in get_all_events()}
    assert "moved-away" not in remaining
    assert {"before-window", "kept", "after-window"} <= remaining

    # An empty sync result wipes the whole window.
    deleted = delete_stale_events([], base, base + datetime.timedelta(hours=24))
    assert deleted == 1
    assert "kept" not in {e.event_id for e in get_all_events()}
