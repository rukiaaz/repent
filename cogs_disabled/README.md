# Disabled Cogs Archive

This directory contains cogs that have been temporarily disabled and moved from the main `cogs/` directory to:
- Reduce memory footprint
- Free up command slots (stay under 100 global command limit)
- Simplify the codebase

## Archived Cogs

### Initially Disabled (Optimization)
- **antinuke_advanced.py** - Advanced antinuke features (temporarily disabled for testing)
- **antiraid.py** - Old anti-raid system (replaced by enhanced_antiraid.py)
- **security_scanner.py** - Security scanning features (temporarily disabled to save command slots)
- **advanced_logging.py** - Advanced logging features (temporarily disabled to save command slots)
- **verification.py** - Verification system (temporarily disabled to save command slots)
- **welcome.py** - Welcome/farewell system (temporarily disabled to save command slots)

### Disabled for Command Limit
- **help_prefix.py** - Help prefix system (redundant with help.py)
- **premium.py** - Premium features system (temporarily disabled to save command slots)
- **security_dashboard.py** - Security dashboard (temporarily disabled to save command slots)
- **enhanced_moderation.py** - Enhanced moderation (overlaps with moderation.py)
- **enhanced_antiraid.py** - Enhanced anti-raid (overlaps with antinuke.py)
- **utility.py** - Utility commands (userinfo, serverinfo, etc.) - high command count

## Restoration

To restore any of these cogs:
1. Move the file back to the `cogs/` directory
2. Remove any skip logic in `main.py` if present
3. Restart the bot
4. Monitor command count to stay under 100 global limit

## Notes

- These cogs were disabled to stay under Discord's 100 global slash command limit
- They can be re-enabled if Discord increases command slot limits or commands are optimized
- Some cogs may have dependencies or require additional configuration when re-enabled
- Consider consolidating similar functionality to reduce command count