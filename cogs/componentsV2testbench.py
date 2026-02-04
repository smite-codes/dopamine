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

class CreateChoose(PrivateLayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        self.build_layout()

    def build_layout(self):
        self.clear_items()
        container = discord.ui.Container()
        container.add_item((discord.ui.TextDisplay("## Create Giveaway")))
        container.add_item(discord.ui.TextDisplay("Choose an option below to continue creating a giveaway. Create button leads to the regular creation menu, while the other option lets you enter a template code."))
        container.add_item(discord.ui.Separator())

        create_btn = discord.ui.Button(label="Create", style=discord.ButtonStyle.primary)
        template_btn = discord.ui.Button(label="Create from Template", style=discord.ButtonStyle.secondary)
        row = discord.ui.ActionRow()

        row.add_item(create_btn)
        row.add_item(template_btn)

        container.add_item(row)

        self.add_item(container)

class ManagePage(PrivateLayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        self.build_layout()

    def build_layout(self):
        self.clear_items()
        container = discord.ui.Container()
        container.add_item((discord.ui.TextDisplay("## Manage Autoreact Panels")))
        container.add_item(discord.ui.TextDisplay("List of all existing Autoreact Panels. Click Edit to configure details or the channel."))
        container.add_item(discord.ui.Separator())
        edit_btn = discord.ui.Button(label="Edit", style=discord.ButtonStyle.secondary)
        container.add_item(discord.ui.Section(discord.ui.TextDisplay("### 1. Panel Name in {channel}"), accessory=edit_btn))
        container.add_item(discord.ui.TextDisplay("-# Page 1 of 1"))
        container.add_item(discord.ui.Separator())
        left_btn = discord.ui.Button(emoji="◀", style=discord.ButtonStyle.primary, disabled=1==1)
        go_btn = discord.ui.Button(label="Go To Page", style=discord.ButtonStyle.secondary, disabled=2==2)
        right_btn = discord.ui.Button(emoji="▶", style=discord.ButtonStyle.primary, disabled=3==3)

        row = discord.ui.ActionRow()

        row.add_item(left_btn)
        row.add_item(go_btn)
        row.add_item(right_btn)

        container.add_item(row)

        container.add_item(discord.ui.Separator())

        return_btn = discord.ui.Button(label="Return to Dashboard", style=discord.ButtonStyle.secondary)

        row = discord.ui.ActionRow()

        row.add_item(return_btn)

        container.add_item(row)

        self.add_item(container)

class EditPage(PrivateLayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        self.build_layout()

    def build_layout(self):
        self.clear_items()
        container = discord.ui.Container()
        container.add_item((discord.ui.TextDisplay("Edit: {panel name}")))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay("**State:** placeholder\n**Emojis:** placeholder\n**Channel:** placeholder\n**Target:** placeholder\n**Mode:** placeholder\n"))
        container.add_item(discord.ui.Separator())
        state_btn = discord.ui.Button(label=f"{'Deactivate' if 1==1 else 'Activate'}", style=discord.ButtonStyle.secondary if 1==1 else discord.ButtonStyle.primary)
        edit_btn = discord.ui.Button(label="Edit", style=discord.ButtonStyle.secondary)
        channel_btn = discord.ui.Button(label="Edit Channel", style=discord.ButtonStyle.secondary)
        member_btn = discord.ui.Button(label=f"{'Disable Member Whitelist' if 2==2 else 'Enable Member Whitelist'}", style=discord.ButtonStyle.secondary if 2==2 else discord.ButtonStyle.primary)
        image_btn = discord.ui.Button(label=f"{'Disable Image-only Mode' if 3==3 else 'Enable Image-only Mode'}", style=discord.ButtonStyle.secondary if 3==3 else discord.ButtonStyle.primary)
        delete_btn = discord.ui.Button(label="Delete", style=discord.ButtonStyle.danger)

        row = discord.ui.ActionRow()

        row.add_item(state_btn)
        row.add_item(edit_btn)
        row.add_item(channel_btn)
        row.add_item(delete_btn)

        container.add_item(row)

        row = discord.ui.ActionRow()

        row.add_item(member_btn)
        row.add_item(image_btn)

        container.add_item(row)

        container.add_item(discord.ui.Separator())

        return_btn = discord.ui.Button(label="Return to Manage Menu", style=discord.ButtonStyle.secondary)
        row = discord.ui.ActionRow()
        row.add_item(return_btn)
        container.add_item(row)

        self.add_item(container)

class GoToPageModal(discord.ui.Modal):
    def __init__(self, parent_view: "ManagePage", total_pages: int):
        super().__init__(title="Jump to Page")
        self.parent_view = parent_view
        self.total_pages = total_pages

        self.page_input = discord.ui.TextInput(
            label=f"Page Number (1-{total_pages})",
            placeholder="Enter a page number...",
            min_length=1,
            max_length=5,
            required=True,
        )
        self.add_item(self.page_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page_num = int(self.page_input.value)
            if 1 <= page_num <= self.total_pages:
                self.parent_view.page = page_num
                self.parent_view.build_layout()
                await interaction.response.edit_message(view=self.parent_view)
            else:
                await interaction.response.send_message(
                    f"Please enter a number between 1 and {self.total_pages}.",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "Invalid input. Please enter a valid whole number.",
                ephemeral=True
            )

class CreateChannelSelect(PrivateLayoutView):
    def __init__(self, user, cog, guild_id, is_rebind=False, panel_title=None):
        super().__init__(user, timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.is_rebind = is_rebind
        self.panel_title = panel_title
        self.build_layout()

    def build_layout(self):
        container = discord.ui.Container()

        self.select = discord.ui.ChannelSelect(
            placeholder="Select a channel...",
            channel_types=[discord.ChannelType.text],
            min_values=1, max_values=1
        )
        self.select.callback = self.select_callback

        row = discord.ui.ActionRow()
        row.add_item(self.select)
        container.add_item(discord.ui.TextDisplay("### Step 1: Select a Channel"))
        container.add_item(discord.ui.TextDisplay("Choose the channel where you want the reactions to be made:"))
        container.add_item(row)
        self.add_item(container)

    async def select_callback(self, interaction: discord.Interaction):
        pass

class EditChannelSelect(PrivateLayoutView):
    def __init__(self, user, cog, guild_id, is_rebind=False, panel_title=None):
        super().__init__(user, timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.is_rebind = is_rebind
        self.panel_title = panel_title
        self.build_layout()

    def build_layout(self):
        container = discord.ui.Container()

        self.select = discord.ui.ChannelSelect(
            placeholder="Select a channel...",
            channel_types=[discord.ChannelType.text],
            min_values=1, max_values=1
        )
        self.select.callback = self.select_callback

        row = discord.ui.ActionRow()
        row.add_item(self.select)
        container.add_item(discord.ui.TextDisplay("Select a Channel"))
        container.add_item(discord.ui.TextDisplay("Choose the channel where you want the reactions to be made:"))
        container.add_item(row)
        self.add_item(container)

    async def select_callback(self, interaction: discord.Interaction):
        pass

class MemberSelect(PrivateLayoutView):
    def __init__(self, user, cog, guild_id, is_rebind=False, panel_title=None):
        super().__init__(user, timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.is_rebind = is_rebind
        self.panel_title = panel_title
        self.build_layout()

    def build_layout(self):
        container = discord.ui.Container()

        self.select = discord.ui.UserSelect(
            placeholder="Select members...",
            min_values=1, max_values=25
        )
        self.select.callback = self.select_callback

        row = discord.ui.ActionRow()
        row.add_item(self.select)
        container.add_item(discord.ui.TextDisplay("Select Members"))
        container.add_item(discord.ui.TextDisplay("Choose only the member(s) whose messages should get the reaction:"))
        container.add_item(row)
        self.add_item(container)

    async def select_callback(self, interaction: discord.Interaction):
        pass



class DestructiveConfirmationView(PrivateLayoutView):
    def __init__(self, user, title_name, cog, guild_id):
        super().__init__(user, timeout=30)
        self.title_name = title_name
        self.cog = cog
        self.color = None
        self.guild_id = guild_id
        self.value = None
        self.title_text = "Delete Autoreact Panel"
        self.body_text = f"Are you sure you want to permanently delete the panel name **{title_name}**? This cannot be undone."
        self.build_layout()

    def build_layout(self):
        self.clear_items()
        container = discord.ui.Container(accent_color=self.color)
        container.add_item(discord.ui.TextDisplay(f"### {self.title_text}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(self.body_text))

        is_disabled = self.value is not None
        action_row = discord.ui.ActionRow()
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.gray, disabled=is_disabled)
        confirm = discord.ui.Button(label="Delete Permanently", style=discord.ButtonStyle.red, disabled=is_disabled)

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
        await self.cog.delete_panel(self.guild_id, self.title_name)

    async def on_timeout(self, interaction: discord.Interaction):
        if self.value is None:
            self.value = False
            await self.update_view(interaction, "Timed Out", discord.Color(0xdf5046))


class CV2TestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="cv2test", description="Tests Discord Components V2 layout")
    async def cv2test(self, interaction: discord.Interaction):
        view = EditPage()
        await interaction.response.send_message(
            view=view,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CV2TestCog(bot))