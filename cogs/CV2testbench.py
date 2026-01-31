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

class ModerationDashboard(PrivateLayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        self.build_layout()

    def build_layout(self):
        self.clear_items()
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay("## Dopamine Moderation Dashboard"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("Dopamine replaces traditional mute/kick/ban commands with a **12-point escalation system**. "
            "Moderators assign points, and the bot handles the math and the punishment automatically.\n\n"
            "**Default Punishment Logic:**\n"
            "* 1 Point: Warning\n"
            "* 2-5 Points: Incremental Timeouts (15m to 1h)\n"
            "* 6-11 Points: Incremental Bans (12h to 7d)\n"
            "* 12 Points: Permanent Ban\n> The points system is completely customizable, and you can customize point amounts for each action or disable an action completely.\n\n"
            
            "**Core Features:**\n"
            "* **Decay:** Points drop by 1 every set frequency (default: two weeks) if no new infractions occur.\n"
            "* **Rejoin Policy:** Users unbanned via the bot start a set point amount (default: four) to prevent immediate repeat offenses by keeping them on thin ice."))
        container.add_item(discord.ui.Separator())
        values_btn = discord.ui.Button(label="Customise Points System", style=discord.ButtonStyle.primary)
        settings_btn = discord.ui.Button(label="Settings", style=discord.ButtonStyle.secondary)

        row = discord.ui.ActionRow()
        row.add_item(values_btn)
        row.add_item(settings_btn)
        container.add_item(row)
        self.add_item(container)


class SettingsPage(PrivateLayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        self.build_layout()

    def build_layout(self):
        self.clear_items()
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay("## Moderation Settings"))
        container.add_item(discord.ui.Separator())
        dm_btn = discord.ui.Button(label=f"{'Disable' if 1==1 else 'Enable'} DMs", style=discord.ButtonStyle.secondary if 1==1 else discord.ButtonStyle.primary)
        log_btn = discord.ui.Button(label=f"{'Disable' if 1==1 else 'Enable'} Mod Logs", style=discord.ButtonStyle.secondary if 1==1 else discord.ButtonStyle.primary)
        simple_btn = discord.ui.Button(label=f"{'Disable' if 1 == 1 else 'Enable'} Simple Mode",
                                    style=discord.ButtonStyle.secondary if 1==1 else discord.ButtonStyle.primary)
        decay_btn = discord.ui.Button(label=f"Edit Decay Frequency", style=discord.ButtonStyle.secondary)
        rejoin_btn = discord.ui.Button(label=f"Edit Rejoin Points", style=discord.ButtonStyle.secondary)
        container.add_item(discord.ui.Section(discord.ui.TextDisplay("* **Decay Frequency:** Edit the frequency at which one point is decayed from a user. Set to 0 to disable decay feature."), accessory=decay_btn))
        container.add_item(
            discord.ui.Section(discord.ui.TextDisplay(
                """* **Simple Mode:**\n  * **Terminology:** Replaces "point" with "warning" and replaces `/point` command with `/warn` (single strike at a time only)\n  * The following simple five-strike preset is applied:\n    * 1 warning: Verbal warning, no punishment\n    * 2 warnings: 60-minute timeout/mute\n    * 3 warnings: 12-hour ban\n    * 4 warnings: 7-day ban\n    * 5 warnings: Permanent ban\n  * **Best For:** Users seeking a traditional moderation feel while retaining Dopamine’s decay and rejoin policies without the learning curve. (Note: Customization of actions and point/warning thresholds is still available in Simple Mode!)"""),
                accessory=simple_btn))
        container.add_item(
            discord.ui.Section(discord.ui.TextDisplay(
                "* **Mod Logs:** Logs Moderation actions in the logging channel (if a channel is set using `/logging set`)."),
                accessory=log_btn))
        container.add_item(discord.ui.Section(discord.ui.TextDisplay(
            "* **Rejoin Points:** Edit the number of points that a user is given upon joining after being banned. Set it to `preserve` to preserve their points and leave it unchanged upon joining."),
                                              accessory=rejoin_btn))
        container.add_item(
            discord.ui.Section(discord.ui.TextDisplay("* **Punishment DMs:** Sends a DM to the user who is punished."),
                               accessory=dm_btn))

        container.add_item(discord.ui.Separator())
        return_btn = discord.ui.Button(label="Return to Dashboard", style=discord.ButtonStyle.secondary)

        container.add_item(discord.ui.ActionRow(return_btn))
        self.add_item(container)


class CustomisationPage(PrivateLayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        self.build_layout()

    def build_layout(self):
        self.clear_items()
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay("## Customise Points System"))
        container.add_item(discord.ui.TextDisplay("The list below shows the moderation actions, with their respective points needed to trigger that action. For example, if 1-hour timeout is 3 points, then a user will be timed out for 1 hour once they accumulate 3 points."))
        container.add_item(discord.ui.Separator())
        edit_btn = discord.ui.Button(label="Edit Points", style=discord.ButtonStyle.secondary)
        container.add_item(discord.ui.Section(discord.ui.TextDisplay("1. 38-Minute Timeout: **3** points"), accessory=edit_btn))
        container.add_item(discord.ui.Separator())
        create_btn = discord.ui.Button(label="Create New Action", style=discord.ButtonStyle.primary)
        toggle_delete_btn = discord.ui.Button(label=f"{'Enable' if 1==1 else 'Disable'} Delete Mode", style=discord.ButtonStyle.danger if 1==1 else discord.ButtonStyle.secondary)
        row = discord.ui.ActionRow()
        row.add_item(create_btn)
        row.add_item(toggle_delete_btn)
        container.add_item(row)
        self.add_item(container)

class ConfirmationView(PrivateLayoutView):
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
            cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red)
            confirm = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green)

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
        view = CustomisationPage()
        await interaction.response.send_message(
            view=view,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CV2TestCog(bot))