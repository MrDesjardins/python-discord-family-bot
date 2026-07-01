"""Parse a single human "when" expression into a reminder schedule.

Mobile users hate typing ``YYYY-MM-DD`` + ``HH:MM`` into two rigid slash-command
fields. This module accepts one natural field instead — "tomorrow", "in 3 days",
"friday 6pm", "tonight", "2026-07-15 18:00", "daily 09:00" — and resolves it to
either a one-time UTC instant or a recurring daily time.

Kept pure (no Discord, no config, no DB): callers pass ``now_local`` (tz-aware) and
the ``default_time``, so it is fully unit-testable. ``deps.reminders`` also uses
``suggest_when`` to power tap-friendly slash-command autocomplete.
"""

from __future__ import annotations

import dataclasses
import datetime
import re
from typing import List, Optional, Tuple

from deps.functions_date import get_tz, parse_time

# Weekday name (full + common short forms) -> Python weekday index (Mon=0).
_WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

# Named periods -> "HH:MM". "morning" resolves to the configured default time.
_PERIODS = {
    "noon": "12:00",
    "afternoon": "15:00",
    "evening": "20:00",
    "tonight": "20:00",
    "night": "21:00",
    "midnight": "00:00",
}

_RECURRING_PREFIXES = ("everyday", "every day", "each day", "daily")

# Relative unit -> seconds. ``in <n> <unit>`` resolves to an exact now+delta instant.
_UNIT_SECONDS = {
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 604800,
    "wk": 604800,
    "week": 604800,
    "weeks": 604800,
}


@dataclasses.dataclass
class ParsedWhen:
    """Result of parsing a ``when`` expression.

    Exactly one schedule is described: recurring (a daily ``HH:MM``) or one-time
    (a tz-aware UTC ``remind_at``).
    """

    recurring: bool
    remind_time: Optional[str] = None  # "HH:MM" when recurring
    remind_at_utc: Optional[datetime.datetime] = None  # UTC instant when one-time


def _parse_clock(token: str) -> Optional[Tuple[int, int]]:
    """Parse a clock token like '18:00', '6pm', '9:30am' into (hour, minute).

    A bare hour without ``:`` or am/pm (e.g. '8') is rejected as too ambiguous.
    """
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", token.strip().lower())
    if not match:
        return None
    minute_part, ampm = match.group(2), match.group(3)
    if minute_part is None and ampm is None:
        return None  # a lone number is not a time
    hour = int(match.group(1))
    minute = int(minute_part or 0)
    if ampm:
        if not 1 <= hour <= 12:
            return None
        hour = (hour % 12) + (12 if ampm == "pm" else 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _split_time(text: str) -> Tuple[str, Optional[Tuple[int, int]], bool]:
    """Peel a trailing time/period off ``text``.

    Returns ``(anchor, (hour, minute) | None, from_period)`` where ``from_period``
    marks a named period ('tonight', 'evening', ...) vs an explicit clock time.
    """
    lowered = text.strip().lower()
    if lowered == "morning" or lowered.endswith(" morning"):
        return lowered[: -len("morning")].strip(), None, True  # None => caller uses default_time
    for period, hhmm in _PERIODS.items():
        if lowered == period or lowered.endswith(" " + period):
            hour, minute = parse_time(hhmm)
            return lowered[: len(lowered) - len(period)].strip(), (hour, minute), True
    match = re.search(r"\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)$", lowered)
    if match:
        clock = _parse_clock(match.group(1))
        if clock is not None:
            return lowered[: match.start()].strip(), clock, False
    # The whole string may itself be a bare clock ("6pm", "18:00").
    clock = _parse_clock(lowered)
    if clock is not None:
        return "", clock, False
    return lowered, None, False


def _weekday_date(today: datetime.date, target: int, next_week: bool) -> datetime.date:
    """Next date matching weekday ``target``; ``next_week`` skips an extra week."""
    days_ahead = (target - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7  # "monday" on a Monday means the next one, not today
    if next_week:
        days_ahead += 7
    return today + datetime.timedelta(days=days_ahead)


def _anchor_date(anchor: str, today: datetime.date) -> Optional[datetime.date]:
    """Resolve a date-anchor phrase to a concrete date, or None if unrecognized."""
    if anchor in ("", "today"):
        return today
    if anchor == "tomorrow":
        return today + datetime.timedelta(days=1)
    if anchor in ("weekend", "this weekend"):
        return _weekday_date(today, 5, next_week=False)  # upcoming Saturday
    if anchor in ("next week", "in a week"):
        return today + datetime.timedelta(days=7)
    next_week = anchor.startswith("next ")
    key = anchor[5:] if next_week else anchor
    if key in _WEEKDAYS:
        return _weekday_date(today, _WEEKDAYS[key], next_week)
    return None


def _to_utc(naive_local: datetime.datetime, timezone_name: str) -> datetime.datetime:
    """Localize a naive wall-clock datetime and convert to UTC (DST-correct)."""
    tz = get_tz(timezone_name)
    aware = tz.localize(naive_local) if hasattr(tz, "localize") else naive_local.replace(tzinfo=tz)
    return aware.astimezone(datetime.timezone.utc)


def _parse_one_time(
    text: str, now_local: datetime.datetime, timezone_name: str, default_time: str
) -> datetime.datetime:
    """Resolve a one-time expression to a UTC instant, or raise ValueError."""
    lowered = text.strip().lower()

    # Relative: "in 2 hours", "in 3 days".
    rel = re.fullmatch(r"in\s+(\d+)\s*([a-z]+)", lowered)
    if rel:
        seconds = _UNIT_SECONDS.get(rel.group(2))
        if seconds is None:
            raise ValueError(f"unknown time unit '{rel.group(2)}'")
        try:
            return now_local.astimezone(datetime.timezone.utc) + datetime.timedelta(seconds=int(rel.group(1)) * seconds)
        except OverflowError as exc:  # absurd offset like "in 9999999999 days"
            raise ValueError("offset too far in the future") from exc

    # Explicit ISO date / datetime.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", lowered):
        midnight = datetime.datetime.combine(
            datetime.date.fromisoformat(lowered), datetime.time(*parse_time(default_time))
        )
        return _to_utc(midnight, timezone_name)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2}(:\d{2})?", lowered):
        return _to_utc(datetime.datetime.fromisoformat(lowered.replace("t", " ")), timezone_name)

    # Anchor phrase + optional time.
    anchor, clock, from_period = _split_time(lowered)
    target = _anchor_date(anchor, now_local.date())
    if target is None:
        raise ValueError(f"could not understand '{text}'")
    if clock is None:
        clock = parse_time(default_time)
    naive = datetime.datetime.combine(target, datetime.time(clock[0], clock[1]))
    result = _to_utc(naive, timezone_name)
    # A bare explicit time already past today rolls to tomorrow ("6pm" at 8pm => tomorrow).
    if anchor == "" and not from_period and result <= now_local.astimezone(datetime.timezone.utc):
        result = _to_utc(naive + datetime.timedelta(days=1), timezone_name)
    return result


def parse_when(
    text: Optional[str],
    now_local: datetime.datetime,
    timezone_name: str,
    default_time: str,
) -> ParsedWhen:
    """Parse a ``when`` field into a recurring or one-time schedule.

    Empty/None => recurring daily at ``default_time``. A ``daily [time]`` prefix =>
    recurring at that time. Anything else => a one-time UTC instant. Raises
    ``ValueError`` on an unrecognizable expression.
    """
    if text is None or not text.strip():
        return ParsedWhen(recurring=True, remind_time=default_time)

    lowered = text.strip().lower()
    for prefix in _RECURRING_PREFIXES:
        if lowered == prefix or lowered.startswith(prefix + " "):
            rest = lowered[len(prefix) :].strip()
            if rest.startswith("at "):
                rest = rest[3:].strip()
            if not rest:
                return ParsedWhen(recurring=True, remind_time=default_time)
            clock = _parse_clock(rest)
            if clock is None:
                raise ValueError(f"could not understand daily time '{rest}'")
            return ParsedWhen(recurring=True, remind_time=f"{clock[0]:02d}:{clock[1]:02d}")

    return ParsedWhen(recurring=False, remind_at_utc=_parse_one_time(lowered, now_local, timezone_name, default_time))


def _fmt_local(dt_utc: datetime.datetime, timezone_name: str) -> str:
    """Render a UTC instant as a friendly local label, e.g. 'Thu Jul 02, 8:30 AM'."""
    local = dt_utc.astimezone(get_tz(timezone_name))
    return local.strftime("%a %b %d, %I:%M %p").replace(" 0", " ")


def suggest_when(
    current: str,
    now_local: datetime.datetime,
    timezone_name: str,
    default_time: str,
) -> List[Tuple[str, str]]:
    """Build tap-friendly autocomplete suggestions as ``(label, value)`` pairs.

    ``value`` always round-trips back through :func:`parse_when`. When ``current``
    already parses, the resolved interpretation is offered first so the user can
    confirm it; otherwise a set of common presets is returned.
    """
    suggestions: List[Tuple[str, str]] = []

    text = (current or "").strip()
    if text:
        try:
            parsed = parse_when(text, now_local, timezone_name, default_time)
        except ValueError:
            parsed = None
        if parsed and parsed.recurring:
            suggestions.append((f"✅ Every day at {parsed.remind_time}", f"daily {parsed.remind_time}"))
        elif parsed and parsed.remind_at_utc is not None:
            iso = parsed.remind_at_utc.astimezone(get_tz(timezone_name)).strftime("%Y-%m-%dT%H:%M")
            suggestions.append((f"✅ {_fmt_local(parsed.remind_at_utc, timezone_name)}", iso))
        # A lone number is a common half-typed state: offer both readings.
        if text.isdigit():
            for unit in ("hours", "days"):
                dt_utc = now_local.astimezone(datetime.timezone.utc) + datetime.timedelta(
                    seconds=int(text) * _UNIT_SECONDS[unit]
                )
                suggestions.append((f"In {text} {unit} ({_fmt_local(dt_utc, timezone_name)})", f"in {text} {unit}"))

    def one_time(label: str, expr: str) -> None:
        dt = parse_when(expr, now_local, timezone_name, default_time).remind_at_utc
        if dt is not None:
            suggestions.append(
                (
                    f"{label} ({_fmt_local(dt, timezone_name)})",
                    dt.astimezone(get_tz(timezone_name)).strftime("%Y-%m-%dT%H:%M"),
                )
            )

    one_time("In 1 hour", "in 1 hour")
    one_time("This evening", "tonight")
    one_time("Tomorrow morning", "tomorrow morning")
    one_time("Tomorrow evening", "tomorrow evening")
    one_time("This weekend", "this weekend")
    one_time("Next Monday", "next monday")
    suggestions.append(("🔁 Every day until acknowledged", "daily"))

    # De-dup by value, keep first (Discord caps at 25; we stay well under).
    seen: set[str] = set()
    unique: List[Tuple[str, str]] = []
    for label, value in suggestions:
        if value not in seen:
            seen.add(value)
            unique.append((label, value))
    return unique[:25]
