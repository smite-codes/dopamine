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

class OwnerDashboard(PrivateLayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        self.build_layout()

    def build_layout(self):
        self.clear_items()
        container = discord.ui.Container()
        container.add_item((discord.ui.TextDisplay("## Owner Dashboard")))

        container.add_item(discord.ui.Separator())
        cogtoggle_btn = discord.ui.Button(label=f"{'Unload' if 1==1 else 'Load'}", style=discord.ButtonStyle.secondary if 1==1 else discord.ButtonStyle.primary) # 1==1 is the check that's true if the cog is loaded.
        container.add_item(discord.ui.Section(discord.ui.TextDisplay("1. thenameofthecog.py"), accessory=cogtoggle_btn)) # there will be ONE of these sections for every single cog/extension/whatever.

        restart_btn = discord.ui.Button(label="Restart Bot", style=discord.ButtonStyle.secondary) # This button restarts main.py
        shutdown_btn = discord.ui.Button(label="Shutdown Bot", style=discord.ButtonStyle.primary) # This shuts down the bot gracefully.
        sync_btn = discord.ui.Button(label="Sync Slash Commands", style=discord.ButtonStyle.primary) #This syncs slash commands through await bot.tree.sync()

        row = discord.ui.ActionRow()

        row.add_item(sync_btn)
        row.add_item(shutdown_btn)
        row.add_item(restart_btn)
        container.add_item(discord.ui.Separator())
        container.add_item(row)

        self.add_item(container)

class DestructiveConfirmationView(PrivateLayoutView):
    def __init__(self, title_text: str, body_text: str, color: discord.Color = None):
        super().__init__(timeout=30)
        self.value = None
        self.title_text = title_text
        self.body_text = body_text
        self.color = color
        self.message: discord.Message = None
        self.build_layout()

    def build_layout(self):
        self.clear_items()
        container = discord.ui.Container(accent_color=self.color)
        container.add_item(discord.ui.TextDisplay(f"### {self.title_text}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(self.body_text))

        if self.value is None:
            action_row = discord.ui.ActionRow()
            cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.gray)
            confirm = discord.ui.Button(label="Reset to Default", style=discord.ButtonStyle.red)

            cancel.callback = self.cancel_callback
            confirm.callback = self.confirm_callback

            action_row.add_item(cancel)
            action_row.add_item(confirm)
            container.add_item(discord.ui.Separator())
            container.add_item(action_row)

        self.add_item(container)

    async def update_view(self, interaction: discord.Interaction, title: str, color: discord.Color):
        self.title_text = title
        self.body_text = f"~~{self.body_text}~~"
        self.color = color
        self.build_layout()

        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)
        self.stop()

    async def cancel_callback(self, interaction: discord.Interaction):
        self.value = False
        await self.update_view(interaction, "Action Canceled", discord.Color(0xdf5046))

    async def confirm_callback(self, interaction: discord.Interaction):
        self.value = True
        await self.update_view(interaction, "Action Confirmed", discord.Color.green())

    async def on_timeout(self, interaction: discord.Interaction):
        if self.value is None and self.message:
            await self.update_view(interaction, "Timed Out", discord.Color(0xdf5046))
            self.stop()


class CV2TestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="cv2test", description="Tests Discord Components V2 layout")
    async def cv2test(self, interaction: discord.Interaction):
        view = TrackerDashboard()
        await interaction.response.send_message(
            view=view,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CV2TestCog(bot))