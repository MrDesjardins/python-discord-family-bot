"""Non-secret configuration loaded from a YAML file.

This is the authoritative source for channel IDs, timezone, AI tuning, and the
calendar settings. Secrets (tokens, API keys, the Google service-account file
path) stay in environment variables / ``.env`` — never in this YAML.

Usage:
    from deps.config import get_config
    cfg = get_config()
    cfg.channels.reminder
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any, Dict, Optional

import yaml

from deps.functions_date import parse_time

DEFAULT_CONFIG_PATH = os.getenv("CONFIG_FILE", "config.yaml")


@dataclasses.dataclass
class ChannelsConfig:
    """Discord channel IDs the bot posts to."""

    reminder: int
    calendar: int
    ai: Optional[int] = None  # None => the bot answers @-mentions in any channel


@dataclasses.dataclass
class AIConfig:
    """Tuning for the AI Q&A feature."""

    model: str = "gpt-4o-mini"
    embedding_model: str = "all-MiniLM-L6-v2"
    max_context_messages: int = 50
    recency_halflife_days: float = 14.0
    similarity_weight: float = 0.7


@dataclasses.dataclass
class RemindersConfig:
    """Defaults for the /setreminder feature."""

    default_time: str = "08:30"
    timezone: str = "America/Los_Angeles"


@dataclasses.dataclass
class DailySummaryConfig:
    """Daily digest of the day's calendar events and reminders."""

    enabled: bool = False
    time: str = "08:00"  # HH:MM (24h) in the reminders timezone


@dataclasses.dataclass
class CalendarConfig:
    """Google Calendar reminder settings."""

    enabled: bool = False
    name: str = "Équipe PM"
    calendar_id: Optional[str] = None  # set to skip name lookup (needed for service-account shares)
    reminder_lead_minutes: int = 30
    poll_interval_minutes: int = 15
    lookahead_hours: int = 48


@dataclasses.dataclass
class Config:
    """Top-level configuration object."""

    guild_id: int
    channels: ChannelsConfig
    ai: AIConfig
    reminders: RemindersConfig
    calendar: CalendarConfig
    daily_summary: DailySummaryConfig


def _require(mapping: Dict[str, Any], key: str, context: str) -> Any:
    """Return mapping[key] or raise a clear error naming the missing field."""
    if key not in mapping or mapping[key] is None:
        raise ValueError(f"config: missing required field '{context}{key}'")
    return mapping[key]


def parse_config(data: Dict[str, Any]) -> Config:
    """Build a Config from a parsed YAML dict (pure; unit-testable)."""
    data = data or {}
    channels_raw = data.get("channels") or {}
    ai_raw = data.get("ai") or {}
    reminders_raw = data.get("reminders") or {}
    calendar_raw = data.get("calendar") or {}
    daily_summary_raw = data.get("daily_summary") or {}

    channels = ChannelsConfig(
        reminder=int(_require(channels_raw, "reminder", "channels.")),
        calendar=int(_require(channels_raw, "calendar", "channels.")),
        ai=int(channels_raw["ai"]) if channels_raw.get("ai") is not None else None,
    )
    ai = AIConfig(
        model=ai_raw.get("model", AIConfig.model),
        embedding_model=ai_raw.get("embedding_model", AIConfig.embedding_model),
        max_context_messages=int(ai_raw.get("max_context_messages", AIConfig.max_context_messages)),
        recency_halflife_days=float(ai_raw.get("recency_halflife_days", AIConfig.recency_halflife_days)),
        similarity_weight=float(ai_raw.get("similarity_weight", AIConfig.similarity_weight)),
    )
    reminders = RemindersConfig(
        default_time=reminders_raw.get("default_time", RemindersConfig.default_time),
        timezone=reminders_raw.get("timezone", RemindersConfig.timezone),
    )
    calendar = CalendarConfig(
        enabled=bool(calendar_raw.get("enabled", CalendarConfig.enabled)),
        name=calendar_raw.get("name", CalendarConfig.name),
        calendar_id=calendar_raw.get("calendar_id") or None,
        reminder_lead_minutes=int(calendar_raw.get("reminder_lead_minutes", CalendarConfig.reminder_lead_minutes)),
        poll_interval_minutes=int(calendar_raw.get("poll_interval_minutes", CalendarConfig.poll_interval_minutes)),
        lookahead_hours=int(calendar_raw.get("lookahead_hours", CalendarConfig.lookahead_hours)),
    )
    daily_summary = DailySummaryConfig(
        enabled=bool(daily_summary_raw.get("enabled", DailySummaryConfig.enabled)),
        time=daily_summary_raw.get("time", DailySummaryConfig.time),
    )
    # Validate the summary time at load time so a typo fails loudly here instead of
    # silently killing the background loop on its first tick.
    parse_time(daily_summary.time)
    return Config(
        guild_id=int(_require(data, "guild_id", "")),
        channels=channels,
        ai=ai,
        reminders=reminders,
        calendar=calendar,
        daily_summary=daily_summary,
    )


def load_config(path: Optional[str] = None) -> Config:
    """Read and parse the YAML config file from disk."""
    config_path = path or DEFAULT_CONFIG_PATH
    with open(config_path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return parse_config(data)


_config: Optional[Config] = None


def get_config() -> Config:
    """Return the process-wide config, loading it on first access."""
    global _config  # pylint: disable=global-statement
    if _config is None:
        _config = load_config()
    return _config


def reload_config(path: Optional[str] = None) -> Config:
    """Force a re-read of the config file (used after editing config.yaml)."""
    global _config  # pylint: disable=global-statement
    _config = load_config(path)
    return _config
