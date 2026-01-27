import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import asyncio
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from config import MCTDB_PATH
from utils.checks import slash_mod_check
import re


class MemberTrackerEditModal(discord.ui.Modal, title="Edit Member Tracker Settings"):
    member_goal = discord.ui.TextInput(
        label="Member Goal",
        placeholder="Set a member count goal... (leave blank to keep unchanged)",
        required=False,
        max_length=10
    )
    format_template = discord.ui.TextInput(
        label="Format (Documentation: /membertracker info) ",
        style=discord.TextStyle.paragraph,
        placeholder="Enter a format here... (leave blank to keep unchanged)",
        required=False,
        max_length=1000
    )
    embed_color = discord.ui.TextInput(
        label="Embed Color",
        placeholder="Enter a HEX value... (leave blank to keep unchanged)",
        required=False,
        max_length=9
    )

    def __init__(self, cog: "MemberCountTracker"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        updates = []
        guild_id = interaction.guild.id

        if not await self.cog.check_vote_access(interaction.user.id):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Vote to Use This Feature!",
                    description=f"This command requires voting! To access this feature, please vote for Dopamine [__here__](https://top.gg/bot/{self.cog.bot.user.id}).",
                    color=0xffaa00
                ),
                ephemeral=True
            )
            return

        if guild_id not in self.cog.tracker_cache or not self.cog.tracker_cache[guild_id].get('is_active'):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Tracker Not Enabled",
                    description="Enable the tracker with `/membertracker enable` before editing settings.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return

        async with self.cog.acquire_db() as db:
            if self.member_goal.value:
                try:
                    goal_val = int(self.member_goal.value)
                    if goal_val <= 0: raise ValueError
                except ValueError:
                    return await interaction.response.send_message("Enter a positive integer.", ephemeral=True)

                await db.execute("UPDATE member_tracker SET member_goal = ? WHERE guild_id = ?", (goal_val, guild_id))
                self.cog.tracker_cache[guild_id]['member_goal'] = goal_val
                updates.append(f"Member goal set to **{goal_val}**")

            if self.format_template.value:
                template = self.format_template.value.strip()
                if not any(token in template for token in ("{member_count}", "{remaining_until_goal}")):
                    return await interaction.response.send_message("Invalid format tokens.", ephemeral=True)

                await db.execute("UPDATE member_tracker SET custom_format = ? WHERE guild_id = ?", (template, guild_id))
                self.cog.tracker_cache[guild_id]['custom_format'] = template
                updates.append("Custom format updated")

            if self.embed_color.value:
                hex_value = self.embed_color.value.strip().lstrip("#")
                if not re.fullmatch(r"[0-9a-fA-F]{6}", hex_value):
                    return await interaction.response.send_message("Invalid hex color.", ephemeral=True)

                color_int = int(hex_value, 16)
                await db.execute("UPDATE member_tracker SET color = ? WHERE guild_id = ?", (color_int, guild_id))
                self.cog.tracker_cache[guild_id]['color'] = color_int
                updates.append(f"Embed color set to `#{hex_value.upper()}`")

            await db.commit()

        await interaction.response.send_message(
            embed=discord.Embed(
                title="Member Tracker Updated",
                description="\n".join(updates) if updates else "No changes made.",
                color=discord.Color.green()
            ),
            ephemeral=True
        )


class MemberCountTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_pool: Optional[asyncio.Queue] = None
        self.tracker_cache: Dict[int, dict] = {}

    async def cog_load(self):
        await self.init_pools()
        await self.init_db()
        await self.populate_caches()
        if not self.member_count_monitor.is_running():
            self.member_count_monitor.start()

    async def cog_unload(self):
        if self.member_count_monitor.is_running():
            self.member_count_monitor.cancel()

        if self.db_pool:
            while not self.db_pool.empty():
                conn = await self.db_pool.get()
                await conn.close()

    async def init_pools(self, pool_size: int = 5):
        if self.db_pool is None:
            self.db_pool = asyncio.Queue(maxsize=pool_size)
            for _ in range(pool_size):
                conn = await aiosqlite.connect(MCTDB_PATH, timeout=5.0)
                await conn.execute("PRAGMA busy_timeout=5000")
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA foreign_keys=ON")
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
            await db.execute('''
                             CREATE TABLE IF NOT EXISTS member_tracker
                             (
                                 guild_id INTEGER PRIMARY KEY,
                                 channel_id INTEGER,
                                 is_active INTEGER DEFAULT 0,
                                 member_goal INTEGER,
                                 custom_format TEXT,
                                 last_member_count INTEGER,
                                 color INTEGER
                             )
                             ''')
            await db.commit()

    async def populate_caches(self):
        self.tracker_cache.clear()
        async with self.acquire_db() as db:
            async with db.execute("SELECT * FROM member_tracker WHERE is_active = 1") as cursor:
                rows = await cursor.fetchall()
                columns = [column[0] for column in cursor.description]
                for row in rows:
                    data = dict(zip(columns, row))
                    self.tracker_cache[data["guild_id"]] = data

    async def check_vote_access(self, user_id: int) -> bool:
        voter_cog = self.bot.get_cog('TopGGVoter')
        return await voter_cog.check_vote_access(user_id) if voter_cog else True

    membertracker_group = app_commands.Group(name="membertracker", description="Member count tracker commands")

    @membertracker_group.command(name="enable", description="Enable member tracker")
    @app_commands.check(slash_mod_check)
    async def enable_member_tracker(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self.check_vote_access(interaction.user.id):
            return await interaction.response.send_message("Voting required!", ephemeral=True)

        guild_id = interaction.guild.id
        count = interaction.guild.member_count
        default_color = 0x337fd5

        async with self.acquire_db() as db:
            await db.execute('''
                INSERT OR REPLACE INTO member_tracker 
                (guild_id, channel_id, is_active, last_member_count, color)
                VALUES (?, ?, 1, ?, ?)
            ''', (guild_id, channel.id, count, default_color))
            await db.commit()

        self.tracker_cache[guild_id] = {
            "guild_id": guild_id,
            "channel_id": channel.id,
            "is_active": 1,
            "last_member_count": count,
            "color": default_color,
            "member_goal": None,
            "custom_format": None
        }

        await interaction.response.send_message(f"Tracker enabled in {channel.mention}", ephemeral=True)

    @membertracker_group.command(name="disable", description="Disable member tracker")
    @app_commands.check(slash_mod_check)
    async def disable_member_tracker(self, interaction: discord.Interaction):
        async with self.acquire_db() as db:
            await db.execute("UPDATE member_tracker SET is_active = 0 WHERE guild_id = ?", (interaction.guild.id,))
            await db.commit()

        self.tracker_cache[interaction.guild_id] = {"is_active": 0}
        await interaction.response.send_message("Member tracker has been disabled.", ephemeral=True)

    @membertracker_group.command(name="info", description="View tracker info")
    @app_commands.check(slash_mod_check)
    async def member_tracker_info(self, interaction: discord.Interaction):
        data = self.tracker_cache.get(interaction.guild.id)

        if not data:
            return await interaction.response.send_message("Tracker not active. Use `/membertracker enable`.",
                                                           ephemeral=True)

        channel = self.bot.get_channel(data['channel_id'])
        embed = discord.Embed(
            title="Member Count Tracker Information",
            description=f"**Status:** 🟢 Active\n**Channel:** {channel.mention if channel else 'Unknown'}",
            color=data['color'] or 0x337fd5
        )
        if data['member_goal']:
            embed.add_field(name="Goal", value=f"{data['member_goal']} members")
        if data['custom_format']:
            embed.add_field(name="Format", value=f"```\n{data['custom_format']}\n```", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @membertracker_group.command(name="edit", description="Edit settings")
    @app_commands.check(slash_mod_check)
    async def edit_member_tracker(self, interaction: discord.Interaction):
        await interaction.response.send_modal(MemberTrackerEditModal(self))

    @tasks.loop(minutes=5)
    async def member_count_monitor(self):
        await self.bot.wait_until_ready()

        active_trackers = list(self.tracker_cache.values())

        for data in active_trackers:
            guild_id = data['guild_id']
            guild = self.bot.get_guild(guild_id)
            if not guild: continue

            current_count = guild.member_count
            if current_count <= (data['last_member_count'] or 0):
                continue

            channel = guild.get_channel(data['channel_id'])
            if not channel: continue

            fmt = data['custom_format']
            goal = data['member_goal']
            remaining = max(0, goal - current_count) if goal else None

            if fmt:
                msg = fmt.replace('{member_count}', str(current_count)).replace('{servername}', guild.name)
                msg = msg.replace('{remaining_until_goal}', str(remaining) if remaining is not None else "N/A")
                msg = msg.replace('{member_goal}', str(goal) if goal else "N/A")
            else:
                msg = f"{guild.name} now has **{current_count}** members!"

            embed = discord.Embed(description=msg, color=data['color'] or 0x337fd5)

            try:
                await channel.send(embed=embed)

                async with self.acquire_db() as db:
                    if goal and current_count >= goal:
                        await channel.send(
                            embed=discord.Embed(description=f"Goal of {goal} reached! 🎉", color=discord.Color.gold()))
                        await db.execute(
                            "UPDATE member_tracker SET is_active = 0, last_member_count = ? WHERE guild_id = ?",
                            (current_count, guild_id))
                        self.tracker_cache.pop(guild_id, None)
                    else:
                        await db.execute("UPDATE member_tracker SET last_member_count = ? WHERE guild_id = ?",
                                         (current_count, guild_id))
                        self.tracker_cache[guild_id]['last_member_count'] = current_count
                    await db.commit()
            except Exception as e:
                print(f"Error in monitor for {guild_id}: {e}")

    @membertracker_group.command(name="delete", description="Delete and reset all server data")
    @app_commands.check(slash_mod_check)
    async def reset_member_tracker(self, interaction: discord.Interaction):
        async with self.acquire_db() as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [r[0] for r in await cursor.fetchall()]

            for table in tables:
                cursor = await db.execute(f"PRAGMA table_info({table})")
                cols = await cursor.fetchall()
                if any(c[1].lower() == "guild_id" for c in cols):
                    await db.execute(f"DELETE FROM {table} WHERE guild_id = ?", (interaction.guild.id,))

            await db.commit()

        self.tracker_cache.pop(interaction.guild.id, None)
        await interaction.response.send_message("All server data reset.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(MemberCountTracker(bot))