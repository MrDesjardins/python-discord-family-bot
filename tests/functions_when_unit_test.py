"""Unit tests for the natural-language 'when' parser (pure, no Discord/DB)."""

import datetime

import pytest
import pytz

from deps.functions_when import parse_when, suggest_when

TZ = "America/Los_Angeles"
DEFAULT = "08:30"


def _now(year=2026, month=7, day=1, hour=10, minute=0):
    # A Wednesday at 10:00 local, well away from DST edges.
    return pytz.timezone(TZ).localize(datetime.datetime(year, month, day, hour, minute))


def _utc(year, month, day, hour, minute):
    return datetime.datetime(year, month, day, hour, minute, tzinfo=datetime.timezone.utc)


# ---------------- recurring ----------------


def test_empty_is_recurring_at_default():
    result = parse_when(None, _now(), TZ, DEFAULT)
    assert result.recurring is True and result.remind_time == DEFAULT
    assert parse_when("   ", _now(), TZ, DEFAULT).recurring is True


def test_daily_prefix_sets_recurring_time():
    assert parse_when("daily", _now(), TZ, DEFAULT).remind_time == DEFAULT
    assert parse_when("daily 09:00", _now(), TZ, DEFAULT).remind_time == "09:00"
    assert parse_when("every day at 7am", _now(), TZ, DEFAULT).remind_time == "07:00"


# ---------------- relative ----------------


def test_in_hours_is_exact_delta():
    result = parse_when("in 2 hours", _now(hour=10), TZ, DEFAULT)
    # 10:00 PDT (17:00 UTC) + 2h = 19:00 UTC.
    assert result.recurring is False
    assert result.remind_at_utc == _utc(2026, 7, 1, 19, 0)


def test_in_days():
    result = parse_when("in 3 days", _now(day=1, hour=10), TZ, DEFAULT)
    assert result.remind_at_utc == _utc(2026, 7, 4, 17, 0)  # same clock time, +3 days


def test_unknown_unit_raises():
    with pytest.raises(ValueError):
        parse_when("in 5 fortnights", _now(), TZ, DEFAULT)


def test_absurd_offset_raises_valueerror_not_overflow():
    # A huge offset overflows timedelta; it must surface as ValueError (which the
    # command handler catches) rather than an uncaught OverflowError.
    with pytest.raises(ValueError):
        parse_when("in 9999999999 days", _now(), TZ, DEFAULT)


# ---------------- anchors + times ----------------


def test_tomorrow_uses_default_time():
    result = parse_when("tomorrow", _now(day=1), TZ, DEFAULT)
    # 2026-07-02 08:30 PDT == 15:30 UTC.
    assert result.remind_at_utc == _utc(2026, 7, 2, 15, 30)


def test_tomorrow_with_period_and_clock():
    assert parse_when("tomorrow evening", _now(day=1), TZ, DEFAULT).remind_at_utc == _utc(2026, 7, 3, 3, 0)  # 20:00 PDT
    assert parse_when("tomorrow 6pm", _now(day=1), TZ, DEFAULT).remind_at_utc == _utc(2026, 7, 3, 1, 0)  # 18:00 PDT


def test_weekday_next_occurrence():
    # Wed 2026-07-01; "friday" -> 2026-07-03 at default 08:30 PDT (15:30 UTC).
    assert parse_when("friday", _now(day=1), TZ, DEFAULT).remind_at_utc == _utc(2026, 7, 3, 15, 30)
    # "next friday" -> a week later, 2026-07-10.
    assert parse_when("next friday", _now(day=1), TZ, DEFAULT).remind_at_utc == _utc(2026, 7, 10, 15, 30)


def test_same_weekday_rolls_a_week():
    # Today is Wednesday; "wednesday" means the next one, not today.
    assert parse_when("wednesday", _now(day=1), TZ, DEFAULT).remind_at_utc == _utc(2026, 7, 8, 15, 30)


def test_iso_date_and_datetime():
    assert parse_when("2026-07-15", _now(), TZ, DEFAULT).remind_at_utc == _utc(2026, 7, 15, 15, 30)
    assert parse_when("2026-07-15 18:00", _now(), TZ, DEFAULT).remind_at_utc == _utc(2026, 7, 16, 1, 0)


def test_bare_time_rolls_to_tomorrow_when_past():
    # At 10:00, "6am" already passed today -> tomorrow 06:00 PDT (13:00 UTC).
    assert parse_when("6am", _now(day=1, hour=10), TZ, DEFAULT).remind_at_utc == _utc(2026, 7, 2, 13, 0)
    # "6pm" is still ahead today -> today 18:00 PDT (01:00 UTC next day).
    assert parse_when("6pm", _now(day=1, hour=10), TZ, DEFAULT).remind_at_utc == _utc(2026, 7, 2, 1, 0)


def test_tonight_stays_today_even_if_evening_passed():
    # Period words are not rolled forward: at 22:00, "tonight" is still today 20:00.
    assert parse_when("tonight", _now(day=1, hour=22), TZ, DEFAULT).remind_at_utc == _utc(2026, 7, 2, 3, 0)


def test_unparseable_raises():
    with pytest.raises(ValueError):
        parse_when("sometime-ish maybe", _now(), TZ, DEFAULT)


# ---------------- autocomplete suggestions ----------------


def test_suggest_defaults_present_and_roundtrip():
    pairs = suggest_when("", _now(), TZ, DEFAULT)
    labels = [label for label, _ in pairs]
    assert any("Tomorrow morning" in label for label in labels)
    assert any("Every day" in label for label in labels)
    # Every non-recurring value round-trips back through parse_when.
    for _label, value in pairs:
        parse_when(value, _now(), TZ, DEFAULT)  # must not raise


def test_suggest_echoes_a_parseable_entry_first():
    pairs = suggest_when("friday 6pm", _now(day=1), TZ, DEFAULT)
    assert pairs[0][0].startswith("✅")
    # Its value round-trips to the same instant.
    assert parse_when(pairs[0][1], _now(day=1), TZ, DEFAULT).remind_at_utc == _utc(2026, 7, 4, 1, 0)


def test_suggest_number_offers_hours_and_days():
    pairs = suggest_when("3", _now(), TZ, DEFAULT)
    values = [value for _, value in pairs]
    assert "in 3 hours" in values and "in 3 days" in values
