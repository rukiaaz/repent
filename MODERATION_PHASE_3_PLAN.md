"""
Phase 3: Ban Command with Dropdown
This file contains the ban command implementation with dropdown.
This is a summary of the changes needed for moderation.py.
"""

# Ban Command Update

# Add imports:
# from utils.dropdowns import create_reason_dropdown, create_duration_dropdown
# from utils.embed_templates import action_confirmation_embed, moderation_result_embed

# Add these classes before the ban command:

class BanView(discord.ui.View):
    def __init__(self, cog, target_user):
        super().__init__(timeout=None)
        self.cog = cog
        self.target_user = target_user
    
    @discord.ui.select(
        placeholder="Select Reason",
        options=create_reason_dropdown(context="moderation")
    )
    async def select_reason(self, interaction: discord.Interaction, select: discord.ui.Select):
        reason = select.values[0]
        
        embed = action_confirmation_embed(
            action_type="Ban",
            target=self.target_user.mention,
            details={"Reason": reason, "Duration": "Permanent"},
            warning="⚠️ This action is permanent."
        )
        
        view = self.cog.BanConfirmView(self.cog, self.target_user, reason, 0)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        self.stop()

class BanConfirmView(discord.ui.View):
    def __init__(self, cog, target_user, reason, delete_days):
        super().__init__(timeout=None)
        self.cog = cog
        self.target_user = target_user
        self.reason = reason
        self.delete_days = delete_days
    
    @discord.ui.button(label="✅ Confirm Ban", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._execute_ban(interaction, self.target_user, self.reason, self.delete_days)
        self.stop()
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Ban cancelled", embed=None, view=None)
        self.stop()

async def _execute_ban(self, interaction: discord.Interaction, user: discord.Member, reason: str, delete_days: int):
    """Execute the ban action."""
    try:
        await interaction.guild.ban(user, reason=f"{interaction.user}: {reason}", delete_message_days=delete_days)
        await log_action(interaction.guild.id, "ban", user.id, {"reason": reason, "moderator": interaction.user.id})
        
        embed = moderation_result_embed(
            action="Ban",
            target=user.mention,
            moderator=interaction.user.mention,
            reason=reason,
            success=True
        )
        embed.set_footer(text=f"ID: {user.id} • Action by {interaction.user.display_name}")
        await interaction.followup.send(embed=embed, ephemeral=False)
        
    except Exception as e:
        embed = error_embed(f"Failed to ban: {str(e)}")
        await interaction.followup.send(embed=embed, ephemeral=False)

# Update ban command:
@app_commands.command(name="ban", description="Ban a user from the server")
@app_commands.describe(user="User to ban")
async def ban(self, interaction: discord.Interaction, user: discord.Member):
    """Ban command with reason dropdown."""
    # Permission checks...
    
    view = self.BanView(self, user)
    embed = discord.Embed(
        title="⚡ Ban User",
        description=f"Select a reason for banning {user.mention}",
        color=0xFFFFFF
    )
    embed.add_field(name="Target", value=user.mention, inline=False)
    embed.add_field(name="Warning", value="⚠️ This action is permanent.", inline=False)
    
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
