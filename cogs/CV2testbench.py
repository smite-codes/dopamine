import discord
from discord.ext import commands
from discord import app_commands

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

class StarboardDashboard(PrivateLayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        self.build_layout()

    def build_layout(self):
        self.clear_items()
        container = discord.ui.Container()
        toggle_btn = discord.ui.Button(label=f"{'Disable' if 1==1 else 'Enable'}", style=discord.ButtonStyle.secondary if 1==1 else discord.ButtonStyle.primary)
        container.add_item(discord.ui.Section(discord.ui.TextDisplay("## Starboard Dashboard"), accessory=toggle_btn))

        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("A starboard is like a Hall Of Fame for Discord messages. Users can react to a message with a ⭐️ and once it reaches the set threshold, Dopamine will post a copy of it in the channel you choose."))
        if 1==1:
            container.add_item(discord.ui.TextDisplay("* **Current Channel:** {channel.mention}\n* **Current Threshold:** {threshold}"))
            container.add_item(discord.ui.Separator())
            threshold_btn = discord.ui.Button(label="Edit Threshold", style=discord.ButtonStyle.primary)
            channel_btn = discord.ui.Button(label="Edit Channel", style=discord.ButtonStyle.secondary)
            row = discord.ui.ActionRow()
            row.add_item(threshold_btn)
            row.add_item(channel_btn)
            container.add_item(row)

        self.add_item(container)

class ChannelSelectView(PrivateLayoutView):
    def __init__(self, user, cog, guild_id, is_rebind=False, panel_title=None):
        super().__init__(timeout=None)

    def build_layout(self):
        container = discord.ui.Container()

        select = discord.ui.ChannelSelect(
            placeholder="Select a channel...",
            channel_types=[discord.ChannelType.text],
            min_values=1, max_values=1
        )

        row = discord.ui.ActionRow()
        row.add_item(select)
        container.add_item(discord.ui.TextDisplay("###Select a Channel"))
        container.add_item(discord.ui.TextDisplay("Choose the channel where you want the starboard to appear:"))
        container.add_item(row)
        self.add_item(container)


class CV2TestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="cv2test", description="Tests Discord Components V2 layout")
    async def cv2test(self, interaction: discord.Interaction):
        view = StarboardDashboard()
        await interaction.response.send_message(
            view=view,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CV2TestCog(bot))