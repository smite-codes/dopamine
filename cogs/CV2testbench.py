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

class CV2Helper(PrivateLayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        self.build_layout()

    def build_layout(self):
        self.clear_items()

        container = discord.ui.Container(accent_color=discord.Color.blue())

        container.add_item(discord.ui.TextDisplay("## Welcome Feature Dashboard"))


        section = discord.ui.Section(
            discord.ui.TextDisplay("Configure all settings related to Dopamine's welcome feature. Click the adjacent button to enable or disable the feature."),
            accessory=discord.ui.Button(label=f"{"Welcome Feature Enabled" if 1==1 else "Disabled"}", style=discord.ButtonStyle.primary if 1==1 else discord.ButtonStyle.secondary) # the 1 here is a placeholder for checking whether the feature is enabled or disabled. hope this makes sense.
        )
        container.add_item(section)

        if 1==1: #this is a placeholder. this should only be true (and therefore only be shown) when is_enabled is 1 or true.
            container.add_item(discord.ui.Separator())
            section = discord.ui.Section(
                discord.ui.TextDisplay("### Text"),
                accessory=discord.ui.Button(label=f"{"Enabled" if 1==1 else "Disabled"}", style=discord.ButtonStyle.primary if 1==1 else discord.ButtonStyle.secondary) # the 1 here is a placeholder for checking whether the feature is enabled or disabled. if the feature is disabled and the user clicks the button, a followup message will be sent containing a discord channel dropdown, where they can select upto 1 channel. hope this makes sense.
            )
            if 2==2: #this is a placeholder. this is supposed to be true when is_enabled is set to 1 AND text feature is enabled. or less, we will only show the above header with the enabled/disabled button.
                container.add_item(section)
                section = discord.ui.Section(discord.ui.TextDisplay("The text part of the welcome message. Click the customise button to customise the format.\n\n* **Current Format:**\n  * `Welcome to **{server.name}**, {member.mention}!`\n* **Available Variables:**\n  * `{member.mention}` - Mention the member.\n  * `{member.name}` - The member's username.\n  * `{server.name}` - The name of the server.\n  * `{position}` - The position/rank of the member (eg. 'you are are our 156th member')."),
                                             accessory=discord.ui.Button(emoji="⚙️", label=f"Customise", style=discord.ButtonStyle.secondary)) # this button will open a modal with a big text input field. users dont have to necessarily use one of the avaible variables. only check if a variable is correct if the string includes something with curly braces {}.
                container.add_item(section)
            container.add_item(discord.ui.Separator())
            section = discord.ui.Section(
                discord.ui.TextDisplay("### Welcome Card"),
                accessory=discord.ui.Button(label=f"{"Enabled" if 1==1 else "Disabled"}",
                                            style=discord.ButtonStyle.primary if 1==1 else discord.ButtonStyle.secondary) # the 1 here is a placeholder for checking whether the feature is enabled or disabled. hope this makes sense.
            )
            container.add_item(section)
            if 3==3: #this is a placeholder. this is supposed to be true when welcome card feature is enabled. or less, we will only show the above header with the enabled/disabled button. as an off topic suggestion, this whole container/view should be refreshed upon button clicks so that the hidden sections become visible.
                section = discord.ui.Section(discord.ui.TextDisplay("The Welcome Card (image) of the welcome message. Use the customise button to provide a custom image URL, or to edit one of the text lines of the image.\n\n* **Current Image:** Using default image/using custom image.\n* **Current Image Text:**\n  * Line 1: `Welcome {member.name}`\n  * Line 2: `You are our 36th member!`\n* **Available Variables for Image Text:**\n  * `{member.name}` - The member's username.\n  * `{server.name}` - The name of the server.\n  * `{position}` - The position/rank of the member (eg. 'you are are our 156th member')"),
                                             accessory=discord.ui.Button(emoji="⚙️", label="Customise", style=discord.ButtonStyle.secondary)) # this button will open a modal with the following fields that are all optional and left unmodified if left blank: Image URL, line 1, line 2. users dont have to necessarily use one of the available     variables. only check if a variable is correct if the string includes something with curly braces {}.
                container.add_item(section)
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay("### Reset to Default"))
            container.add_item(discord.ui.Section(discord.ui.TextDisplay("Click the Reset button to reset everything to default."), accessory=discord.ui.Button(label="Reset", style=discord.ButtonStyle.secondary))) #when this button is clicked, it will send the "DestructiveConfirmationView" provided below.

        self.add_item(container)

class DestructiveConfirmationView(PrivateLayoutView):
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
            await self.update_view(interaction, "Action Confirmed", discord.Color.green())


class CV2TestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="cv2test", description="Tests Discord Components V2 layout")
    async def cv2test(self, interaction: discord.Interaction):
        view = CV2Helper()
        await interaction.response.send_message(
            view=view,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CV2TestCog(bot))