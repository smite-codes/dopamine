import discord
from discord import app_commands
from discord.ext import commands
from utils.log import LoggingManager
from utils.checks import slash_mod_check

class DestructiveConfirmationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.value = None

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.red)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.defer()
        self.stop()

class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manager = LoggingManager()

    async def cog_load(self):
        await self.manager.init_pools()
        await self.manager.init_db()
        await self.manager.populate_cache()

    log = app_commands.Group(name="logging", description="Manage logging feature.")
    @log.command(name="set", description="Set the logging channel for logs.")
    @app_commands.check(slash_mod_check)
    @app_commands.describe(channel="Channel to use for logs")
    async def setlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        already = await self.manager.logging_get(interaction.guild.id)
        await self.manager.logging_set(interaction.guild.id, channel.id)

        embed = discord.Embed(
            title="This channel has been set as the log channel.",
            description=f"All moderation logs will now be sent here.",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Set by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        channel = self.bot.get_channel(channel.id)
        if not channel:
            channel = self.bot.fetch_channel(channel.id)
        if not channel:
            return await interaction.response.send_message("I can't find the channel that you set for logging! Please ensure I have the necessary permissions.", ephemeral=True)
        await channel.send_message(embed=embed)
        await interaction.response.send_message(embed=discord.Embed(
            title=f"{"Logging has been enabled" if already else "Logging Channel Updated"}",
            description=f"Log channel set to {channel.mention}",
            color=discord.Color.green()), ephemeral=True)

    @log.command(name="get", description="Check what channel is set as the logging channel.")
    @app_commands.check(slash_mod_check)
    async def getlog(self, interaction: discord.Interaction):
        channel_id = await self.manager.logging_get(interaction.guild.id)
        await interaction.response.send_message(f"The logging channel is currently set to <#{channel_id}>.", ephemeral=True)

    @log.command(name="test", description="Test whether the bot can access the logging channel or not.")
    @app_commands.check(slash_mod_check)
    async def testlog(self, interaction: discord.Interaction):
        channel_id = await self.manager.logging_get(interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(f"No logging channel is set in **{interaction.guild}**.")
        channel = self.bot.get_channel(channel_id)
        if not channel:
            channel = self.bot.fetch_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(
                "I can't find the channel that you set for logging! Please ensure I have the necessary permissions.",
                ephemeral=True)
        embed = discord.Embed(title="Test",
                              description=f"Beep, boop! This is a test message to test whether logging works or not.",
                              color=discord.Colour.blue())
        await channel.send_message(embed=embed, ephemeral=True)

    @log.command(name="disable", description="Disable logging and delete logging channel for this server from database.")
    @app_commands.check(slash_mod_check)
    async def deletelog(self, interaction: discord.Interaction):
        exists = await self.manager.logging_get(interaction.guild.id)
        if not exists:
            return await interaction.response.send_message("Logging is already disabled in this server.", ephemeral=True)

        view = DestructiveConfirmationView(self)
        await interaction.response.send_message(embed=discord.Embed(title="Pending Confirmation",
                                                                    description=f"Are you sure you want to:\n* Disable logging.\n* Delete the logging channel from the database permanently.",
                                                                    view=view, colour=discord.Colour(0x000000)))
        await view.wait()

        if view.value is None:
            await interaction.edit_original_response(embed=discord.Embed(title="Timed Out",
                                                                         ddescription=f"~~Are you sure you want to:\n* Disable logging.\n* Delete the saved channel from the database permanently.~~",
                                                                         colour=discord.Colour.red()))
        if view.value is False:
            await interaction.edit_original_response(embed=discord.Embed(title="Action Canceled",
                                                                         ddescription=f"~~Are you sure you want to:\n* Disable logging.\n* Delete the saved channel from the database permanently.~~",
                                                                         colour=discord.Colour.red()))
        if view.value is True:
            await self.manager.logging_delete(interaction.guild_id)
            await interaction.edit_original_response(embed=discord.Embed(title="Action Confirmed",
                                                                         ddescription=f"~~Are you sure you want to:\n* Disable logging.\n* Delete the saved channel from the database permanently.~~",
                                                                         colour=discord.Colour.green()))
async def setup(bot):
    await bot.add_cog(Logging(bot))