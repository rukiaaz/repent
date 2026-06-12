"""
Balance - Captcha Verification
Simple math captcha for user verification.
"""

from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from config import OWNER_ID
from database import get_guild, update_guild
from utils.embeds import success_embed, error_embed, info_embed

class Captcha(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Store active challenges: {user_id: {answer, timestamp, attempts}}
        self.challenges = {}

    async def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID

    @app_commands.command(name="captcha", description="Configure captcha system (Admin only)")
    @app_commands.describe(action="enable, disable, difficulty, or status")
    async def captcha(self, interaction: discord.Interaction, action: str):
        if not await self._is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        guild = interaction.guild
        settings = await get_guild(guild.id)
        action_l = action.lower()

        if action_l == "enable":
            await update_guild(guild.id, captcha_enabled=1)
            return await interaction.response.send_message(
                embed=success_embed("Captcha Enabled", "Captcha verification has been enabled."),
                ephemeral=False
            )

        elif action_l == "disable":
            await update_guild(guild.id, captcha_enabled=0)
            return await interaction.response.send_message(
                embed=success_embed("Captcha Disabled", "Captcha verification has been disabled."),
                ephemeral=False
            )

        elif action_l == "difficulty":
            await update_guild(guild.id, captcha_difficulty=1)
            return await interaction.response.send_message(
                embed=success_embed("Difficulty Set", "Captcha difficulty set to easy (2 numbers, 1-10)."),
                ephemeral=False
            )

        elif action_l == "status":
            enabled = settings.get("captcha_enabled", 0)
            difficulty = settings.get("captcha_difficulty", 1)
            embed = discord.Embed(title="🔢 Captcha Status", color=0x4488FF)
            embed.add_field(name="Status", value="✅ Enabled" if enabled else "❌ Disabled", inline=True)
            embed.add_field(name="Difficulty", value=f"Level {difficulty}", inline=True)
            return await interaction.response.send_message(embed=embed, ephemeral=False)

        else:
            return await interaction.response.send_message(
                embed=error_embed("Use: `enable`, `disable`, `difficulty`, or `status`."),
                ephemeral=True
            )

    @app_commands.command(name="verify-captcha", description="Complete captcha verification")
    async def verify_captcha(self, interaction: discord.Interaction, answer: int):
        user_id = interaction.user.id
        
        if user_id not in self.challenges:
            return await interaction.response.send_message(
                embed=error_embed("No Active Challenge", "You don't have an active captcha challenge."),
                ephemeral=True
            )
        
        challenge = self.challenges[user_id]
        
        if challenge["answer"] == answer:
            del self.challenges[user_id]
            # Grant verification role
            settings = await get_guild(interaction.guild.id)
            role_id = settings.get("captcha_role", 0)
            
            if role_id:
                role = interaction.guild.get_role(role_id)
                if role:
                    await interaction.user.add_roles(role, reason="[Balance] Captcha verification passed")
                    return await interaction.response.send_message(
                        embed=success_embed("Verification Passed", f"You have been verified and received {role.mention}!"),
                        ephemeral=True
                    )
            
            return await interaction.response.send_message(
                embed=success_embed("Verification Passed", "Captcha verification successful!"),
                ephemeral=True
            )
        else:
            challenge["attempts"] += 1
            if challenge["attempts"] >= 3:
                del self.challenges[user_id]
                return await interaction.response.send_message(
                    embed=error_embed("Too Many Attempts", "Captcha challenge failed. Please try again later."),
                    ephemeral=True
                )
            return await interaction.response.send_message(
                embed=error_embed("Wrong Answer", f"Wrong answer. Attempts remaining: {3 - challenge['attempts']}"),
                ephemeral=True
            )

    async def create_captcha(self, member: discord.Member):
        """Create a captcha challenge for a member."""
        # Generate simple math problem
        num1 = random.randint(1, 10)
        num2 = random.randint(1, 10)
        answer = num1 + num2
        
        self.challenges[member.id] = {
            "answer": answer,
            "timestamp": discord.utils.utcnow(),
            "attempts": 0
        }
        
        embed = discord.Embed(
            title="🔐 Captcha Verification Required",
            description=f"Solve this math problem to continue:\n\n**{num1} + {num2} = ?**\n\nUse `/verify-captcha [answer]` to submit your answer.",
            color=0xFF4444
        )
        embed.set_footer(text=f"User ID: {member.id}")
        
        try:
            await member.send(embed=embed)
        except:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(Captcha(bot))