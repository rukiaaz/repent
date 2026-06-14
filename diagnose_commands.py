"""
Diagnostic script to check if commands are registered in the tree.
Run this to see what's in the command tree before sync.
"""

import os
import sys
import ast
import re

def scan_for_commands(project_root):
    """Scan the codebase for all @app_commands.command decorators."""
    commands = []
    
    cogs_dir = os.path.join(project_root, "cogs")
    
    for filename in os.listdir(cogs_dir):
        if not filename.endswith(".py") or filename == "__init__.py":
            continue
        
        filepath = os.path.join(cogs_dir, filename)
        cog_name = f"cogs.{filename[:-3]}"
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
            
            # Find all @app_commands.command decorators
            for line_num, line in enumerate(lines, 1):
                if '@app_commands.command' in line:
                    # Find the function def
                    func_def = None
                    for i in range(line_num, min(line_num + 5, len(lines))):
                        if lines[i].strip().startswith('async def '):
                            func_def = lines[i]
                            break
                    
                    if func_def:
                        # Extract command name
                        name_match = re.search(r'name="([^"]+)"', line)
                        desc_match = re.search(r'description="([^"]+)"', line)
                        
                        command_name = name_match.group(1) if name_match else None
                        if not command_name:
                            func_name_match = re.search(r'async def (\w+)', func_def)
                            if func_name_match:
                                command_name = func_name_match.group(1)
                        
                        if command_name:
                            commands.append({
                                'name': command_name,
                                'cog': cog_name,
                                'file': filename,
                                'line': line_num
                        })
        
        except Exception as e:
            print(f"Error scanning {filename}: {e}")
    
    return commands

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    print("=" * 70)
    print("COMMAND DIAGNOSTIC SCAN")
    print("=" * 70)
    
    commands = scan_for_commands(project_root)
    
    print(f"\nFound {len(commands)} commands in code:\n")
    
    # Group by cog
    by_cog = {}
    for cmd in commands:
        if cmd['cog'] not in by_cog:
            by_cog[cmd['cog']] = []
        by_cog[cmd['cog']].append(cmd)
    
    for cog in sorted(by_cog.keys()):
        print(f"{cog}: {len(by_cog[cog])} commands")
        for cmd in by_cog[cog]:
            print(f"  /{cmd['name']} - line {cmd['line']}")
    
    print("\n" + "=" * 70)
    print(f"TOTAL: {len(commands)} commands")
    print("=" * 70)
    
    # Check for common issues
    print("\n" + "=" * 70)
    print("COMMON ISSUES CHECK")
    print("=" * 70)
    
    # Check for cogs with 0 commands
    all_cogs = []
    for filename in os.listdir(os.path.join(project_root, "cogs")):
        if filename.endswith(".py") and filename != "__init__.py":
            all_cogs.append(f"cogs.{filename[:-3]}")
    
    cogs_with_commands = set(cmd['cog'] for cmd in commands)
    cogs_without_commands = set(all_cogs) - cogs_with_commands
    
    if cogs_without_commands:
        print(f"\n[WARN] Cogs with no commands:")
        for cog in sorted(cogs_without_commands):
            print(f"  {cog}")
    
    # Check for duplicate command names
    cmd_names = [cmd['name'] for cmd in commands]
    duplicates = [name for name in cmd_names if cmd_names.count(name) > 1]
    
    if duplicates:
        print(f"\n[WARN] Duplicate command names:")
        for name in set(duplicates):
            print(f"  /{name}")
    
    print("\n" + "=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
