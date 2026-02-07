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
from utils.log import LoggingManager
from core.dashboard import OwnerDashboard
from VERSION import bot_version

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

bot = commands.Bot(command_prefix="!!", intents=intents, help_command=None,
                   member_cache_flags=discord.MemberCacheFlags(voice=True, joined=False), chunk_guilds_at_startup=False, guild_ready_timeout=0)


class PrivateLayoutView(discord.ui.LayoutView):
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "This isn't for you!",
                ephemeral=True
            )
            return False
        return True


async def restart_bot():
    print()
    print("Restarting bot...")
    await signal_handler()
    os.execv(sys.executable, [sys.executable] + sys.argv)


async def setup_hook():
    bot.logger = LoggingManager()
    bot.process_start_time = time.time()
    bot.monitor = ConnectionMonitor(bot)
    bot.monitor.monitor_connection.start()

    cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")

    if os.path.exists(cogs_dir):
        for filename in os.listdir(cogs_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                extension = f"cogs.{filename[:-3]}"
                try:
                    await bot.load_extension(extension)
                    print(f"> Loaded {extension} Successfully")
                except Exception as e:
                    print(f"ERROR: Failed to load {extension}: {e}")
    else:
        print("WARNING: 'cogs' directory not found.")

    for s in (signal.SIGINT, signal.SIGTERM):
        bot.loop.add_signal_handler(
            s, lambda: asyncio.create_task(signal_handler())
        )


async def signal_handler():
    print("\nBot shutdown requested...")
    extensions = list(bot.extensions.keys())
    for extension in extensions:
        try:
            await bot.unload_extension(extension)
            print(f"> Unloaded {extension} successfully")
        except Exception as e:
            print(f"Error unloading {extension}: {e}")

    print("👋 Goodbye!")
    await bot.close()


bot.setup_hook = setup_hook


@bot.event
async def on_ready():
    if bot.owner_id is None:
        app_info = await bot.application_info()

        if app_info.team:
            bot.owner_id = app_info.team.owner_id
        else:
            bot.owner_id = app_info.owner.id

        owner_user = bot.get_user(bot.owner_id)
        if not owner_user:
            owner_user = await bot.fetch_user(bot.owner_id)

        owner_user_name = owner_user.name
    else:
        owner_user = await bot.fetch_user(bot.owner_id)
        owner_user_name = owner_user.name

    print(f"---------------------------------------------------")
    print(f"Powered by Dopamine Framework {bot_version}")
    print()
    print(f"Bot ready: {bot.user} (ID: {bot.user.id})")
    print(f"Bot Owner identified: {owner_user_name}")
    print(f"---------------------------------------------------")

    logger.info("")
    logger.info("")
    logger.info(f"---------------------------------------------------")
    logger.info(f"Powered by Dopamine Framework {bot_version}")
    logger.info()
    logger.info(f"Bot ready: {bot.user} (ID: {bot.user.id})")
    logger.info(f"Bot Owner identified: {owner_user_name}")
    logger.info(f"---------------------------------------------------")
    logger.info("")
    logger.info("")

    await bot.change_presence(
        status=discord.Status.dnd,
        activity=discord.CustomActivity(name="✨ Testing v3.0.0-beta!")
    )
    bot.start_time = time.time()


class ConnectionMonitor:
    def __init__(self, bot):
        self.bot = bot
        self.fail_count = 0
        self.is_reconnecting = False

    @tasks.loop(seconds=30)
    async def monitor_connection(self):
        if self.is_reconnecting:
            return

        latency = self.bot.latency

        if not self.bot.is_ready() or latency != latency or latency > 15:
            self.fail_count += 1
            logger.warning(f"Connection check failed ({self.fail_count}/2)")
            print(f"Connection check failed ({self.fail_count}/2)")
        else:
            self.fail_count = 0

        if self.fail_count >= 2:
            await self.reconnect_logic()

    async def reconnect_logic(self):
        self.is_reconnecting = True
        logger.error("Connection lost. Attempting manual reconnect...")
        print("Connection lost. Attempting manual reconnect...")

        while not self.bot.is_closed():
            try:
                await self.bot.close()
                await asyncio.sleep(5)

                await self.bot.login(TOKEN)
                await self.bot.connect()
                logger.info("Successfully reconnected to Discord Gateway.")
                print("Successfully reconnected to Discord Gateway.")
                self.fail_count = 0
                self.is_reconnecting = False
                break
            except Exception as e:
                logger.error(f"Reconnect failed: {e}. Retrying in 30s...")
                print(f"Reconnect failed: {e}. Retrying in 30s...")
                await asyncio.sleep(30)

@bot.tree.command(name="od", description=".")
async def zc(interaction: discord.Interaction):
    if not await bot.is_owner(interaction.user):
        await interaction.response.send_message(
            "🤫",
            ephemeral=True
        )
        return

    view = OwnerDashboard(bot, interaction.user)
    await interaction.response.send_message(view=view)


if __name__ == "__main__":
    async def main_async():
        try:
            async with bot:
                await bot.start(TOKEN)
        except Exception as e:
            print(f"ERROR: Failed to start the bot: {e}")


    asyncio.run(main_async())