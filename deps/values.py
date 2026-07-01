"""Shared constants. Tunable settings now live in config.yaml (see deps/config.py)."""

# Hard fallback used only if a reminder time is missing everywhere else.
DEFAULT_REMINDER_TIME = "08:30"

# --- Slash command names ---
COMMAND_SET_REMINDER = "setreminder"
COMMAND_LIST_REMINDERS = "listreminders"
COMMAND_CANCEL_REMINDER = "cancelreminder"
COMMAND_RELOAD_CONFIG = "reloadconfig"
