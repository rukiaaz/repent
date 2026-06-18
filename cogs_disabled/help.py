"""Repent - Slash Help

Adds /help for a unified dropdown-based command menu.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class HelpDropdown(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        options = [
            discord.SelectOption(
                label="Setup & Configuration",
                description="Setup wizard, config, whitelist",
                value="setup"
            ),
            discord.SelectOption(
                label="Logging System",
                description="Channel logs, message logs, moderation logs",
                value="logging"
            ),
            discord.SelectOption(
                label="Antinuke & Security",
                description="Antinuke, restore, punished users",
                value="antinuke"
            ),
            discord.SelectOption(
                label="Backup & Restore",
                description="Server backups and restoration",
                value="backup"
            ),
            discord.SelectOption(
                label="Trust Levels & Whitelists",
                description="User and bot whitelisting",
                value="whitelist"
            ),
            discord.SelectOption(
                label="Moderation",
                description="Ban, kick, timeout, warnings",
                value="moderation"
            ),
            discord.SelectOption(
                label="Case Management",
                description="Moderation cases and modmail system",
                value="cases"
            ),
            discord.SelectOption(
                label="Reaction Roles",
                description="Self-assignable roles with buttons",
                value="reaction_roles"
            ),
            discord.SelectOption(
                label="Custom Commands",
                description="Create custom server commands",
                value="custom_commands"
            ),
            discord.SelectOption(
                label="Leveling System",
                description="XP, ranks, and level rewards",
                value="leveling"
            ),
            discord.SelectOption(
                label="AutoMod",
                description="Anti-spam, anti-mention, content filtering",
                value="automod"
            ),
        ]
        super().__init__(
            placeholder="Select a category to view commands...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        embed = discord.Embed(
            title=f"Repent Bot Commands - {category}",
            color=0x4488FF
        )

        if category == "setup":
            embed.description = "Bot setup and configuration"
            embed.add_field(
                name="Commands",
                value="`/setup` - Interactive setup wizard\n"
                      "`/quicksetup` - Quick setup (logs, punishment, whitelist)\n"
                      "`/config view` - View configuration\n"
                      "`/config logchannel` - Set log channel\n"
                      "`/config modchannel` - Set mod channel\n"
                      "`/config punishment` - Set punishment type\n"
                      "`/config threshold` - Set antinuke threshold\n"
                      "`/antinuke enable/disable` - Toggle antinuke\n"
                      "`/antinuke status` - View antinuke status\n"
                      "`/antinukeconfig sensitivity` - Set sensitivity\n"
                      "`/antinukeconfig lockdown` - Toggle lockdown\n"
                      "`/antinukeconfig instantrestore` - Toggle instant restore\n"
                      "`/rolewhitelist add/remove` - Manage role whitelists",
                inline=False
            )

        elif category == "logging":
            embed.description = "Advanced logging system configuration"
            embed.add_field(
                name="Commands",
                value="`/setchannellog` - Set channel for message edit/delete logs\n"
                      "`/setguildlog` - Set channel for guild event logs\n"
                      "`/setmsglog` - Set channel for all message logs\n"
                      "`/setvclog` - Set channel for voice channel logs\n"
                      "`/setmodlog` - Set channel for moderation action logs\n"
                      "`/config logchannel` - Set main log channel\n"
                      "`/config modchannel` - Set mod log channel\n"
                      "`/antinukelog` - View recent antinuke security events",
                inline=False
            )

        elif category == "antinuke":
            embed.description = "Antinuke and security commands"
            embed.add_field(
                name="Commands",
                value="`/antinuke enable/disable` - Toggle antinuke\n"
                      "`/antinuke status` - View status\n"
                      "`/antinukelog` - View recent antinuke events\n"
                      "`/antinukeconfig sensitivity` - Set sensitivity\n"
                      "`/antinukeconfig lockdown` - Toggle lockdown\n"
                      "`/antinukeconfig instantrestore` - Toggle instant restore\n"
                      "`/antinukeconfig logging` - Toggle logging\n"
                      "`/safeadmin add/remove` - Manage safe admins\n"
                      "`/safeadmin list` - View safe admins\n"
                      "`/antinuke_restore` - Restore deleted roles/channels\n"
                      "`/punished` - List punished users\n"
                      "`/pardon` - Remove user from punished list",
                inline=False
            )

        elif category == "antiraid":
            embed.description = "Anti-raid system commands"
            embed.add_field(
                name="Commands",
                value="`/raid status` - View configuration & status\n"
                      "`/raid toggle` - Toggle server lockdown\n"
                      "`/raid unlock` - Lift lockdown\n"
                      "`/raid sensitivity` - Set detection sensitivity\n"
                      "`/raid maxjoins` - Set max joins before lockdown\n"
                      "`/raid minage` - Set minimum account age\n"
                      "`/raid quarantine` - Set quarantine channel\n"
                      "`/raid webhook` - Set raid alert webhook\n"
                      "`/raid auto` - Toggle automatic raid mode\n"
                      "`/raidscore` - Check user raid score",
                inline=False
            )

        elif category == "backup":
            embed.description = "Server backup and restoration"
            embed.add_field(
                name="Commands",
                value="`/backup create` - Create backup snapshot\n"
                      "`/backup list` - List all backups\n"
                      "`/backup delete` - Delete backup\n"
                      "`/backup restore` - Restore from backup",
                inline=False
            )

        elif category == "moderation":
            embed.description = "User moderation commands"
            embed.add_field(
                name="Commands",
                value="`/ban` - Ban a user\n"
                      "`/unban` - Unban a user\n"
                      "`/kick` - Kick a user\n"
                      "`/timeout` - Timeout a user\n"
                      "`/untimeout` - Remove timeout\n"
                      "`/warn` - Warn a user\n"
                      "`/warnings` - View warnings\n"
                      "`/clearwarns` - Clear warnings\n"
                      "`/hardban` - Hardban (auto-reban)\n"
                      "`/unhardban` - Remove hardban\n"
                      "`/purge` - Purge messages\n"
                      "`/purgeuser` - Purge messages from user\n"
                      "`/lock/unlock` - Lock/unlock channel\n"
                      "`/slowmode` - Set slowmode\n"
                      "`/nick` - Change nickname\n"
                      "`/roleadd` - Add role to user\n"
                      "`/roleremove` - Remove role from user",
                inline=False
            )

        elif category == "whitelist":
            embed.description = "User and bot whitelist management"
            embed.add_field(
                name="Commands",
                value="`/whitelist add/remove` - Manage user whitelist\n"
                      "`/whitelist list` - View whitelisted users\n"
                      "`/botwhitelist add/remove` - Manage bot whitelist\n"
                      "`/botwhitelist list` - View whitelisted bots\n"
                      "`/safeadmin add/remove` - Manage safe admins\n"
                      "`/safeadmin list` - View safe admins\n"
                      "`/rolewhitelist add/remove` - Manage role whitelists\n\n"
                      "**Level 1:** Bypasses AutoMod\n"
                      "**Level 2:** Bypasses AutoMod + Antinuke\n"
                      "**Bot Whitelist:** Bots immune to antinuke\n"
                      "**Safe Admins:** Immune to all punishments",
                inline=False
            )

        elif category == "leveling":
            embed.description = "XP, leveling, and reward system"
            embed.add_field(
                name="Commands",
                value="`/rank` - View your rank card\n"
                      "`/leaderboard` - View server leaderboard\n"
                      "`/setlevel` - Set user level (Admin)\n"
                      "`/resetxp` - Reset user XP (Admin)\n"
                      "`/levelrole add` - Add level reward role\n"
                      "`/levelrole remove` - Remove level reward role\n"
                      "`/levelrole list` - View level rewards",
                inline=False
            )
            embed.add_field(
                name="Features",
                value="• XP gain per message\n• Level-up notifications\n• Role rewards for levels\n• Leaderboard tracking",
                inline=False
            )

        elif category == "automod":
            embed.description = "AutoMod system - automatic message filtering and moderation"
            embed.add_field(
                name="Commands",
                value="`/automod` - Enable/disable automod\n"
                      "`/badword` - Manage bad word filter\n"
                      "`/ignore` - Ignore channel from automod\n"
                      "`/unignore` - Remove channel from ignore list\n"
                      "`/antinsfw` - Toggle anti-NSFW filter\n"
                      "`/antilink` - Toggle anti-link filter\n"
                      "`/antimention` - Toggle anti-mention filter\n"
                      "`/antispam` - Toggle anti-spam filter\n"
                      "`/antiraid` - Toggle anti-raid mode",
                inline=False
            )

        elif category == "cases":
            embed.description = "Professional case management and modmail system"
            embed.add_field(
                name="Commands",
                value="`/case create` - Create a moderation case\n"
                      "`/case view` - View case details\n"
                      "`/case resolve` - Mark a case as resolved\n"
                      "`/case add_evidence` - Add evidence to a case\n"
                      "`/cases` - View all recent cases or user cases\n"
                      "`/modmail setup` - Configure modmail system\n"
                      "`/modmail list` - View open modmail threads",
                inline=False
            )
            embed.add_field(
                name="Features",
                value="• Case tracking with case numbers\n• Evidence management\n• DM-to-server modmail\n• Auto-response system",
                inline=False
            )

        elif category == "reaction_roles":
            embed.description = "Self-assignable roles with buttons or reactions"
            embed.add_field(
                name="Commands",
                value="`/createrole` - Create a role message\n"
                      "`/addtorole` - Add role to a message\n"
                      "`/finalizerole` - Activate role message\n"
                      "`/removerole` - Remove role from message",
                inline=False
            )
            embed.add_field(
                name="Features",
                value="• Button-based role assignment\n• Reaction-based roles\n• Role cooldowns\n• Required/blacklist roles",
                inline=False
            )

        elif category == "custom_commands":
            embed.description = "Create custom server-specific commands"
            embed.add_field(
                name="Commands",
                value="`/customcmd create` - Create a custom command\n"
                      "`/customcmd edit` - Edit an existing command\n"
                      "`/customcmd delete` - Delete a custom command\n"
                      "`/customcmd list` - View all custom commands",
                inline=False
            )
            embed.add_field(
                name="Placeholders",
                value="• {user} - Username\n• {mention} - User mention\n• {server} - Server name\n• {channel} - Channel mention\n• {member_count} - Member count",
                inline=False
            )

        elif category == "security":
            embed.description = "Advanced security scanning and protection"
            embed.add_field(
                name="Commands",
                value="`/antitoken enable` - Enable token grabber detection\n"
                      "`/antitoken disable` - Disable token grabber detection\n"
                      "`/antitoken check` - Check a URL for safety",
                inline=False
            )
            embed.add_field(
                name="Features",
                value="• Token grabber link detection\n• Malicious domain blacklist\n• Pattern-based scanning\n• Auto-delete suspicious links",
                inline=False
            )

        elif category == "advanced_logging":
            embed.description = "Comprehensive event logging"
            embed.add_field(
                name="Commands",
                value="`/logging enable` - Enable event logging\n"
                      "`/logging disable` - Disable event logging\n"
                      "`/logging configure` - Configure log channels\n"
                      "`/setchannellog` - Channel edit/delete logs\n"
                      "`/setguildlog` - Guild event logs\n"
                      "`/setmsglog` - All message logs\n"
                      "`/setvclog` - Voice channel logs\n"
                      "`/setmodlog` - Moderation action logs",
                inline=False
            )
            embed.add_field(
                name="Events Logged",
                value="• Voice joins/leaves/moves\n• Thread creation/deletion\n• Role additions/removals\n• Nickname changes",
                inline=False
            )

        embed.set_footer(text="Repent Security Bot | Use /help to see this menu")
        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(HelpDropdown(bot))


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show all bot commands in a dropdown menu")
    async def help_slash(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Repent Bot Help",
            description="Advanced Discord security bot. Select a category below to view commands.",
            color=0x4488FF
        )
        embed.add_field(
            name="Security",
            value="Antinuke • Anti-Raid • AutoMod",
            inline=False
        )
        embed.add_field(
            name="Moderation",
            value="Ban • Kick • Timeout • Warnings",
            inline=False
        )
        embed.add_field(
            name="Features",
            value="Welcome • Leveling • Backup",
            inline=False
        )
        embed.set_footer(text="Select a category to get started")

        view = HelpView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
