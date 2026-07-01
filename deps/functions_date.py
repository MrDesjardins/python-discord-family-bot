"""Timezone-aware date/time helpers for reminders."""

import datetime
from typing import Optional, Tuple

import pytz

from deps.values import DEFAULT_REMINDER_TIME


def get_tz(timezone_name: str) -> datetime.tzinfo:
    """Return a tzinfo for an IANA name, falling back to UTC on error."""
    try:
        return pytz.timezone(timezone_name)
    except pytz.UnknownTimeZoneError:
        return pytz.utc


def parse_time(time_str: Optional[str]) -> Tuple[int, int]:
    """Parse 'HH:MM' into (hour, minute). Defaults to DEFAULT_REMINDER_TIME."""
    if not time_str:
        time_str = DEFAULT_REMINDER_TIME
    hour_str, minute_str = time_str.strip().split(":")
    hour, minute = int(hour_str), int(minute_str)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Time must be between 00:00 and 23:59")
    return hour, minute


def local_datetime_to_utc(date_str: str, time_str: Optional[str], timezone_name: str) -> datetime.datetime:
    """Combine a 'YYYY-MM-DD' date and 'HH:MM' time in the guild tz into UTC."""
    year, month, day = (int(part) for part in date_str.strip().split("-"))
    hour, minute = parse_time(time_str)
    tz = get_tz(timezone_name)
    naive = datetime.datetime(year, month, day, hour, minute)
    localized = tz.localize(naive) if hasattr(tz, "localize") else naive.replace(tzinfo=tz)
    return localized.astimezone(pytz.utc)


def now_in_tz(timezone_name: str) -> datetime.datetime:
    """Return the current time in the guild's timezone."""
    return datetime.datetime.now(get_tz(timezone_name))
