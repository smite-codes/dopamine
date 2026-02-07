import logging
import discord
from discord import app_commands

logger = logging.getLogger("discord")


class CommandRegistry:
    def __init__(self, bot):
        self.bot = bot

    async def get_sync_status(self, guild: discord.Guild = None):
        local_commands = self.bot.tree.get_commands(guild=guild)
        try:
            remote_commands = await self.bot.tree.fetch_commands(guild=guild)
        except Exception as e:
            logger.error(f"Failed to fetch remote commands: {e}")
            return False

        if len(local_commands) != len(remote_commands):
            return False

        local_map = {c.name: c.description for c in local_commands}
        remote_map = {c.name: c.description for c in remote_commands}

        return local_map == remote_map

    async def smart_sync(self, guild: discord.Guild = None):
        is_synced = await self.get_sync_status(guild)

        scope = f"Guild({guild.id})" if guild else "Global"

        if not is_synced:
            logger.info(f"Detected changes. Syncing {scope} commands...")
            await self.bot.tree.sync(guild=guild)
            return f"✅ {scope} commands synced successfully."
        else:
            logger.info(f"No changes detected for {scope}. Skipping sync.")
            return f"{scope} commands are already up to date."

    async def force_sync(self, guild: discord.Guild = None):
        scope = f"Guild: {guild.name} ({guild.id})" if guild else "Global"
        try:
            await self.bot.tree.sync(guild=guild)
            return f"Synced slash commands to: {scope}."
        except discord.HTTPException as e:
            return f"❌ Rate limit or API error: {e}"