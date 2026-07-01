"""Singleton holding the single bot instance."""

from __future__ import annotations

from typing import Optional

from deps.mybot import MyBot


class BotSingleton:
    """Ensure a single MyBot instance across the application."""

    _instance: Optional["BotSingleton"] = None
    _bot: MyBot

    def __new__(cls) -> "BotSingleton":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._bot = MyBot()
        return cls._instance

    @property
    def bot(self) -> MyBot:
        """Return the bot instance."""
        return self._bot
