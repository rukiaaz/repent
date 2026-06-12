"""
Balance - Ticket/Support System
Customizable ticket system with transcripts and analytics.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import OWNER_ID
from database import get_guild, update_guild
from utils.embeds import success_embed, error_embed, info_embed

class TicketSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Store active tickets: {ticket_channel_id: {guild_id, user_id, category, created_at}}
        self.active_tickets = {}

    async def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID

    async def _is_mod(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.manage_channels or interaction.user.id == OWNER_ID

    # === Ticket Commands ===

    @app_commands.command(name="ticket", description="Create a support ticket")
    @app_commands.describe(category="Ticket category (optional)")
    async def ticket(self, interaction: discord.Interaction, category: str = "General"):
        guild = interaction.guild
        user = interaction.user
        settings = await get_guild(guild.id)
        
        # Get ticket category configuration
        categories = json.loads(settings.get("ticket_categories", "{}"))
        
        if categories and category in categories:
            cat_config = categories[category]
            role_id = cat_config.get("role_id")
            channel_id = cat_config.get("channel_id")
        else:
            # Default: create in general support channel
            channel = guild.get_channel(settings.get("mod_channel", 0))
            role_id = None
            if not channel:
                return await interaction.response.send_message(
                    embed=error_embed("No ticket channel configured. Ask admin to set one up."),
                    ephemeral=True
                )
        
        # Create ticket channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False, connect=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True)
        }
        
        # Add support role if configured
        if role_id:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True)
        
        ticket_num = len(self.active_tickets) + 1
        channel_name = f"ticket-{ticket_num}-{user.name.lower()}"
        
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=guild.get_channel(channel_id) if channel_id else None
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("Permission Error", "I don't have permission to create channels."),
                ephemeral=True
            )
        
        # Store ticket info
        self.active_tickets[channel.id] = {
            "guild_id": guild.id,
            "user_id": user.id,
            "category": category,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "messages": []
        }
        
        # Send welcome message
        embed = discord.Embed(
            title="🎫 Support Ticket",
            description=f"Hello {user.mention}! Support will be with you shortly.\n\n**Category:** {category}\n**Ticket #**: {ticket_num}",
            color=0x4488FF
        )
        embed.set_footer(text=f"User ID: {user.id}")
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.red, label="Close Ticket", custom_id=f"close_{channel.id}"))
        
        await channel.send(embed=embed, view=view)
        
        await interaction.response.send_message(
            embed=success_embed("Ticket Created", f"Your ticket has been created in {channel.mention}"),
            ephemeral=False
        )
        
        # Auto-create transcript on close (via button callback)
        async def close_button_callback(interaction: discord.Interaction):
            if interaction.custom_id.startswith("close_"):
                ticket_channel_id = interaction.custom_id.split("_")[1]
                if ticket_channel_id in self.active_tickets:
                    await self.close_ticket(ticket_channel_id, interaction.channel)
        
        self.bot.add_listener(close_button_callback, "on_interaction")

    async def close_ticket(self, ticket_channel_id: str, trigger_channel):
        """Close a ticket and generate transcript."""
        ticket_info = self.active_tickets.get(ticket_channel_id)
        if not ticket_info:
            return
        
        channel = self.bot.get_channel(ticket_channel_id)
        if not channel:
            return
        
        # Generate transcript
        transcript = []
        async for message in channel.history(limit=None):
            transcript.append({
                "author": message.author.name,
                "content": message.content,
                "timestamp": message.created_at.isoformat(),
                "attachments": [a.url for a in message.attachments]
            })
        
        # Delete channel
        try:
            await channel.delete()
        except:
            pass
        
        # Remove from active tickets
        del self.active_tickets[ticket_channel_id]
        
        # Store transcript in database (would need to add table)
        # For now, just log it
        print(f"Ticket closed: {ticket_channel_id}, Transcript length: {len(transcript)}")

    @app_commands.command(name="panel", description="Send ticket panel to channel (Admin only)")
    @app_commands.describe(channel="Channel to send panel to")
    async def panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self._is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        guild = interaction.guild
        settings = await get_guild(guild.id)
        categories = json.loads(settings.get("ticket_categories", "{}"))
        
        embed = discord.Embed(
            title="🎫 Support Tickets",
            description="Click a button below to create a ticket.",
            color=0x4488FF
        )
        embed.set_footer(text=f"Server: {guild.name}")
        
        view = discord.ui.View()
        for cat_name, cat_config in categories.items():
            button = discord.ui.Button(
                label=cat_config.get("name", cat_name),
                style=discord.ButtonStyle.blurple,
                custom_id=f"ticket_{cat_name}"
            )
            view.add_item(button)
        
        # Button callback would be similar to ticket command
        await channel.send(embed=embed, view=view)
        
        return await interaction.response.send_message(
            embed=success_embed("Panel Sent", f"Ticket panel sent to {channel.mention}"),
            ephemeral=False
        )

    @app_commands.command(name="ticket-setup", description="Configure ticket categories (Admin only)")
    @app_commands.describe(category="Category name", role="Role with access", channel="Category parent")
    async def ticket_setup(self, interaction: discord.Interaction, category: str, role: discord.Role = None, channel: discord.TextChannel = None):
        if not await self._is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        guild = interaction.guild
        settings = await get_guild(guild.id)
        categories = json.loads(settings.get("ticket_categories", "{}"))
        
        categories[category] = {
            "name": category,
            "role_id": role.id if role else None,
            "channel_id": channel.id if channel else None
        }
        
        await update_guild(guild.id, ticket_categories=json.dumps(categories))
        
        return await interaction.response.send_message(
            embed=success_embed("Category Added", f"Category '{category}' has been configured."),
            ephemeral=False
        )

    @app_commands.command(name="ticket-categories", description="List ticket categories")
    async def ticket_categories(self, interaction: discord.Interaction):
        settings = await get_guild(interaction.guild.id)
        categories = json.loads(settings.get("ticket_categories", "{}"))
        
        if not categories:
            return await interaction.response.send_message(
                embed=info_embed("No Categories", "No ticket categories configured."),
                ephemeral=False
            )
        
        embed = discord.Embed(title="📋 Ticket Categories", color=0x4488FF)
        for cat_name, cat_config in categories.items():
            role = interaction.guild.get_role(cat_config["role_id"]) if cat_config.get("role_id") else None
            embed.add_field(
                name=cat_config["name"],
                value=f"Role: {role.mention if role else 'None'}\nCategory Channel: {cat_config.get('channel_id') or 'None'}",
                inline=False
            )
        
        return await interaction.response.send_message(embed=embed, ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketSystem(bot))