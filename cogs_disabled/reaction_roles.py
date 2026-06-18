"""Repent - Reaction Role System

Self-assignable roles with buttons or reactions, with cooldowns and persistence.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta

from config import OWNER_ID
from database import (
    create_reaction_role, get_reaction_roles, remove_reaction_role,
    get_user_reaction_role_history, add_reaction_role_history, cleanup_reaction_role_history
)
from utils.embeds import success_embed, error_embed, info_embed, warning_embed
from utils.logger import get_logger


class ReactionRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = get_logger()

    async def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID

    async def _is_mod(self, interaction: discord.Interaction) -> bool:
        return (interaction.user.guild_permissions.manage_roles or 
                interaction.user.guild_permissions.manage_channels or
                interaction.user.id == OWNER_ID)

    # ── Reaction Role Commands ──
    @app_commands.command(name="createrole", description="Create a self-assignable role message (Mod only)")
    @app_commands.describe(
        channel="Channel to send the role message",
        title="Title for the role message",
        description="Description of the role message",
        style="reaction or button"
    )
    async def create_role_message(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        description: str,
        style: str = "button"
    ):
        if not await self._is_mod(interaction):
            return await interaction.response.send_message(
                embed=error_embed("Manage Roles permission required."),
                ephemeral=True
            )
        
        # Create initial message with role selection menu
        embed = discord.Embed(
            title=f"🎭 {title}",
            description=description,
            color=0x4488FF
        )
        embed.add_field(
            name="Instructions",
            value="Use `/addtorole` to add roles to this message. Use `/finalizerole` to make it active.",
            inline=False
        )
        embed.set_footer(text="React or use buttons to get roles | Created by Repent")
        
        try:
            message = await channel.send(embed=embed)
            
            # Store the message ID for later reference
            await interaction.response.send_message(
                embed=success_embed("Role Message Created", 
                f"Role message created in {channel.mention}. Message ID: `{message.id}`\nUse this ID with `/addtorole` to add roles."),
                ephemeral=True
            )
            
            # Add to database as a role message without roles yet
            await create_reaction_role(
                interaction.guild.id, message.id, "placeholder", 0, 
                created_by=interaction.user.id
            )
            
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed(f"Failed to create role message: {str(e)}"),
                ephemeral=True
            )

    @app_commands.command(name="addtorole", description="Add a role to a role message (Mod only)")
    @app_commands.describe(
        message_id="The message ID of the role message",
        role="Role to add",
        emoji="Emoji or button label",
        button_style="Button style (for button style)",
        cooldown="Cooldown in seconds (0 = no cooldown)",
        required_role="Required role to get this role (optional)",
        blacklist_role="Role that cannot get this role (optional)",
        is_button="Whether this should be a button instead of reaction"
    )
    async def add_to_role_message(
        self,
        interaction: discord.Interaction,
        message_id: str,
        role: discord.Role,
        emoji: str = None,
        button_style: str = "PRIMARY",
        cooldown: int = 0,
        required_role: discord.Role = None,
        blacklist_role: discord.Role = None,
        is_button: bool = True
    ):
        if not await self._is_mod(interaction):
            return await interaction.response.send_message(
                embed=error_embed("Manage Roles permission required."),
                ephemeral=True
            )
        
        guild = interaction.guild
        
        try:
            # Convert message_id to integer
            msg_id = int(message_id)
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed("Invalid message ID."),
                ephemeral=True
            )
        
        # Get the message
        try:
            message = await channel if 'channel' in locals() else interaction.channel.fetch_message(msg_id)
            channel = message.channel
        except:
            try:
                # Try to find the message in the current channel
                message = await interaction.channel.fetch_message(msg_id)
                channel = message.channel
            except:
                return await interaction.response.send_message(
                    embed=error_embed("Message not found or I don't have access to it."),
                    ephemeral=True
                )
        
        # Parse button style
        button_styles = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger,
            "blurple": discord.ButtonStyle.blurple,
            "grey": discord.ButtonStyle.secondary
        }
        button_style_enum = button_styles.get(button_style.lower(), discord.ButtonStyle.primary)
        
        # Use role name as button label if no emoji provided
        label = emoji or role.name
        if is_button and not emoji:
            emoji = label  # Use label as identifier for buttons
        
        # Create the reaction role
        reaction_role_id = await create_reaction_role(
            guild.id, msg_id, emoji, role.id, 
            is_button=1 if is_button else 0, 
            button_label=label if is_button else "",
            button_style=button_style.name,
            required_role=required_role.id if required_role else 0,
            blacklist_role=blacklist_role.id if blacklist_role else 0,
            cooldown=cooldown,
            created_by=interaction.user.id
        )
        
        # If it's a button, add the button to the message
        if is_button:
            # Create or update view with buttons
            reaction_roles = await get_reaction_roles(guild.id, msg_id)
            
            # Remove existing view and create new one
            # In a real implementation, we'd need to track the view
            pass  # For now, we'll add the button directly
            
            try:
                # Add button to the message
                view = discord.ui.View()
                for rr in reaction_roles:
                    if rr["is_button"]:
                        style = button_styles.get(rr["button_style"].lower(), discord.ButtonStyle.primary)
                        button = discord.ui.Button(
                            style=style,
                            label=rr["button_label"],
                            custom_id=f"reaction_role_{rr['id']}"
                        )
                        view.add_item(button)
                
                await message.edit(view=view)
                
            except Exception as e:
                self.logger.error(f"Failed to update message with buttons: {e}", exc_info=True)
        
        elif not is_button:
            # Add reaction to the message
            try:
                # Check if emoji is a custom emoji
                if emoji.startswith("<") and emoji.endswith(">"):
                    # It's a custom emoji
                    await message.add_reaction(emoji)
                else:
                    # Try to convert to unicode emoji
                    try:
                        emoji_obj = await self.bot.fetch_emoji(emoji)
                        await message.add_reaction(emoji_obj)
                    except:
                        # Use as-is, hope it's a unicode emoji
                        await message.add_reaction(emoji)
            except Exception as e:
                self.logger.error(f"Failed to add reaction: {e}", exc_info=True)
        
        await interaction.response.send_message(
            embed=success_embed("Role Added", 
                f"Added {role.mention} to the role message.\nButton/Reaction: {emoji}\nCooldown: {cooldown}s"),
            ephemeral=False
        )

    @app_commands.command(name="finalizerole", description="Finalize and activate role message (Mod only)")
    @app_commands.describe(message_id="The message ID of the role message")
    async def finalize_role_message(self, interaction: discord.Interaction, message_id: str):
        if not await self._is_mod(interaction):
            return await interaction.response.response.send_message(
                embed=error_embed("Manage Roles permission required."),
                ephemeral=True
            )
        
        try:
            msg_id = int(message_id)
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed("Invalid message ID."),
                ephemeral=True
            )
        
        try:
            message = await interaction.channel.fetch_message(msg_id)
        except:
            return await interaction.response.send_message(
                embed=error_embed("Message not found or I don't have access to it."),
                ephemeral=True
            )
        
        # Get reaction roles for this message
        reaction_roles = await get_reaction_roles(interaction.guild.id, msg_id)
        
        # Create view with buttons
        view = discord.ui.View()
        for rr in reaction_roles:
            if rr["is_button"]:
                button_styles = {
                    "primary": discord.ButtonStyle.primary,
                    "secondary": discord.ButtonStyle.secondary,
                    "success": discord.ButtonStyle.success,
                    "danger": discord.ButtonStyle.danger,
                    "blurple": discord.ButtonStyle.blurple,
                    "grey": discord.ButtonStyle.secondary
                }
                style = button_styles.get(rr["button_style"].lower(), discord.ButtonStyle.primary)
                
                button = discord.ui.Button(
                    style=style,
                    label=rr["button_label"],
                    custom_id=f"reaction_role_{rr['id']}"
                )
                view.add_item(button)
        
        try:
            await message.edit(view=view)
        except Exception as e:
            self.logger.error(f"Failed to finalize role message: {e}", exc_info=True)
        
        await interaction.response.send_message(
            embed=success_embed("Role Message Activated", 
            "The role message is now active and users can use buttons to get roles."),
            ephemeral=False
        )

    # ── Reaction Role Listeners ──
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handle reaction role additions."""
        if payload.guild_id is None:
            return
        
        # Only process in guilds
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        # Get the user
        user = guild.get_member(payload.user_id)
        if not user or user.bot:
            return
        
        # Get reaction roles for this message
        reaction_roles = await get_reaction_roles(guild.id, payload.message_id)
        
        for rr in reaction_roles:
            if not rr["is_button"]:  # Only process reaction-based roles
                # Check if the emoji matches
                emoji = str(payload.emoji)
                if emoji == rr["emoji"]:
                    await self._process_role_assignment(user, guild, rr, payload.message_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Handle reaction role removals."""
        if payload.guild_id is None:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        user = guild.get_member(payload.user_id)
        if not user or user.bot:
            return
        
        # Get reaction roles for this message
        reaction_roles = await get_reaction_roles(guild.id, payload.message_id)
        
        for rr in reaction_roles:
            if not rr["is_button"]:
                emoji = str(payload.emoji)
                if emoji == rr["emoji"]:
                    # Remove the role
                    role = guild.get_role(rr["role_id"])
                    if role and role in user.roles:
                        try:
                            await user.remove_roles(role, reason="[Repent] Removed via reaction role")
                        except Exception as e:
                            self.logger.error(f"Failed to remove role {role.id} from {user.id}: {e}", exc_info=True)

    async def _process_role_assignment(self, user: discord.Member, guild: discord.Guild, reaction_role: dict, message_id: int):
        """Process role assignment with cooldown and restrictions."""
        role = guild.get_role(reaction_role["role_id"])
        if not role:
            return
        
        # Check required role
        if reaction_role["required_role"]:
            required_role = guild.get_role(reaction_role["required_role"])
            if required_role and required_role not in user.roles:
                return  # User doesn't have required role
        
        # Check blacklist
        if reaction_role["blacklist_role"]:
            blacklist_role = guild.get_role(reaction_role["blacklist_role"])
            if blacklist_role and blacklist_role in user.roles:
                return  # User has blacklist role
        
        # Check cooldown
        if reaction_role["cooldown"] > 0:
            history = await get_user_reaction_role_history(
                guild.id, user.id, message_id, reaction_role["role_id"]
            )
            if history:
                return  # User is on cooldown
        
        # Check bot can give role (hierarchy)
        bot_member = guild.me
        if role.position >= bot_member.top_role.position:
            return  # Role too high for bot
        
        # Give the role
        try:
            await user.add_roles(role, reason="[Repent] Given via reaction role")
            
            # Add to history
            await add_reaction_role_history(
                guild.id, user.id, message_id, role.id, reaction_role["cooldown"]
            )
            
        except Exception as e:
            self.logger.error(f"Failed to give role {role.id} to {user.id}: {e}", exc_info=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))