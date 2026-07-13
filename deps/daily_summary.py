"""Pure logic for the daily summary of the day's calendar events and reminders.

Kept free of the database, config, and Discord so it is trivially unit-testable:
callers pass in the already-fetched events/reminders and the current local time.
"""

from __future__ import annotations

import datetime
from typing import List, Tuple

from deps.functions_date import get_tz, parse_time
from deps.models import CalendarEvent, Reminder


def is_summary_due(local_now: datetime.datetime, summary_time: str, last_sent_date: str | None) -> bool:
    """Return True when the summary for today has not been sent and its time has arrived.

    ``local_now`` must be tz-aware in the guild timezone; ``last_sent_date`` is the
    ``YYYY-MM-DD`` string of the last day a summary went out (None if never).
    """
    today_str = local_now.strftime("%Y-%m-%d")
    if last_sent_date == today_str:
        return False
    hour, minute = parse_time(summary_time)
    scheduled = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return local_now >= scheduled


def day_bounds_utc(local_now: datetime.datetime, timezone_name: str) -> Tuple[datetime.datetime, datetime.datetime]:
    """Return the UTC ``[start, end)`` datetimes spanning the local calendar day of ``local_now``."""
    tz = get_tz(timezone_name)

    def localize(naive: datetime.datetime) -> datetime.datetime:
        # Localize each midnight independently so DST transitions get the right offset
        # (adding a 24h timedelta to a fixed-offset localized start would be off by an
        # hour on spring-forward / fall-back days).
        return tz.localize(naive) if hasattr(tz, "localize") else naive.replace(tzinfo=tz)

    start_naive = datetime.datetime(local_now.year, local_now.month, local_now.day)
    end_naive = start_naive + datetime.timedelta(days=1)
    return localize(start_naive).astimezone(datetime.timezone.utc), localize(end_naive).astimezone(
        datetime.timezone.utc
    )


def reminders_for_day(reminders: List[Reminder], local_now: datetime.datetime, timezone_name: str) -> List[Reminder]:
    """Filter active reminders down to those relevant today.

    Recurring reminders fire every day, so they always qualify. One-time reminders
    qualify only when their ``remind_at`` falls on the local day of ``local_now``.
    """
    tz = get_tz(timezone_name)
    today = local_now.date()
    selected: List[Reminder] = []
    for reminder in reminders:
        if reminder.is_recurring:
            selected.append(reminder)
        elif reminder.remind_at is not None and reminder.remind_at.astimezone(tz).date() == today:
            selected.append(reminder)
    return selected


def _sort_reminders(reminders: List[Reminder], timezone_name: str) -> List[Reminder]:
    """Order recurring reminders (by time) before one-time reminders (by time)."""
    tz = get_tz(timezone_name)

    def key(reminder: Reminder) -> Tuple[int, str]:
        if reminder.is_recurring:
            return (0, reminder.remind_time or "")
        local = reminder.remind_at.astimezone(tz) if reminder.remind_at else None
        return (1, local.strftime("%H:%M") if local else "")

    return sorted(reminders, key=key)


def format_summary(
    local_now: datetime.datetime,
    events: List[CalendarEvent],
    reminders: List[Reminder],
    timezone_name: str,
) -> str:
    """Build the Discord message for the day's events and reminders."""
    tz = get_tz(timezone_name)
    lines = [f"📋 **Daily summary — {local_now:%A, %B %d}**"]

    lines.append("")
    if events:
        lines.append("**📅 Calendar events**")
        for event in events:
            local_start = event.start_utc.astimezone(tz)
            line = f"• {local_start:%H:%M} — {event.summary}"
            if event.location:
                line += f" 📍 {event.location}"
            lines.append(line)
    else:
        lines.append("**📅 Calendar events** — none")

    lines.append("")
    if reminders:
        lines.append("**🔔 Reminders**")
        for reminder in _sort_reminders(reminders, timezone_name):
            if reminder.is_recurring:
                when = f"{reminder.remind_time} daily" if reminder.remind_time else "daily"
            else:
                local = reminder.remind_at.astimezone(tz) if reminder.remind_at else None
                when = local.strftime("%H:%M") if local else "today"
            lines.append(f"• {when} — {reminder.content} (<@{reminder.ping_user_id}>)")
    else:
        lines.append("**🔔 Reminders** — none")

    return "\n".join(lines)


def chunk_message(text: str, limit: int = 2000) -> List[str]:
    """Split ``text`` into chunks of at most ``limit`` chars, preferring line breaks.

    Discord rejects messages longer than 2000 characters, so a long digest must be
    posted as several messages. Splits on ``"\\n"`` so lines stay intact; a single line
    longer than ``limit`` is hard-split as a fallback. Returns ``[""]`` for empty input.
    """
    chunks: List[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:  # a single over-long line: hard-split it
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    chunks.append(current)
    return chunks
