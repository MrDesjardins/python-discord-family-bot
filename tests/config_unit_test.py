"""Unit tests for the YAML config parser (pure, no file I/O)."""

import pytest

from deps.config import parse_config


def _minimal() -> dict:
    return {"guild_id": 42, "channels": {"reminder": 111, "calendar": 222}}


def test_parse_minimal_applies_defaults():
    cfg = parse_config(_minimal())
    assert cfg.guild_id == 42
    assert cfg.channels.reminder == 111
    assert cfg.channels.calendar == 222
    assert cfg.channels.ai is None
    # Defaults
    assert cfg.ai.model == "gpt-4o-mini"
    assert cfg.ai.max_context_messages == 50
    assert cfg.reminders.default_time == "08:30"
    assert cfg.reminders.timezone == "America/Los_Angeles"
    assert cfg.calendar.reminder_lead_minutes == 30
    assert cfg.daily_summary.enabled is False
    assert cfg.daily_summary.time == "08:00"


def test_parse_overrides():
    data = _minimal()
    data["channels"]["ai"] = 333
    data["ai"] = {"model": "gpt-4o", "max_context_messages": 25, "similarity_weight": 0.5}
    data["reminders"] = {"default_time": "07:00", "timezone": "UTC"}
    data["calendar"] = {"enabled": True, "name": "Team", "reminder_lead_minutes": 15}
    data["daily_summary"] = {"enabled": True, "time": "07:15"}
    cfg = parse_config(data)
    assert cfg.channels.ai == 333
    assert cfg.ai.model == "gpt-4o"
    assert cfg.ai.max_context_messages == 25
    assert cfg.ai.similarity_weight == 0.5
    assert cfg.reminders.default_time == "07:00"
    assert cfg.reminders.timezone == "UTC"
    assert cfg.calendar.enabled is True
    assert cfg.calendar.name == "Team"
    assert cfg.calendar.reminder_lead_minutes == 15
    assert cfg.daily_summary.enabled is True
    assert cfg.daily_summary.time == "07:15"


def test_bad_daily_summary_time_raises():
    data = _minimal()
    data["daily_summary"] = {"enabled": True, "time": "0800"}  # missing colon
    with pytest.raises(ValueError):
        parse_config(data)


def test_missing_required_field_raises():
    with pytest.raises(ValueError):
        parse_config({"channels": {"reminder": 1, "calendar": 2}})  # no guild_id
    with pytest.raises(ValueError):
        parse_config({"guild_id": 1, "channels": {"reminder": 1}})  # no calendar channel
