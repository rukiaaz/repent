"""Repent - Custom Commands System

Allow administrators to create custom commands for their servers with advanced features.
"""

from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta

from config import OWNER_ID
from database import (
    create_custom_command, get_custom_command, get_all_custom_commands, 
    delete_custom_command, update_custom_command
)
from utils.embeds import success_embed, error_embed, info_embed, warning_embed
from utils.logger import get_logger


class CustomCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = get_logger()
        self.cooldowns = {}  # User cooldown tracking

    async def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID

    # ── Custom Command Management ──
    @app_commands.command(name="customcmd", description="Create custom commands (Admin only)")
    @app_commands.describe(
        action="create, delete, list, or edit",
        name="Command name (without prefix)",
        response="Command response (supports {user}, {server}, {mention})",
        cooldown="Cooldown in seconds (0 = no cooldown)",
        required_role="Role required to use this command (optional)"
    )
    async def custom_command(
        self,
        interaction: discord.Interaction,
        action: str,
        name: str = None,
        response: str = None,
        cooldown: int = 0,
        required_role: discord.Role = None
    ):
        if not await self._is_admin(interaction):
            return await interaction.response.send_message(
                embed=error_embed("Administrator required."),
                ephemeral=True
            )
        
        guild = interaction.guild
        action_l = action.lower()
        
        if action_l == "create":
            if not name or not response:
                return await interaction.response.send_message(
                    embed=error_embed("Name and response are required."),
                    ephemeral=True
                )
            
            # Check if command already exists
            existing = await get_custom_command(guild.id, name.lower())
            if existing:
                return await interaction.response.send_message(
                    embed=error_embed(f"Command `{name}` already exists. Use `edit` to modify it."),
                    ephemeral=True
                )
            
            # Create the command
            await create_custom_command(
                guild.id, name.lower(), response, interaction.user.id,
                cooldown, required_role.id if required_role else 0
            )
            
            # Register the command
            self._register_custom_command(guild.id, name.lower())
            
            await interaction.response.send_message(
                embed=success_embed(
                    "Custom Command Created",
                    f"Command `{name}` created successfully.\n\n**Response:** {response[:200]}...\n**Cooldown:** {cooldown}s\n**Required Role:** {required_role.name if required_role else 'None'}"
                ),
                ephemeral=False
            )
        
        elif action_l == "delete":
            if not name:
                return await interaction.response.send_message(
                    embed=error_embed("Command name is required."),
                    ephemeral=True
                )
            
            success = await delete_custom_command(guild.id, name.lower())
            if not success:
                return await interaction.response.send_message(
                    embed=error_embed(f"Command `{name}` not found."),
                    ephemeral=True
                )
            
            await interaction.response.send_message(
                embed=success_embed("Custom Command Deleted", f"Command `{name}` has been removed."),
                ephemeral=False
            )
        
        elif action_l == "list":
            commands = await get_all_custom_commands(guild.id)
            if not commands:
                return await interaction.response.send_message(
                    embed=info_embed("Custom Commands", "No custom commands configured."),
                    ephemeral=False
                )
            
            embed = discord.Embed(
                title=f"📝 Custom Commands ({len(commands)})",
                color=0x4488FF
            )
            
            for cmd in commands:
                creator = guild.get_member(cmd["created_by"])
                creator_name = creator.name if creator else "Unknown"
                
                embed.add_field(
                    name=f"{cmd['name']}",
                    value=f"**Response:** {cmd['response'][:50]}...\n**Created by:** {creator_name}\n**Cooldown:** {cmd['cooldown']}s",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
        
        elif action_l == "edit":
            if not name:
                return await interaction.response.send_message(
                    embed=error_embed("Command name is required."),
                    ephemeral=True
                )
            
            # Check if command exists
            existing = await get_custom_command(guild.id, name.lower())
            if not existing:
                return await interaction.response.send_message(
                    embed=error_embed(f"Command `{name}` not found."),
                    ephemeral=True
                )
            
            # Update the command
            success = await update_custom_command(
                guild.id, name.lower(), response=response, cooldown=cooldown
            )
            
            if success:
                await interaction.response.send_message(
                    embed=success_embed("Custom Command Updated", f"Command `{name}` has been updated."),
                    ephemeral=False
                )
            else:
                await interaction.response.send_message(
                    embed=error_embed("Nothing to update. Please specify response or cooldown."),
                    ephemeral=True
                )
        
        else:
            await interaction.response.send_message(
                embed=error_embed("Invalid action. Use: create, delete, list, or edit"),
                ephemeral=True
            )

    # ── Custom Command Execution ──
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle custom command execution."""
        if not message.guild:
            return
        if message.author.bot:
            return
        
        guild = message.guild
        prefix = await self._get_prefix(guild)
        
        # Check if message starts with prefix
        if not message.content.startswith(prefix):
            return
        
        # Extract command name
        content = message.content[len(prefix):].strip().split()
        if not content:
            return
        
        command_name = content[0].lower()
        
        # Get the custom command
        cmd = await get_custom_command(guild.id, command_name)
        if not cmd:
            return
        
        # Check cooldown
        if cmd["cooldown"] > 0:
            cooldown_key = f"{guild.id}_{message.author.id}_{command_name}"
            if cooldown_key in self.cooldowns:
                if datetime.now(timezone.utc) < self.cooldowns[cooldown_key]:
                    remaining = (self.cooldowns[cooldown_key] - datetime.now(timezone.utc)).total_seconds()
                    await message.channel.send(
                        f"⏱️ {message.author.mention}, this command is on cooldown. Please wait {int(remaining)} seconds.",
                        delete_after=5
                    )
                    return
        
        # Check required role
        if cmd["required_role"]:
            required_role = guild.get_role(cmd["required_role"])
            if required_role and required_role not in message.author.roles:
                await message.channel.send(
                    f"🚫 {message.author.mention}, you don't have the required role to use this command.",
                    delete_after=5
                )
                return
        
        # Process and send the response
        response = self._process_response(message, cmd["response"])
        
        try:
            await message.channel.send(response)
            
            # Set cooldown
            if cmd["cooldown"] > 0:
                cooldown_key = f"{guild.id}_{message.author.id}_{command_name}"
                self.cooldowns[cooldown_key] = datetime.now(timezone.utc) + timedelta(seconds=cmd["cooldown"])
            
        except Exception as e:
            self.logger.error(f"Failed to execute custom command {command_name}: {e}", exc_info=True)
            try:
                await message.channel.send(
                    f"❌ Failed to execute command: {str(e)}",
                    delete_after=10
                )
            except:
                pass

    def _process_response(self, message: discord.Message, response: str) -> str:
        """Process custom command response with placeholders."""
        replacements = {
            "{user}": message.author.name,
            "{mention}": message.author.mention,
            "{server}": message.guild.name,
            "{member_count}": str(message.guild.member_count),
            "{channel}": message.channel.mention,
            "{user_id}": str(message.author.id),
            "{username}": f"{message.author.name}#{message.author.discriminator}",
        }
        
        for placeholder, value in replacements.items():
            response = response.replace(placeholder, value)
        
        return response

    async def _get_prefix(self, guild: discord.Guild) -> str:
        """Get the custom prefix for the guild."""
        from database import get_guild
        settings = await get_guild(guild.id)
        return settings.get("custom_prefix", "x")

    def _register_custom_command(self, guild_id: int, name: str):
        """Register a custom command for auto-sync (placeholder)."""
        # In a real implementation, this would sync to Discord's command registry
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomCommands(bot))