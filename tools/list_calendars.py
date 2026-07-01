#!/usr/bin/env python3
"""Diagnostic: print every calendar the service account can see.

Run this when the bot logs "no calendar named '…' visible to the service account".
It uses the same credentials path (GOOGLE_SERVICE_ACCOUNT_FILE) and read-only scope as
the bot, so what it prints is exactly what the bot sees.

    uv run tools/list_calendars.py
    # or: python3 tools/list_calendars.py

For each calendar it shows the id, the display name, and the name's repr + code points
so accent/encoding mismatches (NFC vs NFD) are visible. It also reports whether the
configured calendar name (config.yaml -> calendar.name) resolves.
"""

from __future__ import annotations

import os
import sys
import unicodedata

# Allow `python3 tools/list_calendars.py` from the repo root by putting it on sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# pylint: disable=wrong-import-position
from deps.config import get_config  # noqa: E402
from deps.google_calendar import (  # noqa: E402
    SERVICE_ACCOUNT_ENV,
    fetch_upcoming_events,
    find_calendar_id_by_name,
    is_configured,
    list_visible_calendars,
)


def _test_direct_access(calendar_id: str) -> int:
    """Try reading events straight from a calendar id (the service-account path)."""
    print(f"\nTesting direct access to calendar_id {calendar_id!r} ...")
    try:
        events = fetch_upcoming_events(calendar_id, lookahead_hours=24 * 30)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"❌ Cannot read this calendar id: {exc}")
        print(
            "   → The service account has no access. Re-share the calendar with the\n"
            "     service-account email, and double-check you copied the correct Calendar ID."
        )
        return 1
    print(f"✅ Access works — read {len(events)} upcoming event(s).")
    print("   Put this in config.yaml so the bot skips the (empty) calendar list:")
    print(f"       calendar:\n         calendar_id: {calendar_id}")
    return 0


def _describe(name: str) -> str:
    """repr + Unicode code points, so 'é' as NFC vs NFD is unambiguous."""
    points = " ".join(f"U+{ord(ch):04X}" for ch in name)
    form = "NFC" if unicodedata.is_normalized("NFC", name) else "NOT-NFC (likely NFD)"
    return f"{name!r}  [{form}]  {points}"


def main() -> int:
    """List visible calendars, or test direct access to a calendar id passed on argv."""
    if not is_configured():
        print(f"{SERVICE_ACCOUNT_ENV} is not set or the file is missing. Set it in .env.")
        return 1

    # If a calendar id is given (or configured), test reading it directly. This is the
    # path that works for calendars merely *shared* with a service account.
    arg_id = sys.argv[1] if len(sys.argv) > 1 else None
    direct_id = arg_id or get_config().calendar.calendar_id
    if direct_id:
        return _test_direct_access(direct_id)

    try:
        entries = list_visible_calendars()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Failed to list calendars: {exc}")
        return 1

    if not entries:
        print(
            "The service account can see ZERO calendars in its calendar list.\n\n"
            "This is EXPECTED for a calendar merely *shared* with a service account: the\n"
            "share grants access but never adds it to the account's calendar list, so name\n"
            "lookup can't find it. Address the calendar by its ID instead:\n\n"
            "  1. Google Calendar (web) → hover the calendar → ⋮ → Settings and sharing.\n"
            "  2. Scroll to 'Integrate calendar' → copy the 'Calendar ID'\n"
            "     (looks like ...@group.calendar.google.com).\n"
            "  3. Verify access:  python3 tools/list_calendars.py <calendar-id>\n"
            "  4. Put it in config.yaml under  calendar:  as  calendar_id: <calendar-id>\n"
        )
        return 1

    print(f"Service account can see {len(entries)} calendar(s):\n")
    for entry in entries:
        display = entry.get("summaryOverride") or entry.get("summary") or "(no name)"
        print(f"  id:          {entry.get('id')}")
        print(f"  name:        {_describe(display)}")
        if entry.get("summaryOverride"):
            print(f"  (summary):   {_describe(entry.get('summary', ''))}")
        print(f"  accessRole:  {entry.get('accessRole')}")
        print(f"  primary:     {entry.get('primary', False)}")
        print()

    configured = get_config().calendar.name
    resolved = find_calendar_id_by_name(configured)
    print(f"Configured calendar.name = {_describe(configured)}")
    if resolved:
        print(f"✅ Resolves to calendarId: {resolved}")
        return 0
    print(
        "❌ Does NOT match any visible calendar above.\n"
        "Compare the code points: if they differ only by accents, update calendar.name in\n"
        "config.yaml to match the name printed above exactly (copy-paste it)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
