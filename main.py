import os
import logging
import asyncio
import time
import sys
import signal
import asyncio
import discord
from discord.ext import commands, tasks
from config import TOKEN, LOGGING_DEBUG_MODE
from logging.handlers import RotatingFileHandler
from core.bot import Bot
from core.dashboard import OwnerDashboard

if not TOKEN:
    raise SystemExit("ERROR: Set DISCORD_TOKEN in a .env in root folder.")

logger = logging.getLogger("discord")
if LOGGING_DEBUG_MODE:
    logger.setLevel(logging.DEBUG)
    print("Running logger in DEBUG mode")
else:
    logger.setLevel(logging.INFO)
    print("Running logger in PRODUCTION mode")
log_path = os.path.join(os.path.dirname(__file__), "discord.log")
handler = RotatingFileHandler(
    filename=log_path,
    encoding="utf-8",
    mode="a",
    maxBytes=1 * 1024 * 1024,
    backupCount=5
)
logger.addHandler(handler)

log_format = '%(asctime)s||%(levelname)s: %(message)s'
date_format = '%H:%M:%S %d-%m'

formatter = logging.Formatter(log_format, datefmt=date_format)

handler.setFormatter(formatter)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = Bot(intents=intents)

@bot.tree.command(name="od", description=".")
async def zc(interaction: discord.Interaction):
    if not await bot.is_owner(interaction.user):
        await interaction.response.send_message("🤫", ephemeral=True)
        return
    view = OwnerDashboard(bot, interaction.user)
    await interaction.response.send_message(view=view, ephemeral=True)

if __name__ == "__main__":
    async def main_async():
        try:
            async with bot:
                await bot.start(TOKEN)
        except Exception as e:
            print(f"ERROR: Failed to start the bot: {e}")


    asyncio.run(main_async())