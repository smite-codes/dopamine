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

class TrackerDashboard(PrivateLayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        self.build_layout()

    def build_layout(self):
        self.clear_items()
        container = discord.ui.Container()
        toggle_btn = discord.ui.Button(label=f"{'Disable' if 1==1 else 'Enable'}", style=discord.ButtonStyle.secondary if 1==1 else discord.ButtonStyle.primary)
        container.add_item(discord.ui.Section(discord.ui.TextDisplay("## Member Tracker Dashboard"), accessory=toggle_btn))

        container.add_item(discord.ui.TextDisplay("Member Tracker tracks the number of members in the server, and posts a new message in a set channel when the count goes up. You can set a goal and a celebratory message will be posted in the same channel."))
        if 1==1:
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay("**Channel:** {channel.mention if channel else 'Unknown'}"))
            container.add_item(discord.ui.TextDisplay("**Channel:** {channel.mention if channel else 'Unknown'}"))
            if data['member_goal']:
                container.add_item(discord.ui.TextDisplay("### Goal\n{data['member_goal']} members"))
            if data['custom_format']:
                container.add_item(discord.ui.TextDisplay("### Format\n```{data['custom_format']}```"))
            if data['color']:
                container.add_item(discord.ui.TextDisplay("Placeholder for colour"))

            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay("""### ➤ DOCUMENTATION\n\n**Available Variables**\n* `{count}` - Current member count of your server\n* `{remaining}` - Members remaining to reach the goal\n* `{goal}` - The member goal you've set\n* `{server}` - Name of your server\n**Example Formats**\n* `🎉 {_count} members! Only {remainingl} more to go!`\n* `{server} reached {count}! Goal: {goal}`\n**Notes**\n* You can customize it however you want, you don't have to use these examples!\n* {remaining} will only work if a goal is set."""))

            container.add_item(discord.ui.Separator())
            edit_btn = discord.ui.Button(label="Edit", style=discord.ButtonStyle.primary)
            bot_btn = discord.ui.Button(label=f"{"Don't Include Bots' if 2==2 else 'Include Bots"}", style=discord.ButtonStyle.secondary if 2==2 else discord.ButtonStyle.primary)
            row = discord.ui.ActionRow()
            row.add_item(edit_btn)
            row.add_item(bot_btn)
            container.add_item(row)
            container.add_item(discord.ui.Separator())

            container.add_item(discord.ui.TextDisplay("### Reset to Default"))

            btn_reset = discord.ui.Button(label="Reset", style=discord.ButtonStyle.secondary)
            btn_reset.callback = self.reset_button_callback

            container.add_item(discord.ui.Section(
                discord.ui.TextDisplay("Click the Reset button to reset everything to default."),
                accessory=btn_reset
            ))

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