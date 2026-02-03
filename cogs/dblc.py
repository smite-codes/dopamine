import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.checks import slash_mod_check, mod_check
from utils.log import LoggingManager
from VERSION import bot_version
import time
import psutil
import asyncio
import os
from collections import deque

class Dblc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.latency_cache = deque(maxlen=86400)
        self.cache_task.start()

    def cog_unload(self):
        self.cache_task.cancel()

    @tasks.loop(seconds=1.0)
    async def cache_task(self):
        if not self.bot.is_ready():
            return

        try:
            ws_latency = self.bot.latency * 1000

            start = time.perf_counter()
            await self.bot.fetch_user(self.bot.user.id)
            api_latency = (time.perf_counter() - start) * 1000

            total_latency = ws_latency + api_latency
            self.latency_cache.append(total_latency)
        except Exception:
            pass

    @cache_task.before_loop
    async def before_cache_task(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(10)

    @app_commands.command(name="avatar", description="Get a user's avatar.")
    @app_commands.describe(user="The user whose avatar you want to see.")
    async def avatar(self, interaction: discord.Interaction, user: discord.User):
        embed = discord.Embed(
            title=f"{user.name}",
            description="### User Avatar",
            color=discord.Color(0x337fd5)
        )
        embed.set_image(url=user.avatar.url if user.avatar else user.default_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="purge", description="Delete recent messages.")
    @app_commands.check(slash_mod_check)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(number="Number of messages to delete (max 100)")
    async def purge(self, interaction: discord.Interaction, number: int):
        number = max(1, min(number, 100))

        await interaction.response.defer(ephemeral=True)

        try:

            messages = [msg async for msg in interaction.channel.history(limit=number)]

            if not messages:
                return await interaction.edit_original_response("No messages found to delete.", ephemeral=True)

            await interaction.channel.delete_messages(messages)
            deleted_count = len(messages)

        except discord.Forbidden:
            return await interaction.edit_original_response("I don't have permission to delete messages here.", ephemeral=True)
        except discord.HTTPException as e:
            if e.code == 50034:
                return await interaction.edit_original_response(
                    "Cannot delete messages older than 14 days using bulk delete.",
                    ephemeral=True
                )
            return await interaction.edit_original_response(f"An error occurred: {e}", ephemeral=True)
        channel_id = await self.bot.manager.logging_get(interaction.guild.id)
        log_ch = self.bot.get_channel(channel_id)
        if not log_ch:
            log_ch = self.bot.fetch_channel(channel_id)
        if log_ch:
            log_embed = discord.Embed(
                description=f"**{deleted_count}** message(s) purged in {interaction.channel.mention}.",
                color=discord.Color.red()
            )
            log_embed.set_footer(text=f"By {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await log_ch.send(embed=log_embed)

        await interaction.edit_original_response(f"Successfully purged **{deleted_count}** messages.", ephemeral=True)

    @app_commands.command(name="ban", description="Fake-ban someone (cosmetic).")
    @app_commands.describe(member="Who to fake-ban", duration="How long (text)", reason="Optional reason")
    async def ban(self, interaction: discord.Interaction, member: discord.Member | None = None,
                        duration: str | None = None, reason: str | None = None):
        try:

            embed = discord.Embed(
                description=f"**{member.mention}** has been **banned**"
                            + (f" for {duration}" if duration else "")
                            + (f"\n\n**Reason:** {reason}\n\n" if reason else "."),
                color=discord.Color.red()
            )
            embed.set_author(name=f"{member.display_name} ({member.id})", icon_url=member.display_avatar.url)
            embed.set_footer(text=f"by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            if interaction.response.is_done():
                try:
                    await interaction.followup.send(
                        "An unexpected error occurred while running this command.", ephemeral=True
                    )
                except Exception:
                    pass
            else:
                try:
                    await interaction.response.send_message(
                        "An unexpected error occurred while running this command.", ephemeral=True
                    )
                except Exception:
                    pass

    @app_commands.command(name="echo", description="Make the bot say a message in a channel.")
    @app_commands.check(slash_mod_check)
    @app_commands.describe(channel="Where to send the message", message="What to say")
    async def echo(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        try:
            await channel.send(message)
            await interaction.response.send_message("Message echoed successfully.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: Could not send message: {e}", ephemeral=True)

    @app_commands.command(name="say", description="Ask the bot to say something")
    @app_commands.describe(channel="Where to send it", message="What to say")
    async def say(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        try:
            text = f"{interaction.user.mention} has desperately begged on their knees and asked me to say: {message}"
            await channel.send(text)
            await interaction.response.send_message("Sent.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: Could not send message: {e}", ephemeral=True)

    @app_commands.command(name="ping", description="Show bot latency.")
    async def ping_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pong!")
        latency_ms = round(self.bot.latency * 1000)
        await interaction.edit_original_response(content=f"Pong! `{latency_ms}ms`")

    @app_commands.command(name="servercount", description="Get the number of servers the bot is in.")
    async def servercount(self, interaction: discord.Interaction):
        server_count = len(self.bot.guilds)
        await interaction.response.send_message(f"I am currently in **{server_count}** servers.")

    latency = app_commands.Group(name="latency", description="Latency-related commands.")

    @latency.command(name="info", description="Get detailed latency and bot information")

    async def info(self, interaction: discord.Interaction):
        def format_uptime(seconds):
            weeks = seconds // (7 * 24 * 60 * 60)
            seconds %= (7 * 24 * 60 * 60)
            days = seconds // (24 * 60 * 60)
            seconds %= (24 * 60 * 60)
            hours = seconds // (60 * 60)
            seconds %= (60 * 60)
            minutes = seconds // 60
            seconds %= 60

            parts = []
            if weeks > 0:
                parts.append(f"{int(weeks)}w")
            if days > 0:
                parts.append(f"{int(days)}d")
            if hours > 0:
                parts.append(f"{int(hours)}h")
            if minutes > 0:
                parts.append(f"{int(minutes)}m")
            if seconds > 0 or not parts:
                parts.append(f"{int(seconds)}s")

            return " ".join(parts)

        initial_message = (
            "Pinging...\n"
            "Digging around for your IP address...\n"
            "Getting your location...\n"
            "Calculating distance to your home...\n"
            "Sending you some icecream...\n"
            "Done! Icecream sent."
        )

        if self.latency_cache:
            avg_latency = round(sum(self.latency_cache) / len(self.latency_cache), 2)
            sample_count = len(self.latency_cache)
        else:
            avg_latency = "Calculating..."
            sample_count = 0

        await interaction.response.send_message(initial_message)
        discord_latency = round(self.bot.latency * 1000, 2)
        try:
            start = time.perf_counter()
            await self.bot.http.request(discord.http.Route("GET", "/gateway"))
            end = time.perf_counter()
            connection_latency = round((end - start) * 1000, 2)
        except Exception:
            connection_latency = "Error"
        total_latency = round(discord_latency + connection_latency)

        if hasattr(self.bot, 'start_time'):
            uptime_seconds = int(time.time() - self.bot.start_time)
        else:
            uptime_seconds = 0
        uptime_formatted = format_uptime(uptime_seconds)

        try:
            process = psutil.Process(os.getpid())
            memory_bytes = process.memory_info().rss
            memory_mb = memory_bytes / (1024 * 1024)

            if memory_mb >= 1024:
                memory_gb = int(memory_mb // 1024)
                memory_remaining_mb = round(memory_mb % 1024, 2)
                memory_usage = f"{memory_gb}GB {memory_remaining_mb}MB"
            else:
                memory_usage = f"{round(memory_mb, 2)}MB"
        except Exception:
            memory_usage = "Unable to calculate"

        try:
            battery = psutil.sensors_battery()
            if battery:
                percent = battery.percent
                charging = battery.power_plugged
                battery_status = f"Host Device Battery Status: `{percent}% ({'Charging' if charging else 'Discharging'})`"
            else:
                battery_status = "Host Device Battery Status: `Device has no battery`"
        except Exception:
            battery_status = "Host Device Battery Status: `Unable to determine`"

        embed = discord.Embed(
            title="Latency Info",
            description=(
                f"> Bot Version: `{bot_version}`\n\n"
                f"> Discord Latency: `{discord_latency}ms`\n"
                f"> Connection Latency: `{connection_latency}ms`\n"
                f"> Total Latency: `{total_latency}ms`\n\n"
                f"> Average Latency: `{avg_latency}ms` (over `{sample_count}` samples)\n\n"
                f"> Uptime: `{uptime_formatted}`\n"
                f"> Memory Usage: `{memory_usage}`\n"
                f"> {battery_status}"
            ),
            color=discord.Color(0x8632e6)
        )

        message = await interaction.original_response()
        await message.edit(content=None, embed=embed)

async def setup(bot):
    await bot.add_cog(Dblc(bot))