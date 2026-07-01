"""Unit tests for date/time helpers."""

import datetime

import pytest

from deps.functions_date import local_datetime_to_utc, parse_time


def test_parse_time_default():
    assert parse_time(None) == (8, 30)
    assert parse_time("06:15") == (6, 15)


def test_parse_time_invalid():
    with pytest.raises(ValueError):
        parse_time("25:00")


def test_local_datetime_to_utc_pacific():
    # 2026-07-15 08:30 in Los Angeles (PDT, UTC-7) == 15:30 UTC.
    result = local_datetime_to_utc("2026-07-15", "08:30", "America/Los_Angeles")
    assert result == datetime.datetime(2026, 7, 15, 15, 30, tzinfo=datetime.timezone.utc)


def test_local_datetime_to_utc_default_time():
    # Default 08:30 applied when time omitted.
    result = local_datetime_to_utc("2026-12-01", None, "UTC")
    assert result == datetime.datetime(2026, 12, 1, 8, 30, tzinfo=datetime.timezone.utc)
