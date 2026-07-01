#!/usr/bin/env python3
"""Entry point for the family Discord bot."""

import os

from dotenv import load_dotenv

from deps.bot_singleton import BotSingleton
from deps.log import print_error_log, print_log
from deps.mybot import MyBot

load_dotenv()

ENV = os.getenv("ENV", "dev")
TOKEN = os.getenv("BOT_TOKEN_DEV") if ENV == "dev" else os.getenv("BOT_TOKEN")


def main() -> None:
    """Start the bot."""
    if not TOKEN:
        token_var = "BOT_TOKEN_DEV" if ENV == "dev" else "BOT_TOKEN"
        print_error_log(f"{token_var} not found in environment/.env. Cannot start.")
        raise SystemExit(1)

    bot: MyBot = BotSingleton().bot
    print_log(f"Starting bot (ENV={ENV})")
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
