"""
Repent - Complete Command Discovery & Validation System
Scans entire codebase for commands, validates loading, sync status, and execution capability.
"""

import os
import ast
import re
import asyncio
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from enum import Enum


class CommandStatus(Enum):
    """Status of a command in the validation process."""
    DISCOVERED = "discovered"  # Found in code
    LOADED = "loaded"          # Successfully loaded by bot
    REGISTERED = "registered"  # Registered to command tree
    SYNCED = "synced"          # Synced to Discord
    FUNCTIONAL = "functional"  # Executes successfully
    BROKEN = "broken"          # Failed to load/execute
    MISSING = "missing"        # Exists in help but not in code


@dataclass
class CommandInfo:
    """Information about a discovered command."""
    name: str
    cog: str
    file: str
    line: int
    command_type: str  # app_commands.command, etc.
    description: str
    parameters: List[Dict[str, Any]]
    status: CommandStatus = CommandStatus.DISCOVERED
    load_error: Optional[str] = None
    sync_error: Optional[str] = None
    execution_error: Optional[str] = None


class CommandDiscovery:
    """Discover and validate all commands in the codebase."""
    
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.commands: Dict[str, CommandInfo] = {}
        self.cogs: Set[str] = set()
        
    def scan_codebase(self) -> Dict[str, CommandInfo]:
        """
        Scan the entire codebase for all commands.
        
        Returns:
            Dictionary mapping command names to CommandInfo objects
        """
        print("=" * 70)
        print("COMMAND DISCOVERY - SCANNING CODEBASE")
        print("=" * 70)
        
        cogs_dir = os.path.join(self.project_root, "cogs")
        
        if not os.path.exists(cogs_dir):
            print(f"[ERROR] Cogs directory not found: {cogs_dir}")
            return self.commands
        
        # Scan each cog file
        for filename in os.listdir(cogs_dir):
            if not filename.endswith(".py") or filename == "__init__.py":
                continue
            
            filepath = os.path.join(cogs_dir, filename)
            cog_name = f"cogs.{filename[:-3]}"
            
            self._scan_file(filepath, cog_name)
            self.cogs.add(cog_name)
        
        print(f"\n[OK] Discovered {len(self.commands)} commands across {len(self.cogs)} cogs")
        return self.commands
    
    def _scan_file(self, filepath: str, cog_name: str):
        """Scan a single Python file for command definitions."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
            
            # Find all @app_commands.command decorators
            for line_num, line in enumerate(lines, 1):
                # Match @app_commands.command
                if '@app_commands.command' in line:
                    # Find the next non-empty line (should be the function def)
                    func_def = None
                    func_line = None
                    for i in range(line_num, min(line_num + 5, len(lines))):
                        if lines[i].strip().startswith('async def '):
                            func_def = lines[i]
                            func_line = i + 1
                            break
                    
                    if func_def:
                        # Extract command name
                        name_match = re.search(r'name="([^"]+)"', line)
                        desc_match = re.search(r'description="([^"]+)"', line)
                        
                        command_name = name_match.group(1) if name_match else None
                        if not command_name:
                            # Try to extract from function name
                            func_name_match = re.search(r'async def (\w+)', func_def)
                            if func_name_match:
                                command_name = func_name_match.group(1)
                        
                        if command_name:
                            description = desc_match.group(1) if desc_match else ""
                            
                            self.commands[command_name] = CommandInfo(
                                name=command_name,
                                cog=cog_name,
                                file=filepath,
                                line=line_num,
                                command_type="app_commands.command",
                                description=description,
                                parameters=[]
                            )
                            print(f"  [OK] {cog_name}: /{command_name}")
                            
        except Exception as e:
            print(f"  [ERROR] Error scanning {filepath}: {e}")
    
    def generate_report(self) -> str:
        """Generate a comprehensive command report."""
        report = []
        report.append("=" * 70)
        report.append("COMMAND DISCOVERY REPORT")
        report.append("=" * 70)
        report.append(f"\nTotal Commands Discovered: {len(self.commands)}")
        report.append(f"Total Cogs Scanned: {len(self.cogs)}")
        report.append("\n" + "=" * 70)
        report.append("COMMANDS BY COG")
        report.append("=" * 70)
        
        # Group by cog
        by_cog: Dict[str, List[CommandInfo]] = {}
        for cmd in self.commands.values():
            if cmd.cog not in by_cog:
                by_cog[cmd.cog] = []
            by_cog[cmd.cog].append(cmd)
        
        for cog in sorted(by_cog.keys()):
            report.append(f"\n{cog} ({len(by_cog[cog])} commands):")
            for cmd in sorted(by_cog[cog], key=lambda x: x.name):
                report.append(f"  /{cmd.name} - {cmd.description or 'No description'}")
        
        report.append("\n" + "=" * 70)
        return "\n".join(report)


class CommandValidator:
    """Validate command loading, registration, and execution."""
    
    def __init__(self, bot):
        self.bot = bot
        self.discovery = CommandDiscovery(os.path.dirname(os.path.dirname(__file__)))
        self.validation_results: Dict[str, Dict[str, Any]] = {}
    
    async def validate_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Validate all commands through the entire lifecycle.
        
        Returns:
            Dictionary mapping command names to validation results
        """
        print("\n" + "=" * 70)
        print("COMMAND VALIDATION - STARTING")
        print("=" * 70)
        
        # Step 1: Discover all commands in code
        discovered = self.discovery.scan_codebase()
        
        # Step 2: Check which are loaded in the bot
        await self._check_loaded_commands(discovered)
        
        # Step 3: Check which are registered in the tree
        self._check_registered_commands(discovered)
        
        # Step 4: Check which are synced to Discord
        await self._check_synced_commands()
        
        # Step 5: Validate each command can execute (basic checks)
        await self._validate_command_execution(discovered)
        
        return self.validation_results
    
    async def _check_loaded_commands(self, discovered: Dict[str, CommandInfo]):
        """Check which commands are successfully loaded by the bot."""
        print("\n" + "=" * 70)
        print("STEP 2: CHECKING LOADED COMMANDS")
        print("=" * 70)
        
        loaded_count = 0
        failed_count = 0
        
        for cmd_name, cmd_info in discovered.items():
            cog = self.bot.get_cog(cmd_info.cog.split('.')[-1])
            
            if cog:
                cmd_info.status = CommandStatus.LOADED
                loaded_count += 1
                print(f"  [OK] /{cmd_name} - Loaded in {cmd_info.cog}")
            else:
                cmd_info.status = CommandStatus.BROKEN
                cmd_info.load_error = f"Cog {cmd_info.cog} not loaded"
                failed_count += 1
                print(f"  [FAIL] /{cmd_name} - Cog {cmd_info.cog} not loaded")
        
        print(f"\nLoaded: {loaded_count} | Failed: {failed_count}")
    
    def _check_registered_commands(self, discovered: Dict[str, CommandInfo]):
        """Check which commands are registered in the command tree."""
        print("\n" + "=" * 70)
        print("STEP 3: CHECKING REGISTERED COMMANDS")
        print("=" * 70)
        
        registered_count = 0
        
        for cmd_name, cmd_info in discovered.items():
            # Check if command exists in the tree
            # This is a simplified check - in production you'd walk the tree
            try:
                # Get the command from the tree
                if hasattr(self.bot.tree, 'get_command'):
                    tree_cmd = self.bot.tree.get_command(cmd_name)
                    if tree_cmd:
                        cmd_info.status = CommandStatus.REGISTERED
                        registered_count += 1
                        print(f"  [OK] /{cmd_name} - Registered in tree")
                    else:
                        print(f"  [WARN] /{cmd_name} - Not in tree (sync issue?)")
            except Exception as e:
                print(f"  [WARN] /{cmd_name} - Error checking registration: {e}")
        
        print(f"\nRegistered: {registered_count}")
    
    async def _check_synced_commands(self):
        """Check which commands are synced to Discord."""
        print("\n" + "=" * 70)
        print("STEP 4: CHECKING SYNCED COMMANDS")
        print("=" * 70)
        
        try:
            # Get synced commands from Discord
            synced_commands = await self.bot.tree.fetch_global_commands()
            print(f"  [OK] Fetched {len(synced_commands)} global commands from Discord")
            
            for cmd in synced_commands:
                print(f"  [OK] /{cmd['name']} - Synced to Discord")
        
        except Exception as e:
            print(f"  [ERROR] Failed to fetch synced commands: {e}")
    
    async def _validate_command_execution(self, discovered: Dict[str, CommandInfo]):
        """Validate each command can execute (basic checks)."""
        print("\n" + "=" * 70)
        print("STEP 5: VALIDATING COMMAND EXECUTION")
        print("=" * 70)
        
        for cmd_name, cmd_info in discovered.items():
            # Check if command has a callback
            try:
                cog = self.bot.get_cog(cmd_info.cog.split('.')[-1])
                if cog:
                    # Try to get the command method
                    if hasattr(cog, cmd_name):
                        cmd_info.status = CommandStatus.FUNCTIONAL
                        print(f"  [OK] /{cmd_name} - Has callback")
                    else:
                        print(f"  [WARN] /{cmd_name} - No callback found in cog")
                        cmd_info.execution_error = "No callback"
            except Exception as e:
                print(f"  [ERROR] /{cmd_name} - Error validating: {e}")
                cmd_info.execution_error = str(e)


class HelpAuditor:
    """Audit the help system for accuracy."""
    
    def __init__(self, help_file: str):
        self.help_file = help_file
        self.help_commands: Set[str] = set()
        self.actual_commands: Dict[str, CommandInfo] = {}
    
    def parse_help_commands(self) -> Set[str]:
        """Parse the help file to extract all mentioned commands."""
        print("\n" + "=" * 70)
        print("HELP AUDIT - PARSING HELP FILE")
        print("=" * 70)
        
        try:
            with open(self.help_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find all command references (pattern: /command or `command`)
            # Match patterns like `/command`, ``/command``, or just command names
            patterns = [
                r'/([a-zA-Z0-9_-]+)',  # /command
                r'`([a-zA-Z0-9_-]+)`',  # `command`
            ]
            
            commands = set()
            for pattern in patterns:
                matches = re.findall(pattern, content)
                commands.update(matches)
            
            # Filter out non-command words
            command_words = {'setup', 'config', 'antinuke', 'whitelist', 'botwhitelist', 
                           'safeadmin', 'rolewhitelist', 'setchannellog', 'setguildlog',
                           'setmsglog', 'setvclog', 'setmodlog', 'antinukeconfig', 'ban',
                           'unban', 'kick', 'timeout', 'untimeout', 'warn', 'warnings',
                           'clearwarns', 'purge', 'purgeuser', 'lock', 'unlock', 'slowmode',
                           'nick', 'roleadd', 'roleremove', 'hardban', 'unhardban', 'ticket',
                           'panel', 'ticket-setup', 'ticket-categories', 'case', 'cases',
                           'modmail', 'userinfo', 'serverinfo', 'avatar', 'banner', 'roleinfo',
                           'channelinfo', 'ping', 'uptime', 'afk', 'botinfo', 'invite', 'spam',
                           'clearsnipe', 'editsnipe', 'serverstats', 'updatepresence', 'instagram',
                           'tiktok', 'youtube', 'health', 'announcements', 'captcha', 'verify-captcha',
                           'urlscan', 'premium', 'premium-features', 'premium-set', 'premium-usage',
                           'defense', 'trust', 'help', 'customcmd', 'createrole', 'addtorole',
                           'finalizerole', 'verification', 'create', 'delete', 'list', 'view',
                           'enable', 'disable', 'add', 'remove', 'status'}
            
            # Filter to only likely commands
            self.help_commands = {cmd for cmd in commands if cmd in command_words or len(cmd) > 2}
            
            print(f"  [OK] Found {len(self.help_commands)} commands in help file")
            for cmd in sorted(self.help_commands):
                print(f"    /{cmd}")
            
            return self.help_commands
            
        except Exception as e:
            print(f"  [ERROR] Error parsing help file: {e}")
            return set()
    
    def compare_with_actual(self, actual_commands: Dict[str, CommandInfo]) -> Dict[str, str]:
        """
        Compare help commands with actual commands.
        
        Returns:
            Dictionary mapping issues to descriptions
        """
        print("\n" + "=" * 70)
        print("HELP AUDIT - COMPARING WITH ACTUAL COMMANDS")
        print("=" * 70)
        
        issues = {}
        
        # Commands in help but not in code
        missing_in_code = self.help_commands - set(actual_commands.keys())
        for cmd in missing_in_code:
            issues[f"/{cmd}"] = "Exists in help but not in code (DEAD LINK)"
            print(f"  [FAIL] /{cmd} - In help but not in code")
        
        # Commands in code but not in help
        missing_in_help = set(actual_commands.keys()) - self.help_commands
        for cmd in missing_in_help:
            issues[f"/{cmd}"] = "Exists in code but not in help (MISSING FROM HELP)"
            print(f"  [WARN] /{cmd} - In code but not in help")
        
        print(f"\nDead commands in help: {len(missing_in_code)}")
        print(f"Missing from help: {len(missing_in_help)}")
        
        return issues


def main():
    """Main entry point for command discovery and validation."""
    # Get the directory where this script is located (should be D:\repentv3)
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    # Step 1: Discover all commands
    discovery = CommandDiscovery(project_root)
    commands = discovery.scan_codebase()
    
    # Step 2: Generate report
    report = discovery.generate_report()
    print(report)
    
    # Step 3: Audit help system
    help_file = os.path.join(project_root, "cogs", "help.py")
    auditor = HelpAuditor(help_file)
    help_commands = auditor.parse_help_commands()
    
    # Step 4: Compare
    issues = auditor.compare_with_actual(commands)
    
    # Step 5: Save detailed report
    report_path = os.path.join(project_root, "COMMAND_AUDIT_REPORT.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
        f.write("\n\n" + "=" * 70)
        f.write("HELP AUDIT RESULTS")
        f.write("\n" + "=" * 70 + "\n")
        for cmd, issue in issues.items():
            f.write(f"{cmd}: {issue}\n")
    
    print(f"\n[OK] Detailed report saved to: {report_path}")


if __name__ == "__main__":
    main()
