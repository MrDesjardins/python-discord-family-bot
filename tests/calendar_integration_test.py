"""Integration test: Google fetch (mocked) -> upsert -> reminder selection -> mark."""

import datetime

from deps.calendar_data_access import (
    delete_stale_events,
    get_events_in_range,
    get_events_needing_reminder,
    mark_event_reminded,
    upsert_event,
)
from deps.google_calendar import fetch_upcoming_events
from tests.google_calendar_unit_test import _FakeService


def test_calendar_pipeline_end_to_end(db):  # pylint: disable=unused-argument
    """Fetch events via a fake service, store them, and find the one that is due."""
    now = datetime.datetime.now(datetime.timezone.utc)
    soon = now + datetime.timedelta(minutes=20)  # within a 30-min lead window
    later = now + datetime.timedelta(hours=5)  # outside the window

    service = _FakeService(
        events={
            "items": [
                {"id": "soon", "summary": "Soon", "start": {"dateTime": soon.isoformat()}},
                {"id": "later", "summary": "Later", "start": {"dateTime": later.isoformat()}},
            ]
        }
    )

    events = fetch_upcoming_events("cal1", lookahead_hours=48, service=service)
    for event in events:
        upsert_event(event)

    due = get_events_needing_reminder(now, lead_minutes=30)
    assert [e.event_id for e in due] == ["soon"]

    # After reminding, it is no longer returned.
    mark_event_reminded("soon")
    assert get_events_needing_reminder(now, lead_minutes=30) == []


def test_upsert_preserves_reminded_until_time_changes(db):  # pylint: disable=unused-argument
    """Re-syncing the same event keeps reminded; a new start time resets it."""
    now = datetime.datetime.now(datetime.timezone.utc)
    start = now + datetime.timedelta(minutes=10)

    service = _FakeService(events={"items": [{"id": "e", "summary": "E", "start": {"dateTime": start.isoformat()}}]})
    (event,) = fetch_upcoming_events("cal1", lookahead_hours=48, service=service)
    upsert_event(event)
    mark_event_reminded("e")

    # Same time again -> still reminded (not returned).
    upsert_event(event)
    assert get_events_needing_reminder(now, lead_minutes=30) == []

    # New time -> reminded reset, event is due again.
    event.start_utc = now + datetime.timedelta(minutes=15)
    upsert_event(event)
    assert [e.event_id for e in get_events_needing_reminder(now, lead_minutes=30)] == ["e"]


def test_resync_prunes_event_moved_out_of_window(db):  # pylint: disable=unused-argument
    """An event moved beyond the lookahead window disappears from the mirror on re-sync.

    Regression test: the daily summary once listed an event that had been moved to a
    later day because the sync only upserted and never deleted the stale local row.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    window_end = now + datetime.timedelta(hours=48)
    today_event = {
        "id": "party",
        "summary": "Party",
        "start": {"dateTime": (now + datetime.timedelta(hours=3)).isoformat()},
    }
    other_event = {
        "id": "dinner",
        "summary": "Dinner",
        "start": {"dateTime": (now + datetime.timedelta(hours=6)).isoformat()},
    }

    def sync(service_events):
        """Mirror poll_loop: fetch with a pinned now, upsert, then prune the window."""
        service = _FakeService(events={"items": service_events})
        events = fetch_upcoming_events("cal1", lookahead_hours=48, service=service, now=now)
        for event in events:
            upsert_event(event)
        delete_stale_events([e.event_id for e in events], now, window_end)

    sync([today_event, other_event])
    assert {e.event_id for e in get_events_in_range(now, window_end)} == {"party", "dinner"}

    # 'party' is moved days ahead: Google stops returning it within the window.
    sync([other_event])
    assert {e.event_id for e in get_events_in_range(now, window_end)} == {"dinner"}
