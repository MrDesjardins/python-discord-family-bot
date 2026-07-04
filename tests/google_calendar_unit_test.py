"""Unit tests for Google Calendar parsing/lookup using a fake service (no network)."""

import datetime

from deps.google_calendar import (
    _parse_event_datetime,
    fetch_upcoming_events,
    find_calendar_id_by_name,
    normalize_event,
)


def test_parse_timed_event_to_utc():
    dt = _parse_event_datetime({"dateTime": "2026-07-01T09:00:00-07:00"})
    assert dt == datetime.datetime(2026, 7, 1, 16, 0, tzinfo=datetime.timezone.utc)


def test_parse_all_day_event():
    dt = _parse_event_datetime({"date": "2026-07-04"})
    assert dt == datetime.datetime(2026, 7, 4, 0, 0, tzinfo=datetime.timezone.utc)


def test_normalize_event_fields():
    event = normalize_event(
        {
            "id": "evt1",
            "summary": "Standup",
            "description": "daily",
            "location": "Zoom",
            "start": {"dateTime": "2026-07-01T09:00:00+00:00"},
            "end": {"dateTime": "2026-07-01T09:30:00+00:00"},
            "htmlLink": "http://example/evt1",
        },
        "cal1",
    )
    assert event is not None
    assert event.event_id == "evt1"
    assert event.summary == "Standup"
    assert event.location == "Zoom"
    assert event.start_utc.hour == 9


def test_normalize_event_without_start_returns_none():
    assert normalize_event({"id": "x", "summary": "no start"}, "cal1") is None


class _FakeExec:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class _FakeCalendarList:
    def __init__(self, payload):
        self._payload = payload

    def list(self, pageToken=None):  # noqa: N803  (mirrors Google API kwarg)
        return _FakeExec(self._payload)


class _FakeEvents:
    def __init__(self, payload):
        self._payload = payload
        self.last_kwargs = {}

    def list(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeExec(self._payload)


class _FakeService:
    def __init__(self, calendars=None, events=None):
        self._calendars = calendars or {"items": []}
        self.events_api = _FakeEvents(events or {"items": []})

    def calendarList(self):  # noqa: N802  (mirrors Google API method)
        return _FakeCalendarList(self._calendars)

    def events(self):
        return self.events_api


def test_find_calendar_id_by_name_case_insensitive():
    service = _FakeService(
        calendars={"items": [{"id": "cal-A", "summary": "Family"}, {"id": "cal-B", "summary": "Équipe PM"}]}
    )
    assert find_calendar_id_by_name("équipe pm", service=service) == "cal-B"
    assert find_calendar_id_by_name("missing", service=service) is None


def test_fetch_upcoming_events_uses_service():
    service = _FakeService(
        events={
            "items": [
                {"id": "e1", "summary": "A", "start": {"dateTime": "2026-07-01T09:00:00+00:00"}},
                {"id": "e2", "summary": "B", "start": {"date": "2026-07-02"}},
            ]
        }
    )
    events = fetch_upcoming_events("cal-B", lookahead_hours=48, service=service)
    assert [e.event_id for e in events] == ["e1", "e2"]


def test_fetch_upcoming_events_pins_window_to_given_now():
    """A caller-supplied ``now`` sets the query bounds, so a follow-up prune can reuse them."""
    service = _FakeService()
    now = datetime.datetime(2026, 7, 4, 12, 0, tzinfo=datetime.timezone.utc)
    fetch_upcoming_events("cal-B", lookahead_hours=48, service=service, now=now)
    assert service.events_api.last_kwargs["timeMin"] == now.isoformat()
    assert service.events_api.last_kwargs["timeMax"] == (now + datetime.timedelta(hours=48)).isoformat()
