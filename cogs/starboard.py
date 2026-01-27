import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import asyncio
from collections import deque
from typing import Optional, Dict, Set, Tuple, Any
import time
from contextlib import asynccontextmanager
from config import SDB_PATH


class StarboardCog(commands.Cog):
    """Starboard and LFG functionality with manual write-through caching."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.SDB_PATH = SDB_PATH
        self.STAR_EMOJI = "⭐"

        # Caches
        self.settings_cache: Dict[int, dict] = {}
        self.star_posts_cache: Dict[int, Dict[int, int]] = {}  # {guild_id: {source_id: starboard_id}}

        # LFG State
        self.starred_messages: deque[int] = deque(maxlen=10000)
        self.lfg_creators: dict[int, int] = {}
        self.guild_cooldowns: dict[int, float] = {}
        self.lfg_message_times: dict[int, float] = {}

        # Limits
        self._max_lfg_entries: int = 5000
        self.db_pool: Optional[asyncio.Queue[aiosqlite.Connection]] = None
        self._starboard_tasks: Dict[int, asyncio.Task] = {}

    async def cog_load(self):
        """Initialize pools, DB, and populate caches."""
        await self.init_pools()
        await self.init_db()
        await self.populate_caches()
        if not self._cache_cleanup.is_running():
            self._cache_cleanup.start()

    async def cog_unload(self):
        """Cleanup resources on unload."""
        if self._cache_cleanup.is_running():
            self._cache_cleanup.cancel()

        if self.db_pool is not None:
            while not self.db_pool.empty():
                conn = await self.db_pool.get()
                try:
                    await conn.close()
                except:
                    pass

    async def init_pools(self, pool_size: int = 5):
        """Initialize the unified database connection pool."""
        if self.db_pool is None:
            self.db_pool = asyncio.Queue(maxsize=pool_size)
            for _ in range(pool_size):
                conn = await aiosqlite.connect(
                    self.SDB_PATH,
                    timeout=5,
                    isolation_level=None
                )
                await conn.execute("PRAGMA busy_timeout=5000")
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA foreign_keys=ON")
                await conn.commit()
                await self.db_pool.put(conn)

    @asynccontextmanager
    async def acquire_db(self):
        """Context manager to acquire and return a connection to the pool."""
        if self.db_pool is None:
            await self.init_pools()
        conn = await self.db_pool.get()
        try:
            yield conn
        finally:
            await self.db_pool.put(conn)

    async def init_db(self):
        """Setup table structure."""
        async with self.acquire_db() as db:
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS guild_settings
                             (
                                 guild_id
                                 INTEGER
                                 PRIMARY
                                 KEY,
                                 star_threshold
                                 INTEGER
                                 DEFAULT
                                 3,
                                 starboard_channel_id
                                 INTEGER,
                                 lfg_threshold
                                 INTEGER
                                 DEFAULT
                                 4
                             )
                             """)
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS star_posts
                             (
                                 guild_id
                                 INTEGER
                                 NOT
                                 NULL,
                                 source_message_id
                                 INTEGER
                                 NOT
                                 NULL,
                                 starboard_message_id
                                 INTEGER
                                 NOT
                                 NULL,
                                 PRIMARY
                                 KEY
                             (
                                 guild_id,
                                 source_message_id
                             )
                                 )
                             """)
            await db.commit()

    async def populate_caches(self):
        """Load all data from DB into memory."""
        self.settings_cache.clear()
        self.star_posts_cache.clear()

        async with self.acquire_db() as db:
            # Load Settings
            async with db.execute("SELECT * FROM guild_settings") as cursor:
                rows = await cursor.fetchall()
                cols = [c[0] for c in cursor.description]
                for row in rows:
                    data = dict(zip(cols, row))
                    self.settings_cache[data["guild_id"]] = data

            # Load Star Posts
            async with db.execute("SELECT guild_id, source_message_id, starboard_message_id FROM star_posts") as cursor:
                async for gid, src_id, sb_id in cursor:
                    if gid not in self.star_posts_cache:
                        self.star_posts_cache[gid] = {}
                    self.star_posts_cache[gid][src_id] = sb_id

    # --- Database / Cache Write Logic ---

    async def get_guild_settings(self, guild_id: int) -> dict:
        """Fetch settings from cache, or create in DB and cache if missing."""
        if guild_id in self.settings_cache:
            return self.settings_cache[guild_id]

        defaults = {
            "guild_id": guild_id,
            "star_threshold": 3,
            "starboard_channel_id": None,
            "lfg_threshold": 4
        }

        async with self.acquire_db() as db:
            await db.execute(
                "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
                (guild_id,)
            )
            await db.commit()

        self.settings_cache[guild_id] = defaults
        return defaults

    async def update_guild_setting(self, guild_id: int, **kwargs):
        """Update both DB and cache manually (Write-Through)."""
        if not kwargs:
            return

        # Update Cache
        settings = await self.get_guild_settings(guild_id)
        settings.update(kwargs)

        # Update DB
        set_clause = ", ".join(f"{key} = ?" for key in kwargs.keys())
        values = list(kwargs.values()) + [guild_id]

        async with self.acquire_db() as db:
            await db.execute(f"UPDATE guild_settings SET {set_clause} WHERE guild_id = ?", values)
            await db.commit()

    async def upsert_star_post(self, guild_id: int, source_id: int, starboard_id: int):
        """Update both DB and cache manually for star posts."""
        # Update Cache
        if guild_id not in self.star_posts_cache:
            self.star_posts_cache[guild_id] = {}
        self.star_posts_cache[guild_id][source_id] = starboard_id

        # Update DB
        async with self.acquire_db() as db:
            await db.execute("""
                             INSERT INTO star_posts (guild_id, source_message_id, starboard_message_id)
                             VALUES (?, ?, ?) ON CONFLICT(guild_id, source_message_id) DO
                             UPDATE SET
                                 starboard_message_id = excluded.starboard_message_id
                             """, (guild_id, source_id, starboard_id))
            await db.commit()

    async def delete_star_post(self, guild_id: int, source_id: int):
        """Remove from both DB and cache manually."""
        # Update Cache
        if guild_id in self.star_posts_cache:
            self.star_posts_cache[guild_id].pop(source_id, None)

        # Update DB
        async with self.acquire_db() as db:
            await db.execute(
                "DELETE FROM star_posts WHERE guild_id = ? AND source_message_id = ?",
                (guild_id, source_id)
            )
            await db.commit()

    def get_star_post(self, guild_id: int, source_id: int) -> Optional[int]:
        """Pure cache read for performance."""
        return self.star_posts_cache.get(guild_id, {}).get(source_id)

    # --- Utility Logic ---

    @tasks.loop(minutes=5)
    async def _cache_cleanup(self):
        """Standard LFG/Cooldown cleanup (Settings/Star cache persist)."""
        current_time = time.time()

        # Cleanup LFG
        max_age = 24 * 60 * 60
        to_remove_lfg = [m for m, t in self.lfg_message_times.items() if current_time - t > max_age]
        for m in to_remove_lfg:
            self.lfg_creators.pop(m, None)
            self.lfg_message_times.pop(m, None)

        # Cleanup Cooldowns
        to_remove_cd = [k for k, v in self.guild_cooldowns.items() if current_time - v > 600]
        for k in to_remove_cd:
            self.guild_cooldowns.pop(k, None)

    def build_starboard_embed(self, message: discord.Message, star_count: int) -> discord.Embed:
        text = message.content.strip() if message.content else ""
        embed = discord.Embed(description=text, color=discord.Color.gold())
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.add_field(name="Jump to Message", value=f"[Click Here]({message.jump_url})", inline=False)
        embed.set_footer(text=f"{star_count} ⭐ | #{message.channel.name}")

        image_url = None
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                image_url = att.url
                break
        if not image_url:
            for e in message.embeds:
                if e.image and e.image.url: image_url = e.image.url; break
                if e.thumbnail and e.thumbnail.url: image_url = e.thumbnail.url; break
                if e.type == "image" and e.url: image_url = e.url; break
        if image_url:
            embed.set_image(url=image_url)
        return embed

    # --- Events ---

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or str(reaction.emoji) != self.STAR_EMOJI:
            return

        message = reaction.message
        if not message.guild or message.id not in self.lfg_creators:
            return

        settings = await self.get_guild_settings(message.guild.id)
        count = reaction.count - (1 if reaction.me else 0)

        if count >= settings["lfg_threshold"]:
            reactors = [u async for u in reaction.users() if not u.bot]
            mentions = " ".join(u.mention for u in reactors) or "Threshold reached!"
            creator_id = self.lfg_creators.pop(message.id, None)
            self.lfg_message_times.pop(message.id, None)

            creator = message.guild.get_member(creator_id)
            embed = discord.Embed(
                title="LFG Group Ready!",
                description=f"**Created by:** {creator.mention if creator else 'Unknown User'}",
                color=discord.Color.green()
            )
            await message.channel.send(content=mentions, embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id != self.bot.user.id and str(payload.emoji) == self.STAR_EMOJI:
            self._schedule_starboard_update(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) == self.STAR_EMOJI:
            self._schedule_starboard_update(payload)

    def _schedule_starboard_update(self, payload: discord.RawReactionActionEvent):
        mid = payload.message_id
        if mid in self._starboard_tasks and not self._starboard_tasks[mid].done():
            self._starboard_tasks[mid].cancel()
        self._starboard_tasks[mid] = self.bot.loop.create_task(self._process_starboard_payload(payload))

    async def _process_starboard_payload(self, payload: discord.RawReactionActionEvent):
        await asyncio.sleep(0.5)
        try:
            guild = self.bot.get_guild(payload.guild_id)
            if not guild: return

            settings = await self.get_guild_settings(guild.id)
            sb_id = settings.get("starboard_channel_id")
            if not sb_id or payload.channel_id == sb_id: return

            chan = guild.get_channel(payload.channel_id) or await guild.fetch_channel(payload.channel_id)
            msg = await chan.fetch_message(payload.message_id)

            # Handle Bot Authors
            if msg.author.bot:
                existing = self.get_star_post(guild.id, msg.id)
                if existing:
                    try:
                        sbc = guild.get_channel(sb_id)
                        sbm = await sbc.fetch_message(existing)
                        await sbm.delete()
                    except:
                        pass
                    await self.delete_star_post(guild.id, msg.id)
                return

            star_react = next((r for r in msg.reactions if str(r.emoji) == self.STAR_EMOJI), None)
            count = star_react.count if star_react else 0
            existing_id = self.get_star_post(guild.id, msg.id)

            if count < settings["star_threshold"]:
                if existing_id:
                    try:
                        sbc = guild.get_channel(sb_id)
                        sbm = await sbc.fetch_message(existing_id)
                        await sbm.delete()
                    except:
                        pass
                    await self.delete_star_post(guild.id, msg.id)
                return

            # Upsert logic
            sbc = guild.get_channel(sb_id)
            embed = self.build_starboard_embed(msg, count)

            if existing_id:
                try:
                    sbm = await sbc.fetch_message(existing_id)
                    await sbm.edit(embed=embed)
                except discord.NotFound:
                    new_sbm = await sbc.send(embed=embed)
                    await self.upsert_star_post(guild.id, msg.id, new_sbm.id)
            else:
                new_sbm = await sbc.send(embed=embed)
                await self.upsert_star_post(guild.id, msg.id, new_sbm.id)
        finally:
            self._starboard_tasks.pop(payload.message_id, None)

    @commands.Cog.listener()
    async def on_raw_reaction_clear(self, payload: discord.RawReactionClearEvent):
        existing = self.get_star_post(payload.guild_id, payload.message_id)
        if not existing: return

        try:
            settings = await self.get_guild_settings(payload.guild_id)
            sbc = self.bot.get_channel(settings["starboard_channel_id"])
            sbm = await sbc.fetch_message(existing)
            await sbm.delete()
        except:
            pass
        await self.delete_star_post(payload.guild_id, payload.message_id)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not after.guild: return
        existing = self.get_star_post(after.guild.id, after.id)
        if not existing: return

        settings = await self.get_guild_settings(after.guild.id)
        star_react = next((r for r in after.reactions if str(r.emoji) == self.STAR_EMOJI), None)
        count = star_react.count if star_react else 0

        try:
            sbc = after.guild.get_channel(settings["starboard_channel_id"])
            embed = self.build_starboard_embed(after, count)
            sbm = await sbc.fetch_message(existing)
            await sbm.edit(embed=embed)
        except:
            pass

    # --- Commands ---

    starboard_group = app_commands.Group(name="starboard", description="Starboard configuration")

    @starboard_group.command(name="set_channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def starboard_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.update_guild_setting(interaction.guild.id, starboard_channel_id=channel.id)
        await interaction.response.send_message(f"Starboard set to {channel.mention}", ephemeral=True)

    @starboard_group.command(name="threshold")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def starboard_threshold(self, interaction: discord.Interaction, amount: int):
        if amount < 1: return await interaction.response.send_message("Min 1.", ephemeral=True)
        await self.update_guild_setting(interaction.guild.id, star_threshold=amount)
        await interaction.response.send_message(f"Threshold set to {amount} ⭐", ephemeral=True)

    lfg_group = app_commands.Group(name="lfg", description="LFG commands")

    @lfg_group.command(name="create")
    async def lfg_create(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        now = time.time()
        if now - self.guild_cooldowns.get(gid, 0) < 60:
            return await interaction.response.send_message("On cooldown.", ephemeral=True)

        self.guild_cooldowns[gid] = now
        settings = await self.get_guild_settings(gid)

        embed = discord.Embed(
            title="Looking For Group!",
            description=f"React with {self.STAR_EMOJI} to join.\nLooking for **{settings['lfg_threshold']}** people.\n\n**Created by:** {interaction.user.mention}",
            color=discord.Color(0x337fd5)
        )
        msg = await interaction.channel.send(embed=embed)
        await msg.add_reaction(self.STAR_EMOJI)

        self.lfg_creators[msg.id] = interaction.user.id
        self.lfg_message_times[msg.id] = now
        await interaction.response.send_message("LFG Created", ephemeral=True)

    @lfg_group.command(name="threshold")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def lfg_threshold(self, interaction: discord.Interaction, amount: int):
        if amount < 1: return await interaction.response.send_message("Min 1.", ephemeral=True)
        await self.update_guild_setting(interaction.guild.id, lfg_threshold=amount)
        await interaction.response.send_message(f"LFG Threshold set to {amount}", ephemeral=True)

    @commands.command(name="teststarboard")
    async def teststarboard(self, ctx: commands.Context):
        if ctx.author.id != 758576879715483719 or not ctx.message.reference: return

        ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        settings = await self.get_guild_settings(ctx.guild.id)
        sb_id = settings.get("starboard_channel_id")
        if not sb_id: return

        star_react = next((r for r in ref.reactions if str(r.emoji) == self.STAR_EMOJI), None)
        embed = self.build_starboard_embed(ref, star_react.count if star_react else 0)
        await self.bot.get_channel(sb_id).send(embed=embed)


async def setup(bot):
    await bot.add_cog(StarboardCog(bot))