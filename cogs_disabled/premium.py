"""Repent - Premium Features

Bot profile customization and premium features.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config import OWNER_ID
from database import get_guild, update_guild
from utils.embeds import success_embed, error_embed, info_embed


class Premium(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _is_bot_owner(self, interaction: discord.Interaction) -> bool:
        """Check if user is bot owner."""
        return interaction.user.id == OWNER_ID

    @app_commands.command(name="setpfp", description="Change the bot's profile picture (Bot Owner only)")
    @app_commands.describe(url="URL of the new profile picture")
    async def setpfp(self, interaction: discord.Interaction, url: str):
        if not await self._is_bot_owner(interaction):
            return await interaction.response.send_message(
                embed=error_embed("This command is restricted to the bot owner."), 
                ephemeral=True
            )

        try:
            async with self.bot.http.session.get(url) as response:
                if response.status != 200:
                    return await interaction.response.send_message(
                        embed=error_embed("Failed to fetch image. Check the URL."),
                        ephemeral=True
                    )
                image_data = await response.read()
            
            await self.bot.user.edit(avatar=image_data)
            await interaction.response.send_message(
                embed=success_embed("Profile Picture Updated", "Bot profile picture has been changed."),
                ephemeral=False,
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed(f"Failed to update profile picture: {str(e)}"),
                ephemeral=True,
            )

    @app_commands.command(name="setbanner", description="Change the bot's banner (Bot Owner only, requires Nitro)")
    @app_commands.describe(url="URL of the new banner")
    async def setbanner(self, interaction: discord.Interaction, url: str):
        if not await self._is_bot_owner(interaction):
            return await interaction.response.send_message(
                embed=error_embed("This command is restricted to the bot owner."), 
                ephemeral=True
            )

        try:
            async with self.bot.http.session.get(url) as response:
                if response.status != 200:
                    return await interaction.response.send_message(
                        embed=error_embed("Failed to fetch image. Check the URL."),
                        ephemeral=True
                    )
                image_data = await response.read()
            
            await self.bot.user.edit(banner=image_data)
            await interaction.response.send_message(
                embed=success_embed("Banner Updated", "Bot banner has been changed."),
                ephemeral=False,
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed(f"Failed to update banner: {str(e)}\nNote: This requires Discord Nitro."),
                ephemeral=True,
            )

    @app_commands.command(name="setbotname", description="Change the bot's username (Bot Owner only)")
    @app_commands.describe(username="New username for the bot")
    async def setbotname(self, interaction: discord.Interaction, username: str):
        if not await self._is_bot_owner(interaction):
            return await interaction.response.send_message(
                embed=error_embed("This command is restricted to the bot owner."), 
                ephemeral=True
            )

        if len(username) < 2 or len(username) > 32:
            return await interaction.response.send_message(
                embed=error_embed("Username must be between 2 and 32 characters."),
                ephemeral=True,
            )

        try:
            await self.bot.user.edit(username=username)
            await interaction.response.send_message(
                embed=success_embed("Username Updated", f"Bot username changed to `{username}`."),
                ephemeral=False,
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed(f"Failed to update username: {str(e)}"),
                ephemeral=True,
            )

    @app_commands.command(name="setbio", description="Change the bot's bio/about me (Bot Owner only)")
    @app_commands.describe(bio="New bio for the bot")
    async def setbio(self, interaction: discord.Interaction, bio: str):
        if not await self._is_bot_owner(interaction):
            return await interaction.response.send_message(
                embed=error_embed("This command is restricted to the bot owner."), 
                ephemeral=True
            )

        if len(bio) > 190:
            return await interaction.response.send_message(
                embed=error_embed("Bio must be 190 characters or less."),
                ephemeral=True,
            )

        try:
            # Note: This requires special Discord API permissions that may not be available
            await self.bot.user.edit(bio=bio)
            await interaction.response.send_message(
                embed=success_embed("Bio Updated", "Bot bio has been changed."),
                ephemeral=False,
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed(f"Failed to update bio: {str(e)}\nNote: This requires special Discord permissions."),
                ephemeral=True,
            )

    @app_commands.command(name="setprofile", description="Set complete bot profile (Bot Owner only)")
    @app_commands.describe(username="New username", avatar_url="URL of new avatar", bio="New bio")
    async def setprofile(self, interaction: discord.Interaction, username: str = None, avatar_url: str = None, bio: str = None):
        if not await self._is_bot_owner(interaction):
            return await interaction.response.send_message(
                embed=error_embed("This command is restricted to the bot owner."), 
                ephemeral=True
            )

        if not any([username, avatar_url, bio]):
            return await interaction.response.send_message(
                embed=error_embed("Provide at least one field to update."),
                ephemeral=True,
            )

        try:
            update_data = {}
            
            if username:
                if len(username) < 2 or len(username) > 32:
                    return await interaction.response.send_message(
                        embed=error_embed("Username must be between 2 and 32 characters."),
                        ephemeral=True,
                    )
                update_data['username'] = username
            
            if avatar_url:
                async with self.bot.http.session.get(avatar_url) as response:
                    if response.status != 200:
                        return await interaction.response.send_message(
                            embed=error_embed("Failed to fetch image. Check the URL."),
                            ephemeral=True
                        )
                    update_data['avatar'] = await response.read()
            
            if bio:
                if len(bio) > 190:
                    return await interaction.response.send_message(
                        embed=error_embed("Bio must be 190 characters or less."),
                        ephemeral=True,
                    )
                update_data['bio'] = bio
            
            await self.bot.user.edit(**update_data)
            
            changes = []
            if username:
                changes.append(f"Username: `{username}`")
            if avatar_url:
                changes.append("Avatar updated")
            if bio:
                changes.append("Bio updated")
            
            await interaction.response.send_message(
                embed=success_embed("Profile Updated", "\n".join(changes)),
                ephemeral=False,
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed(f"Failed to update profile: {str(e)}"),
                ephemeral=True,
            )

    @app_commands.command(name="resetbot", description="Reset bot to default settings (Bot Owner only)")
    async def resetbot(self, interaction: discord.Interaction):
        if not await self._is_bot_owner(interaction):
            return await interaction.response.send_message(
                embed=error_embed("This command is restricted to the bot owner."), 
                ephemeral=True
            )

        await interaction.response.send_message(
            embed=info_embed("Reset Bot", "This command would reset the bot to default settings. Are you sure?"),
            ephemeral=True
        )
        # Note: This is a placeholder for a more comprehensive reset function


async def setup(bot: commands.Bot):
    await bot.add_cog(Premium(bot))