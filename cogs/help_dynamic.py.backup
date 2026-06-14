"""
Repent - Dynamic Help System
Dynamically generates help from actual loaded commands.
NEVER shows commands that don't exist or don't work.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Dict, List, Optional, Set
from enum import Enum


class CommandCategory(Enum):
    """Categories for organizing commands."""
    SETUP = "Setup & Configuration"
    LOGGING = "Logging System"
    SECURITY = "Antinuke & Security"
    MODERATION = "Moderation"
    BACKUP = "Backup & Restore"
    TICKETS = "Tickets & Support"
    UTILITY = "Utility & Fun"
    PREMIUM = "Premium"
    VERIFICATION = "Verification"
    CUSTOM = "Custom Commands"
    OTHER = "Other"


class DynamicHelpSystem:
    """Dynamic help system that reads from actual loaded commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.categories: Dict[CommandCategory, List[app_commands.AppCommand]] = {}
        self._categorize_commands()
    
    def _categorize_commands(self):
        """Categorize all loaded commands based on their cog and name."""
        # Clear existing categories
        self.categories = {cat: [] for cat in CommandCategory}
        
        # Walk the command tree
        for command in self.bot.tree.walk_commands():
            category = self._determine_category(command)
            self.categories[category].append(command)
        
        self._log_categories()
    
    def _determine_category(self, command: app_commands.AppCommand) -> CommandCategory:
        """Determine the category for a command based on its name and parent cog."""
        cmd_name = command.qualified_name.lower()
        cog_name = command.binding.__class__.__name__.lower() if command.binding else ""
        
        # Setup & Configuration
        if any(kw in cmd_name for kw in ['setup', 'quicksetup', 'config', 'antinukeconfig']):
            return CommandCategory.SETUP
        
        # Logging
        if any(kw in cmd_name for kw in ['setchannellog', 'setguildlog', 'setmsglog', 'setvclog', 'setmodlog']):
            return CommandCategory.LOGGING
        
        # Security / Antinuke
        if any(kw in cmd_name for kw in ['antinuke', 'whitelist', 'botwhitelist', 'safeadmin', 'rolewhitelist', 'defense', 'trust']):
            return CommandCategory.SECURITY
        
        # Moderation
        if any(kw in cmd_name for kw in ['ban', 'kick', 'timeout', 'warn', 'purge', 'lock', 'slowmode', 'hardban', 'case']):
            return CommandCategory.MODERATION
        
        # Backup
        if any(kw in cmd_name for kw in ['backup', 'create', 'restore']) or 'backup' in cog_name:
            return CommandCategory.BACKUP
        
        # Tickets
        if any(kw in cmd_name for kw in ['ticket', 'panel']) or 'ticket' in cog_name:
            return CommandCategory.TICKETS
        
        # Utility
        if any(kw in cmd_name for kw in ['userinfo', 'serverinfo', 'avatar', 'ping', 'uptime', 'afk', 'botinfo', 'invite', 'health']):
            return CommandCategory.UTILITY
        
        # Premium
        if any(kw in cmd_name for kw in ['premium']) or 'premium' in cog_name:
            return CommandCategory.PREMIUM
        
        # Verification
        if any(kw in cmd_name for kw in ['captcha', 'verify']) or 'captcha' in cog_name or 'verification' in cog_name:
            return CommandCategory.VERIFICATION
        
        # Custom
        if 'custom' in cmd_name or 'custom' in cog_name:
            return CommandCategory.CUSTOM
        
        # Default to other
        return CommandCategory.OTHER
    
    def _log_categories(self):
        """Log the categorization for debugging."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Dynamic Help System - Command Categorization:")
        for category, commands in self.categories.items():
            if commands:
                logger.info(f"  {category.value}: {len(commands)} commands")
    
    def get_category_commands(self, category: CommandCategory) -> List[app_commands.AppCommand]:
        """Get all commands in a category."""
        return self.categories.get(category, [])
    
    def get_all_categories(self) -> List[CommandCategory]:
        """Get all categories that have commands."""
        return [cat for cat in CommandCategory if self.categories.get(cat)]
    
    def generate_help_embed(self, category: CommandCategory) -> discord.Embed:
        """Generate a help embed for a specific category."""
        commands = self.get_category_commands(category)
        
        embed = discord.Embed(
            title=f"Repent Bot Commands - {category.value}",
            description=f"Commands in the {category.value} category",
            color=0x4488FF
        )
        
        if commands:
            # Sort commands by name
            commands.sort(key=lambda c: c.qualified_name)
            
            # Build command list
            command_list = []
            for cmd in commands:
                desc = cmd.description or "No description"
                command_list.append(f"`/{cmd.qualified_name}` - {desc}")
            
            embed.add_field(
                name="Commands",
                value="\n".join(command_list),
                inline=False
            )
            
            embed.add_field(
                name="Total",
                value=f"{len(commands)} commands",
                inline=True
            )
        else:
            embed.add_field(
                name="Commands",
                value="No commands in this category",
                inline=False
            )
        
        embed.set_footer(text="Repent Security Bot | Dynamically generated from loaded commands")
        return embed
    
    def generate_main_embed(self) -> discord.Embed:
        """Generate the main help embed with category overview."""
        embed = discord.Embed(
            title="Repent Bot Help",
            description="Advanced Discord security bot. Select a category below to view commands.",
            color=0x4488FF
        )
        
        # Add category overview
        for category in self.get_all_categories():
            cmd_count = len(self.get_category_commands(category))
            if cmd_count > 0:
                embed.add_field(
                    name=category.value,
                    value=f"{cmd_count} commands",
                    inline=True
                )
        
        # Add total
        total_commands = sum(len(cmds) for cmds in self.categories.values())
        embed.add_field(
            name="Total Commands",
            value=f"{total_commands}",
            inline=False
        )
        
        embed.set_footer(text="Select a category to get started | Dynamically generated from loaded commands")
        
        return embed


class DynamicHelpView(discord.ui.View):
    """Dynamic help view with dropdown that only shows available categories."""
    
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.help_system = DynamicHelpSystem(bot)
        self._build_dropdown()
    
    def _build_dropdown(self):
        """Build the dropdown with only available categories."""
        categories = self.help_system.get_all_categories()
        
        options = []
        for category in categories:
            cmd_count = len(self.help_system.get_category_commands(category))
            options.append(
                discord.SelectOption(
                    label=category.value,
                    description=f"{cmd_count} commands",
                    value=category.name
                )
            )
        
        if not options:
            # Fallback if no commands
            options.append(
                discord.SelectOption(
                    label="No Commands",
                    description="No commands available",
                    value="none"
                )
            )
        
        dropdown = CategoryDropdown(self.help_system, options)
        self.add_item(dropdown)


class CategoryDropdown(discord.ui.Select):
    """Dropdown for selecting command categories."""
    
    def __init__(self, help_system: DynamicHelpSystem, options: List[discord.SelectOption]):
        self.help_system = help_system
        super().__init__(
            placeholder="Select a category to view commands...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        category_name = self.values[0]
        
        if category_name == "none":
            embed = discord.Embed(
                title="No Commands",
                description="No commands are currently loaded.",
                color=0xFF4444
            )
            await interaction.response.edit_message(embed=embed)
            return
        
        try:
            category = CommandCategory[category_name]
            embed = self.help_system.generate_help_embed(category)
            await interaction.response.edit_message(embed=embed)
        except KeyError:
            await interaction.response.edit_message(
                content="Category not found",
                embed=None
            )


class Help(commands.Cog):
    """Dynamic help cog that never shows dead commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="help", description="Show all bot commands (dynamically generated from loaded commands)")
    async def help_slash(self, interaction: discord.Interaction):
        """Show dynamically generated help."""
        help_system = DynamicHelpSystem(self.bot)
        embed = help_system.generate_main_embed()
        view = DynamicHelpView(self.bot)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


async def setup(bot: commands.Bot):
    """Setup the dynamic help cog."""
    await bot.add_cog(Help(bot))
