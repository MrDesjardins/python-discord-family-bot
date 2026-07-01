"""Custom bot class for the family Discord bot."""

import os

import discord
from discord.ext import commands

from deps.log import print_error_log, print_log


class MyBot(commands.Bot):
    """discord.py Bot with the intents this bot needs and cog auto-loading."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True  # required to read message text for archiving + AI
        intents.members = True
        intents.reactions = True
        intents.guild_reactions = True
        super().__init__(command_prefix="!", intents=intents)
        self.allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)

    async def setup_hook(self) -> None:
        """Load cogs during discord.py startup."""
        await self.load_cogs()

    async def load_cogs(self) -> None:
        """Load every cog module from the local ``cogs/`` package."""
        for filename in sorted(os.listdir("./cogs")):
            if filename.endswith(".py") and filename != "__init__.py":
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    print_log(f"✅ Loaded {filename}")
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    print_error_log(f"❌ Failed to load {filename}: {exc}")
