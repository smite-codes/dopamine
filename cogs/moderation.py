import asyncio
import aiosqlite
import discord
import time
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Set, List, Any
from contextlib import asynccontextmanager
from config import DB_PATH
from utils.checks import slash_mod_check
from utils.log import LoggingManager


class PointValueModal(discord.ui.Modal, title="Set New Point Value"):
    def __init__(self, index: int, cog, original_msg: discord.Message = None):
        super().__init__()
        self.index = index
        self.cog = cog
        self.message = original_msg
        self.value = discord.ui.TextInput(
            label=f"New point value for Action {index}",
            placeholder="Enter 0-1000 (0 to disable)",
            min_length=1, max_length=4
        )
        self.add_item(self.value)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_val = int(self.value.value)
            if not (0 <= new_val <= 1000): raise ValueError
        except ValueError:
            return await interaction.response.send_message("Invalid number (0-1000).", ephemeral=True)

        guild_id = interaction.guild.id
        current = self.cog.threshold_cache.get(guild_id, [0] * 12)

        if new_val != 0:
            if self.index > 1:
                prev = current[self.index - 2]
                if prev > 0 and new_val <= prev:
                    return await interaction.response.send_message("Must be higher than previous action.",
                                                                   ephemeral=True)
            if self.index < 12:
                nxt = current[self.index]
                if nxt > 0 and new_val >= nxt:
                    return await interaction.response.send_message("Must be lower than next action.", ephemeral=True)

        async with self.cog.acquire_db() as db:
            col = f"p{self.index}"
            await db.execute(
                f"INSERT INTO pointvalues (guild_id, {col}) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET {col}=?",
                (guild_id, new_val, new_val))
            await db.commit()

        # Refresh local cache
        async with self.cog.acquire_db() as db:
            async with db.execute("SELECT * FROM pointvalues WHERE guild_id = ?", (guild_id,)) as cursor:
                row = await cursor.fetchone()
                if row: self.cog.threshold_cache[guild_id] = list(row[1:])

        status = "disabled" if new_val == 0 else f"**{new_val}** points"
        await interaction.response.send_message(f"Updated action {self.index} to {status}.", ephemeral=True)

        if self.message:
            embed = self.cog.build_pointvalues_embed(interaction.guild.name, self.cog.threshold_cache[guild_id])
            await self.message.edit(embed=embed)


class PointValueButtons(discord.ui.View):
    def __init__(self, cog):
        self.cog = cog
        super().__init__(timeout=None)
        for i in range(1, 13):
            btn = discord.ui.Button(label=str(i), style=discord.ButtonStyle.blurple, custom_id=f"pv_{i}")
            btn.callback = self.make_callback(i, cog)
            self.add_item(btn)

    def make_callback(self, index, cog):
        async def callback(interaction: discord.Interaction):
            await interaction.response.send_modal(cog.PointValueModal(index, cog, interaction.message))

        return callback

class Points(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Caches
        self.user_cache: Dict[str, Dict[str, Any]] = {}
        self.threshold_cache: Dict[int, List[int]] = {}
        self.settings_cache: Dict[int, Dict[str, Any]] = {}

        self.db_pool: Optional[asyncio.Queue] = None

    async def cog_load(self):
        await self.init_pools()
        await self.init_db()
        await self.populate_caches()
        self.unban_loop.start()
        self.decay_loop.start()

    async def cog_unload(self):
        self.unban_loop.stop()
        self.decay_loop.stop()
        if self.db_pool:
            while not self.db_pool.empty():
                conn = await self.db_pool.get()
                await conn.close()

    async def init_pools(self, pool_size: int = 5):
        if self.db_pool is None:
            self.db_pool = asyncio.Queue(maxsize=pool_size)
            for _ in range(pool_size):
                conn = await aiosqlite.connect(DB_PATH, timeout=5)
                await conn.execute("PRAGMA busy_timeout=5000")
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous = NORMAL")
                await conn.commit()
                await self.db_pool.put(conn)

    @asynccontextmanager
    async def acquire_db(self):
        conn = await self.db_pool.get()
        try:
            yield conn
        finally:
            await self.db_pool.put(conn)

    async def init_db(self):
        async with self.acquire_db() as db:
            await db.executescript('''
                                   CREATE TABLE IF NOT EXISTS users
                                   (
                                       guild_id INTEGER,
                                       user_id INTEGER,
                                       points INTEGER DEFAULT 0,
                                       last_punishment INTEGER,
                                       last_decay INTEGER, 
                                       PRIMARY KEY (guild_id, user_id)
                                       );
                                   CREATE TABLE IF NOT EXISTS pointvalues
                                   (
                                       guild_id INTEGER PRIMARY KEY,
                                       p1 INTEGER DEFAULT 1,
                                       p2 INTEGER DEFAULT 2,
                                       p3 INTEGER DEFAULT 3,
                                       p4 INTEGER DEFAULT 4,
                                       p5 INTEGER DEFAULT 5,
                                       p6 INTEGER DEFAULT 6,
                                       p7 INTEGER DEFAULT 7,
                                       p8 INTEGER DEFAULT 8,
                                       p9 INTEGER DEFAULT 9,
                                       p10 INTEGER DEFAULT 10,
                                       p11 INTEGER DEFAULT 11,
                                       p12 INTEGER DEFAULT 12
                                   );
                                   CREATE TABLE IF NOT EXISTS ban_schedule
                                   (
                                       guild_id INTEGER, 
                                       user_id INTEGER,
                                       unban_at INTEGER,
                                       PRIMARY KEY (guild_id, user_id)
                                       );
                                   CREATE TABLE IF NOT EXISTS settings
                                   (
                                       guild_id INTEGER PRIMARY KEY,
                                       decay_interval INTEGER DEFAULT 14,
                                       word TEXT DEFAULT "points"
                                   );
                                   ''')
            await db.commit()

    async def populate_caches(self):
        self.user_cache.clear()
        self.threshold_cache.clear()
        self.settings_cache.clear()

        async with self.acquire_db() as db:
            async with db.execute("SELECT * FROM users") as cursor:
                async for row in cursor:
                    self.user_cache[f"{row[0]}:{row[1]}"] = {
                        "points": row[2],
                        "last_punishment": row[3],
                        "last_decay": row[4]
                    }

            async with db.execute("SELECT * FROM pointvalues") as cursor:
                async for row in cursor:
                    self.threshold_cache[row[0]] = list(row[1:])

            async with db.execute("SELECT * FROM settings") as cursor:
                async for row in cursor:
                    self.settings_cache[row[0]] = {"decay_interval": row[1], "word": row[2]}

    async def get_user_data(self, guild_id: int, user_id: int) -> dict:
        key = f"{guild_id}:{user_id}"
        if key not in self.user_cache:
            data = {"points": 0, "last_punishment": None, "last_decay": None}
            self.user_cache[key] = data
            async with self.acquire_db() as db:
                await db.execute(
                    "INSERT OR IGNORE INTO users (guild_id, user_id, points) VALUES (?, ?, ?)",
                    (guild_id, user_id, 0)
                )
                await db.commit()
        return self.user_cache[key]

    async def update_user_points(self, guild_id: int, user_id: int, points: int, punishment_ts: Optional[int] = None):
        key = f"{guild_id}:{user_id}"
        data = await self.get_user_data(guild_id, user_id)
        data["points"] = points
        if punishment_ts:
            data["last_punishment"] = punishment_ts
            data["last_decay"] = None

        self.user_cache[key] = data

        async with self.acquire_db() as db:
            await db.execute('''
                             UPDATE users
                             SET points          = ?,
                                 last_punishment = ?,
                                 last_decay      = ?
                             WHERE guild_id = ?
                               AND user_id = ?
                             ''', (points, data["last_punishment"], data["last_decay"], guild_id, user_id))
            await db.commit()

    def get_punishment_data(self, points: int, guild_id: int):
        thresholds = self.threshold_cache.get(guild_id, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])

        punishments = {
            1: ("warning", None),
            2: ("timeout", timedelta(minutes=15)),
            3: ("timeout", timedelta(minutes=30)),
            4: ("timeout", timedelta(minutes=45)),
            5: ("timeout", timedelta(minutes=60)),
            6: ("ban", timedelta(hours=12)),
            7: ("ban", timedelta(hours=12)),
            8: ("ban", timedelta(days=1)),
            9: ("ban", timedelta(days=3)),
            10: ("ban", timedelta(days=7)),
            11: ("ban", timedelta(days=7)),
            12: ("ban", None),
        }

        prev_idx = 1
        for i, threshold in enumerate(thresholds, start=1):
            if threshold == 0: continue
            if points < threshold:
                return punishments[prev_idx]
            prev_idx = i

        return punishments[prev_idx]

    async def get_log_channel(self, guild: discord.Guild):
        channel_id = await self.manager.logging_get(guild.id)
        channel = self.bot.get_channel(channel_id)
        if not channel:
            channel = self.bot.fetch_channel(channel_id)
        if not channel:
            return None
        return channel

    async def apply_punishment(self, interaction: discord.Interaction, member: discord.Member, amount: int, reason: str):
        action, duration = self.get_punishment_data(amount, interaction.guild.id)
        reason_text = f"Points: {amount} | {reason or 'No reason provided.'}"
        action_text = {
            "warning": "warned",
            "timeout": "timed out",
            "ban": "banned"
        }.get(action, action)

        def human_readable_duration(self, td: timedelta) -> str:
            total_seconds = int(td.total_seconds())
            if total_seconds == 0:
                return "0 seconds"

            units = [
                ("month", 60 * 60 * 24 * 30),
                ("day", 60 * 60 * 24),
                ("hour", 60 * 60),
                ("minute", 60),
                ("second", 1),
            ]

            parts = []
            for name, seconds_in_unit in units:
                value = total_seconds // seconds_in_unit
                if value > 0:
                    total_seconds %= seconds_in_unit
                    parts.append(f"{value} {name}{'s' if value > 1 else ''}")

            return ", ".join(parts)

        duration_str = human_readable_duration(duration) if duration else None
        def build_embed(interaction: discord.Interaction, action_text: str, duration_str: str = None):
            display_action = action_text
            if "ban" in action_text.lower() and duration_str is None:
                display_action = "permanently banned"

            if duration_str:
                first_line = f"{member.mention} has been **{display_action}** for **{duration_str}**."
            else:
                first_line = f"{member.mention} has been **{display_action}.**"

            dm_preposition = "from" if "ban" in action_text.lower() else "in"

            if duration_str:
                dm_first_line = f"You have been **{display_action}** {dm_preposition} **{interaction.guild.name}** for **{duration_str}**."
            else:
                dm_first_line = f"You have been **{display_action}** {dm_preposition} **{interaction.guild.name}**."

            description = (
                f"User has **{amount}** point(s) – {first_line}\n\n"
                f"**Reason:** {reason or 'No reason provided.'}"
            )

            dm_description = (
                f"You have **{amount}** point(s) – {dm_first_line}\n\n"
                f"**Reason:** {reason or 'No reason provided.'}"
            )
            is_ban = "ban" in action_text.lower()
            main_color = discord.Color.red() if is_ban else discord.Color.orange()

            embed = discord.Embed(description=description, color=main_color)
            embed.set_author(name=f"{member} ({member.id})", icon_url=member.display_avatar.url)
            embed.set_footer(text=f"by {interaction.user}", icon_url=interaction.user.display_avatar.url)

            dm_embed = discord.Embed(description=dm_description, color=main_color)
            dm_embed.set_footer(text=f"by {interaction.user}", icon_url=interaction.user.display_avatar.url)

            return embed, dm_embed

        log_embed, dm_embed = build_embed(interaction, action_text, duration_str)
        try:
            await member.send(embed=dm_embed)
        except:
            pass
        if action == "timeout" and duration:
            await member.timeout(discord.utils.utcnow() + duration, reason=reason_text)

        elif action == "ban":
            await interaction.guild.ban(member, reason=reason_text, delete_message_days=0)
            if duration:
                unban_ts = int((discord.utils.utcnow() + duration).timestamp())
                async with self.acquire_db() as db:
                    await db.execute(
                        "INSERT OR REPLACE INTO ban_schedule (guild_id, user_id, unban_at) VALUES (?, ?, ?)",
                        (interaction.guild.id, member.id, unban_ts)
                    )
                    await db.commit()
        log_ch = await self.get_log_channel(interaction.guild)
        if log_ch:
            await log_ch.send(embed=log_embed)

    @tasks.loop(seconds=60)
    async def unban_loop(self):
        now = int(discord.utils.utcnow().timestamp())
        async with self.acquire_db() as db:
            async with db.execute(
                    "SELECT guild_id, user_id FROM ban_schedule WHERE unban_at <= ?",
                    (now,)
            ) as cursor:
                rows = await cursor.fetchall()

            for guild_id, user_id in rows:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    try:
                        await guild.unban(discord.Object(id=user_id), reason="Temporary ban expired")
                    except discord.NotFound:
                        pass
                    except Exception as e:
                        print(f"Error unbanning {user_id} in {guild_id}: {e}")

                await db.execute(
                    "DELETE FROM ban_schedule WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id)
                )
            await db.commit()

    @tasks.loop(hours=6)
    async def decay_loop(self):
        now = int(discord.utils.utcnow().timestamp())

        async with self.acquire_db() as db:
            for key, data in list(self.user_cache.items()):
                guild_id_str, user_id_str = key.split(":")
                guild_id, user_id = int(guild_id_str), int(user_id_str)

                points = data["points"]
                last_p = data["last_punishment"]
                last_d = data["last_decay"]

                if points <= 0 or not last_p:
                    continue

                settings = self.settings_cache.get(guild_id, {})
                days = settings.get("decay_interval", 14)
                interval_seconds = days * 86400

                reference_ts = last_d if (last_d and last_d > last_p) else last_p

                elapsed = now - reference_ts
                periods = elapsed // interval_seconds

                if periods > 0:
                    new_points = max(0, points - periods)
                    new_decay_ts = reference_ts + (periods * interval_seconds)

                    data["points"] = new_points
                    data["last_decay"] = new_decay_ts if new_points > 0 else None

                    await db.execute('''
                                     UPDATE users
                                     SET points     = ?,
                                         last_decay = ?
                                     WHERE guild_id = ?
                                       AND user_id = ?
                                     ''', (new_points, data["last_decay"], guild_id, user_id))

            await db.commit()

    @app_commands.command(name="point", description="Add points to a user.")
    @app_commands.check(slash_mod_check)
    async def point(self, interaction: discord.Interaction, member: discord.Member, amount: int, reason: Optional[str] = None):
        def format_punishment_text(action: str | None, duration: timedelta | None) -> tuple[
            str | None, str | None, str]:
            if action and action.lower() == "ban":
                if duration is None:
                    action_text = "banned permanently"
                else:
                    action_text = "banned"
            else:
                action_text = action

            duration_text = None
            if action in ["timeout", "ban"] and duration is not None:
                total_seconds = int(duration.total_seconds()) if isinstance(duration, timedelta) else int(duration)
                if total_seconds < 60:
                    duration_text = f"{total_seconds} second{'s' if total_seconds != 1 else ''}"
                elif total_seconds < 3600:
                    minutes = total_seconds // 60
                    duration_text = f"{minutes} minute{'s' if minutes != 1 else ''}"
                elif total_seconds < 86400:
                    hours = total_seconds // 3600
                    duration_text = f"{hours} hour{'s' if hours != 1 else ''}"
                else:
                    days = total_seconds // 86400
                    duration_text = f"{days} day{'s' if days != 1 else ''}"

            if duration_text:
                punishment_text = f"{action_text} for {duration_text}"
            else:
                punishment_text = f"{action_text}" if action_text else "No punishment (No threshold reached)"

            return action_text, duration_text, punishment_text

        await interaction.response.defer()

        data = await self.get_user_data(interaction.guild.id, member.id)
        new_points = max(0, data["points"] + amount)
        now = int(time.time())

        await self.update_user_points(interaction.guild.id, member.id, new_points, punishment_ts=now)

        action, duration = self.get_punishment_data(new_points, interaction.guild.id)

        punishment_text, duration_text, action_text = format_punishment_text(action, duration)

        embed = discord.Embed(
            description=f"**{member.mention}** now has **{new_points}** points – {punishment_text}.\n\n**Reason**: {reason or 'No reason provided.'}",
            color=discord.Color.red()
        )
        embed.set_author(name=f"{member.display_name} ({member.id})", icon_url=member.display_avatar.url)
        embed.set_footer(text=f"by {interaction.user}")

        await interaction.edit_original_response(embed=embed)
        await self.apply_punishment(interaction, member, new_points, reason)

    @app_commands.command(name="pardon", description="Remove points from a user.")
    @app_commands.check(slash_mod_check)
    async def pardon(self, interaction: discord.Interaction, member: discord.Member, amount: int, reason: Optional[str] = None):
        data = await self.get_user_data(interaction.guild.id, member.id)
        old_points = data["points"]
        new_points = max(0, old_points - amount)

        await self.update_user_points(interaction.guild.id, member.id, new_points)

        embed = discord.Embed(
            description=f"## Points Updated\n\nPoints removed: **{amount}**\nOld: **{old_points}** | New: **{new_points}**\n\n{f"**Reason**: {reason}" if reason else "**Reason**: No reason provided."}",
            color=discord.Color.blue()
        )
        embed.set_author(name=f"{member.name} ({member.id})", icon_url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)
        log_ch = await self.get_log_channel(interaction.guild)
        if log_ch:
            log_embed = discord.Embed(
                description=(f"## Points Updated\n\nPoints removed: **{amount}** point(s)\n\n"
                             f"Old Points**:{old_points}**\nNew Points**:{new_points}**\n\n**Reason**: {reason}"),
                color=discord.Color(0x337fd5)
            )
            log_embed.set_author(name=f"{member.name} ({member.id})", icon_url=member.display_avatar.url)
            log_embed.set_footer(text=f"by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await log_ch.send(embed=log_embed)

    @app_commands.command(name="unban", description="Unban a user.")
    @app_commands.check(slash_mod_check)
    async def unban(self, interaction: discord.Interaction, user: discord.User, reason: Optional[str] = None):
        try:
            await interaction.guild.unban(user, reason=f"Unbanned by {interaction.user}: {reason}")

            async with self.acquire_db() as db:
                await db.execute("DELETE FROM ban_schedule WHERE guild_id = ? AND user_id = ?",
                                 (interaction.guild.id, user.id))
                await db.commit()

            await self.update_user_points(interaction.guild.id, user.id, 4)

            await interaction.response.send_message(
                embed=discord.Embed(description=f"**{user.name}** has been unbanned.", color=discord.Color.green()))
        except discord.NotFound:
            return await interaction.response.send_message("User is not banned.", ephemeral=True)
        except discord.Forbidden:
            return await interaction.response.send_message("I lack permissions to unban.", ephemeral=True)
        log_ch = await self.get_log_channel(interaction.guild)
        if log_ch:
            log_embed = discord.Embed(description=f"**{user.name}** has been unbanned.\n\n**Reason**: {reason}",
                                      color=discord.Color(0x337fd5))
            log_embed.set_author(name=f"{user.name} ({user.id})", icon_url=user.display_avatar.url)
            log_embed.set_footer(text=f"by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await log_ch.send(embed=log_embed)

    @app_commands.command(name="points", description="Show points info.")
    @app_commands.check(slash_mod_check)
    async def points_lookup_slash(self, interaction: discord.Interaction, user: discord.User):
        data = await self.get_user_data(interaction.guild.id, user.id)

        last_p = f"<t:{data['last_punishment']}:f>" if data['last_punishment'] else "never"
        last_d = f"<t:{data['last_decay']}:f>" if data['last_decay'] else "never"

        embed = discord.Embed(
            description=f"## Points info\n\nPoints: **{data['points']}**\nLast punishment: **{last_p}**\nLast decay: **{last_d}**",
            color=discord.Color.blue()
        )
        embed.set_author(name=f"{user.name} ({user.id})", icon_url=user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="pointvalues", description="Edit thresholds.")
    @app_commands.check(slash_mod_check)
    async def pointvalues(self, interaction: discord.Interaction):
        def build_pointvalues_embed(guild_name: str, thresholds: list) -> discord.Embed:
            punishment_labels = [
                "Warning:", "15-minute Timeout:", "30-minute Timeout:", "45-minute Timeout:",
                "60-minute Timeout:", "12-hour Ban:", "12-hour Ban:", "1-day Ban:",
                "3-day Ban:", "7-day Ban:", "7-day Ban:", "Permanent Ban:"
            ]
            desc = "".join([
                f"**{i}. {label}** **{'disabled' if thresholds[i - 1] == 0 else str(thresholds[i - 1]) + ' Points'}**\n\n"
                for i, label in enumerate(punishment_labels, 1)
            ])

            return discord.Embed(
                title=f"Punishment Point Settings for {guild_name}",
                description=desc,
                color=discord.Color(0x337fd5)
            )

        thresholds = self.threshold_cache.get(interaction.guild.id, [0] * 12)
        embed = build_pointvalues_embed(interaction.guild.name, thresholds)
        await interaction.response.send_message(embed=embed, view=self.PointValueButtons(self))