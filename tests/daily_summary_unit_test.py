"""Unit tests for the pure daily-summary logic (no DB, config, or Discord)."""

import datetime

import pytz

from deps.daily_summary import chunk_message, day_bounds_utc, format_summary, is_summary_due, reminders_for_day
from deps.models import CalendarEvent, Reminder

TZ = "America/Los_Angeles"


def _local(year, month, day, hour=0, minute=0):
    return pytz.timezone(TZ).localize(datetime.datetime(year, month, day, hour, minute))


def _reminder(**kwargs) -> Reminder:
    base = dict(
        id=1,
        guild_id=1,
        channel_id=10,
        message_id=None,
        author_id=100,
        content="Take out trash",
        created_at=datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc),
        is_recurring=True,
        remind_time="08:30",
        remind_at=None,
        is_active=True,
        acknowledged=False,
        last_reminded_date=None,
    )
    base.update(kwargs)
    return Reminder(**base)


def _event(**kwargs) -> CalendarEvent:
    base = dict(
        event_id="e1",
        calendar_id="cal1",
        summary="Standup",
        description=None,
        location=None,
        start_utc=datetime.datetime(2026, 6, 30, 16, 0, tzinfo=datetime.timezone.utc),
        end_utc=None,
        html_link=None,
        reminded=False,
    )
    base.update(kwargs)
    return CalendarEvent(**base)


# ---------------- is_summary_due ----------------


def test_due_only_after_scheduled_time():
    assert is_summary_due(_local(2026, 6, 30, 7, 59), "08:00", None) is False
    assert is_summary_due(_local(2026, 6, 30, 8, 0), "08:00", None) is True
    assert is_summary_due(_local(2026, 6, 30, 9, 30), "08:00", None) is True


def test_not_due_if_already_sent_today():
    assert is_summary_due(_local(2026, 6, 30, 9, 0), "08:00", "2026-06-30") is False
    # A new day re-arms it.
    assert is_summary_due(_local(2026, 7, 1, 9, 0), "08:00", "2026-06-30") is True


# ---------------- day_bounds_utc ----------------


def test_day_bounds_span_local_day_in_utc():
    start, end = day_bounds_utc(_local(2026, 6, 30, 8, 0), TZ)
    # PDT is UTC-7 in summer: local midnight -> 07:00 UTC.
    assert start == datetime.datetime(2026, 6, 30, 7, 0, tzinfo=datetime.timezone.utc)
    assert end == datetime.datetime(2026, 7, 1, 7, 0, tzinfo=datetime.timezone.utc)


def test_day_bounds_spring_forward_is_23_hours():
    # 2026-03-08 is the US spring-forward day: the local day is only 23h long, so
    # each midnight is localized independently (PST -08:00 -> PDT -07:00).
    start, end = day_bounds_utc(_local(2026, 3, 8, 12, 0), TZ)
    assert start == datetime.datetime(2026, 3, 8, 8, 0, tzinfo=datetime.timezone.utc)  # midnight PST
    assert end == datetime.datetime(2026, 3, 9, 7, 0, tzinfo=datetime.timezone.utc)  # midnight PDT
    assert (end - start) == datetime.timedelta(hours=23)


# ---------------- reminders_for_day ----------------


def test_recurring_always_included_onetime_filtered_by_date():
    recurring = _reminder(id=1, is_recurring=True)
    today_onetime = _reminder(
        id=2,
        is_recurring=False,
        remind_time=None,
        remind_at=datetime.datetime(2026, 6, 30, 22, 0, tzinfo=datetime.timezone.utc),  # 15:00 PDT
        content="Call mom",
    )
    other_day_onetime = _reminder(
        id=3,
        is_recurring=False,
        remind_time=None,
        remind_at=datetime.datetime(2026, 7, 5, 22, 0, tzinfo=datetime.timezone.utc),
        content="Dentist",
    )
    result = reminders_for_day([recurring, today_onetime, other_day_onetime], _local(2026, 6, 30, 8, 0), TZ)
    assert [r.id for r in result] == [1, 2]


# ---------------- format_summary ----------------


def test_format_includes_events_and_reminders():
    events = [_event(summary="Standup", location="Zoom")]
    reminders = [
        _reminder(id=1, is_recurring=True, remind_time="08:30", content="Trash", author_id=100),
        _reminder(
            id=2,
            is_recurring=False,
            remind_time=None,
            remind_at=datetime.datetime(2026, 6, 30, 22, 0, tzinfo=datetime.timezone.utc),
            content="Call mom",
            author_id=200,
        ),
    ]
    text = format_summary(_local(2026, 6, 30, 8, 0), events, reminders, TZ)
    assert "Daily summary — Tuesday, June 30" in text
    assert "09:00 — Standup 📍 Zoom" in text  # 16:00 UTC -> 09:00 PDT
    assert "08:30 daily — Trash (<@100>)" in text
    assert "15:00 — Call mom (<@200>)" in text


def test_format_empty_day():
    text = format_summary(_local(2026, 6, 30, 8, 0), [], [], TZ)
    assert "**📅 Calendar events** — none" in text
    assert "**🔔 Reminders** — none" in text


# ---------------- chunk_message ----------------


def test_chunk_short_text_is_single_chunk():
    assert chunk_message("hello\nworld", limit=2000) == ["hello\nworld"]
    assert chunk_message("") == [""]


def test_chunk_splits_over_limit_on_line_boundaries():
    # 80 lines of "line NN" (~7 chars + newline) comfortably exceeds a 200-char limit.
    text = "\n".join(f"line {i:02d}" for i in range(80))
    chunks = chunk_message(text, limit=200)
    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    # No line was broken mid-content and nothing was dropped: rejoining restores the input.
    assert "\n".join(chunks) == text


def test_chunk_hard_splits_a_single_over_long_line():
    text = "x" * 4500  # one line, no newline, longer than the limit
    chunks = chunk_message(text, limit=2000)
    assert [len(c) for c in chunks] == [2000, 2000, 500]
    assert "".join(chunks) == text
