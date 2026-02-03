import os
import logging
import asyncio
import time
import sys
import signal
import discord
from discord.ext import commands, tasks
from config import TOKEN, LOGGING_DEBUG_MODE
from logging.handlers import RotatingFileHandler

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
                   member_cache_flags=discord.MemberCacheFlags(voice=True, joined=False), chunk_guilds_at_startup=False)
bot.synced = False


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


class OwnerDashboard(PrivateLayoutView):
    def __init__(self, bot, user, page=1):
        super().__init__(user, timeout=None)
        self.bot = bot
        self.page = page
        self.items_per_page = 5
        self.build_layout()

    def build_layout(self):
        self.clear_items()
        container = discord.ui.Container()
        container.add_item((discord.ui.TextDisplay("## Owner Dashboard")))
        container.add_item(discord.ui.Separator())

        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        cog_files = []
        if os.path.exists(cogs_dir):
            cog_files = [f for f in os.listdir(cogs_dir) if f.endswith(".py") and not f.startswith("__")]

        cog_files.sort()
        total_items = len(cog_files)
        total_pages = (total_items + self.items_per_page - 1) // self.items_per_page if total_items > 0 else 1

        start_idx = (self.page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        current_page_cogs = cog_files[start_idx:end_idx]

        if not current_page_cogs:
            container.add_item(discord.ui.TextDisplay("*No extensions found in /cogs.*"))
        else:
            for idx, filename in enumerate(current_page_cogs, start_idx + 1):
                ext_name = f"cogs.{filename[:-3]}"
                is_loaded = ext_name in self.bot.extensions

                cog_btn = discord.ui.Button(
                    label="Unload" if is_loaded else "Load",
                    style=discord.ButtonStyle.secondary if is_loaded else discord.ButtonStyle.primary
                )

                cog_btn.callback = self.create_toggle_callback(ext_name, is_loaded)
                container.add_item(
                    discord.ui.Section(discord.ui.TextDisplay(f"{idx}. `{filename}`"), accessory=cog_btn))

            container.add_item(discord.ui.TextDisplay(f"-# Page {self.page} of {total_pages}"))

        if total_pages > 1:
            nav_row = discord.ui.ActionRow()

            left_btn = discord.ui.Button(label="◀️", style=discord.ButtonStyle.primary, disabled=(self.page <= 1))
            left_btn.callback = self.prev_page
            nav_row.add_item(left_btn)

            go_btn = discord.ui.Button(label="Go To Page", style=discord.ButtonStyle.secondary)
            go_btn.callback = self.go_to_page_callback
            nav_row.add_item(go_btn)

            right_btn = discord.ui.Button(label="▶️", style=discord.ButtonStyle.primary,
                                          disabled=(self.page >= total_pages))
            right_btn.callback = self.next_page
            nav_row.add_item(right_btn)

            container.add_item(nav_row)

        container.add_item(discord.ui.Separator())

        sync_btn = discord.ui.Button(label="Sync Slash", style=discord.ButtonStyle.primary)
        shutdown_btn = discord.ui.Button(label="Shutdown", style=discord.ButtonStyle.danger)
        restart_btn = discord.ui.Button(label="Restart", style=discord.ButtonStyle.danger)
        log_btn = discord.ui.Button(label="Show Log", style=discord.ButtonStyle.secondary)

        sync_btn.callback = self.sync_callback
        shutdown_btn.callback = self.shutdown_callback
        restart_btn.callback = self.restart_callback
        log_btn.callback = self.show_log_callback

        action_row = discord.ui.ActionRow()
        action_row.add_item(sync_btn)
        action_row.add_item(shutdown_btn)
        action_row.add_item(restart_btn)
        action_row.add_item(log_btn)

        container.add_item(action_row)
        self.add_item(container)

    def create_toggle_callback(self, ext_name, is_loaded):
        async def callback(interaction: discord.Interaction):
            try:
                if is_loaded:
                    await self.bot.unload_extension(ext_name)
                    print(f"> Unloaded {ext_name} Successfully")
                else:
                    await self.bot.load_extension(ext_name)
                    print(f"> Loaded {ext_name} Successfully")
                self.build_layout()
                await interaction.response.edit_message(view=self)
            except Exception as e:
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)

        return callback

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self.build_layout()
        await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self.build_layout()
        await interaction.response.edit_message(view=self)

    async def go_to_page_callback(self, interaction: discord.Interaction):
        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        cog_files = [f for f in os.listdir(cogs_dir) if f.endswith(".py") and not f.startswith("__")] if os.path.exists(
            cogs_dir) else []
        total_pages = (len(cog_files) + self.items_per_page - 1) // self.items_per_page

        modal = OwnerGoToPageModal(self, total_pages)
        await interaction.response.send_modal(modal)

    async def sync_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.tree.sync()
            await interaction.followup.send("Synced slash commands successfully.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Sync failed: {e}")

    async def shutdown_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Shutting down...", ephemeral=True)
        await signal_handler()

    async def restart_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Restarting process...", ephemeral=True)
        await restart_bot()

    async def show_log_callback(self, interaction: discord.Interaction):
        log_path = os.path.join(os.path.dirname(__file__), "discord.log")

        if not os.path.exists(log_path):
            return await interaction.response.send_message("Log file not found.", ephemeral=True)

        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log_content = f.read()

            if len(log_content) > 1900:
                file = discord.File(log_path, filename="discord.log")
                await interaction.response.send_message("Log exceeds 1900 characters, sending as an attachment:", file=file,
                                                        ephemeral=True)
            elif not log_content.strip():
                await interaction.response.send_message("Log file is empty.", ephemeral=True)
            else:
                await interaction.response.send_message(f"```\n{log_content}\n```", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"Failed to read log: {e}", ephemeral=True)

class OwnerGoToPageModal(discord.ui.Modal):
    def __init__(self, parent_view: OwnerDashboard, total_pages: int):
        super().__init__(title="Jump to Page")
        self.parent_view = parent_view
        self.total_pages = max(total_pages, 1)

        self.page_input = discord.ui.TextInput(
            label=f"Page Number (1-{self.total_pages})",
            placeholder="Enter a page number...",
            min_length=1,
            max_length=5,
            required=True,
        )
        self.add_item(self.page_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page_num = int(self.page_input.value)
            if 1 <= page_num <= self.total_pages:
                self.parent_view.page = page_num
                self.parent_view.build_layout()
                await interaction.response.edit_message(view=self.parent_view)
            else:
                await interaction.response.send_message(f"Please enter a number between 1 and {self.total_pages}.",
                                                        ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Invalid input.", ephemeral=True)


async def restart_bot():
    print("Restarting bot...")
    await signal_handler()
    os.execv(sys.executable, [sys.executable] + sys.argv)


async def setup_hook():
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
    print(f"Bot ready: {bot.user} (ID: {bot.user.id})")
    print(f"Bot Owner identified: {owner_user_name}")
    print(f"---------------------------------------------------")

    logger.info("")
    logger.info("")
    logger.info(f"---------------------------------------------------")
    logger.info(f"Bot ready: {bot.user} (ID: {bot.user.id})")
    logger.info(f"Bot Owner identified: {owner_user_name}")
    logger.info(f"---------------------------------------------------")
    logger.info("")
    logger.info("")

    await bot.change_presence(
        status=discord.Status.dnd,
        activity=discord.CustomActivity(name="✨ Testing v3.0.0-alpha!")
    )


@bot.tree.command(name="zc", description=".")
async def zc(interaction: discord.Interaction):
    if interaction.user.id != bot.owner_id:
        await interaction.response.send_message(
            "🤫",
            ephemeral=True
        )
        return

    view = OwnerDashboard(bot, interaction.user)
    await interaction.response.send_message(view=view)


@bot.tree.command(name="fuckoff",
                  description="Is the bot annoying you? Tell it to fuck off and shut itself down using this.")
async def fuckoff(interaction: discord.Interaction):
    if interaction.user.id != bot.owner_id:
        await interaction.response.send_message(
            "What do you think you're doing? Who do you think you are?? Why do you want to kill me???\nYou're not my dev. Don't tell me what to do. Go away.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "K 👍\nFucking off now.",
        ephemeral=True
    )

    asyncio.create_task(signal_handler())


if __name__ == "__main__":
    async def main_async():
        try:
            async with bot:
                await bot.start(TOKEN)
        except Exception as e:
            print(f"ERROR: Failed to start the bot: {e}")


    asyncio.run(main_async())