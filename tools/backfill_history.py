#!/usr/bin/env python3
"""One-off backfill of Discord message history into the bot database.

The bot only archives messages sent while it is online (see cogs/events.py); it does
NOT read history. This script fills the gap: it logs in, reads every text channel it can
see, and stores messages from the last N weeks up to a cutoff of *today 17:30
America/Los_Angeles*, using the same store path as live archiving. The running bot's
embedding loop then embeds them within ~30s (no embedding is done here).

Run it ONCE, ON the mini-pc (where .env, config.yaml and family_bot.db live):

    cd /home/pdesjardins/code/python-discord-family-bot
    ENV=prod uv run tools/backfill_history.py --dry-run   # preview counts, writes nothing
    ENV=prod uv run tools/backfill_history.py             # actually store

Safe to re-run: stores use INSERT OR IGNORE, so duplicates are skipped. It can run while
the bot is live (it opens a short second session and closes when done).
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys

import discord
from dotenv import load_dotenv

# override=True so this project's .env wins over any BOT_TOKEN already exported in the
# shell (e.g. another bot's token) — otherwise dotenv keeps the ambient value and we could
# log into the wrong bot.
load_dotenv(os.path.join(os.getcwd(), ".env"), override=True)

# Allow `uv run tools/backfill_history.py` from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from deps.config import get_config  # noqa: E402
from deps.functions_date import get_tz  # noqa: E402
from deps.log import print_error_log, print_log  # noqa: E402
from deps.message_data_access import store_message  # noqa: E402

WEEKS_BACK = 5
CUTOFF_TZ = "America/Los_Angeles"
CUTOFF_HOUR = 17
CUTOFF_MINUTE = 30


def _window() -> tuple[datetime.datetime, datetime.datetime]:
    """Return (after_utc, before_utc): the 5-week window ending today 17:30 LA time."""
    tz = get_tz(CUTOFF_TZ)
    now_local = datetime.datetime.now(tz)
    before_local = now_local.replace(hour=CUTOFF_HOUR, minute=CUTOFF_MINUTE, second=0, microsecond=0)
    after_local = before_local - datetime.timedelta(weeks=WEEKS_BACK)
    return after_local.astimezone(datetime.timezone.utc), before_local.astimezone(datetime.timezone.utc)


async def _backfill(client: discord.Client, dry_run: bool) -> None:
    """Walk the configured family guild's text channels and store messages in the window."""
    # Safety: only ever write to the guild in config.yaml. If we somehow logged into the
    # wrong bot (e.g. a stray BOT_TOKEN), it won't be in this guild, so we store nothing.
    expected_guild_id = get_config().guild_id
    guild = client.get_guild(expected_guild_id)
    if guild is None:
        print_error_log(
            f"backfill: logged-in bot {client.user} is NOT in the configured guild "
            f"{expected_guild_id}. Wrong token? Aborting without storing anything."
        )
        return
    print_log(f"backfill: target guild '{guild.name}' ({guild.id}) via bot {client.user}")

    after_utc, before_utc = _window()
    print_log(f"backfill: window {after_utc.isoformat()} .. {before_utc.isoformat()} (UTC)")

    stored = skipped_bot = skipped_empty = 0
    for channel in guild.text_channels:
        channel_total = 0
        try:
            async for message in channel.history(limit=None, after=after_utc, before=before_utc, oldest_first=True):
                if message.author.bot:
                    skipped_bot += 1
                    continue
                if not (message.content or "").strip():
                    skipped_empty += 1
                    continue
                if not dry_run:
                    store_message(
                        message_id=message.id,
                        guild_id=guild.id,
                        channel_id=channel.id,
                        channel_name=channel.name,
                        author_id=message.author.id,
                        author_name=message.author.display_name,
                        content=message.content or "",
                        created_at=message.created_at,
                    )
                stored += 1
                channel_total += 1
        except discord.Forbidden:
            print_log(f"backfill: no access to #{channel.name} in {guild.name}; skipping")
            continue
        except discord.HTTPException as exc:
            print_error_log(f"backfill: error reading #{channel.name}: {exc}")
            continue
        if channel_total:
            print_log(f"backfill: #{channel.name}: {channel_total} message(s)")

    verb = "would store" if dry_run else "stored"
    print_log(f"backfill: done. {verb} {stored} message(s); " f"skipped {skipped_bot} bot + {skipped_empty} empty.")


def main() -> int:
    """Log in, run the backfill, then disconnect."""
    parser = argparse.ArgumentParser(description="Backfill Discord message history into the DB.")
    parser.add_argument("--dry-run", action="store_true", help="Count messages but write nothing.")
    args = parser.parse_args()

    env = os.getenv("ENV", "prod")  # this tool defaults to prod
    token = os.getenv("BOT_TOKEN_DEV") if env == "dev" else os.getenv("BOT_TOKEN")
    if not token:
        var = "BOT_TOKEN_DEV" if env == "dev" else "BOT_TOKEN"
        print_error_log(f"backfill: {var} not set (ENV={env}). Cannot log in.")
        return 1

    intents = discord.Intents.default()
    intents.message_content = True  # required to read message text over REST/history
    intents.members = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:  # pylint: disable=unused-variable
        try:
            print_log(f"backfill: logged in as {client.user}; scanning {len(client.guilds)} guild(s)")
            await _backfill(client, args.dry_run)
        finally:
            await client.close()

    client.run(token, log_handler=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
