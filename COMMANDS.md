# Balance Bot Commands Reference

## 🔒 Security Commands

### Multi-Layer Defense
```
/defense status - View defense layer status
/defense escalate - Escalate defense to next level
/defense lockdown - Emergency lockdown mode
/defense-layer <layer> <enable> - Toggle specific defense layer (1-5)
```

### Zero Trust Security
```
/trust [user] - View user's trust score or low-trust users
/trust-reset <user> - Reset user's trust score
```

### Behavioral Analysis
```
/behavior <user> - Analyze user behavior patterns
/behavior-baseline - Establish behavioral baseline for server
```

---

## 🔐 Verification System

```
/verification set <channel> - Set verification channel
/verification role <role> - Set verification role
/verification message <text> - Set embed description
/verification embed title <text> - Set embed title
/verification embed color <hex> - Set embed color
/verification embed button <text> - Set button text
/verification send - Send verification message
/verification disable - Disable verification
/verification status - View verification status
```

---

## 👋 Welcome & Farewell

### Welcome Messages
```
/welcome set <channel> - Set welcome channel
/welcome message <text> - Set welcome message template
/welcome autorole <role> - Set auto-role for new members
```

### Farewell Messages
```
/farewell set <channel> - Set farewell channel
/farewell message <text> - Set farewell message template
```

### Boost Notifications
```
/boost set <channel> - Set boost notification channel
/boost message <text> - Set boost message template
```

**Template Variables:** `{user}`, `{username}`, `{server}`, `{count}`, `{guild}`

---

## 🎫 Ticket System

```
/ticket [category] - Create a support ticket
/ticket-setup <category> [role] [channel] - Configure ticket category
/ticket-categories - List all ticket categories
/panel <channel> - Send ticket panel to channel
```

---

## 🔢 Captcha

```
/captcha enable - Enable captcha verification
/captcha disable - Disable captcha verification
/captcha difficulty - Set captcha difficulty
/captcha status - View captcha status
/verify-captcha <answer> - Submit captcha answer
```

---

## 🛡️ Moderation

### Standard Moderation
```
/ban <user> [reason] [delete_days] - Ban a user
/unban <user_id> [reason] - Unban a user
/kick <user> [reason] - Kick a user
/timeout <user> <duration> [reason] - Timeout a user
/untimeout <user> - Remove timeout from user
/warn <user> [reason] - Warn a user
/warnings <user> - View user's warnings
/clearwarns <user> - Clear user's warnings
/hardban <user> [reason] - Hardban user (auto-reban on rejoin)
/unhardban <user_id> - Remove from hardban list
```

### Message Management
```
/purge <amount> - Delete recent messages (1-100)
/purgeuser <user> [amount] - Delete messages from specific user
```

### Channel Control
```
/lock [channel] - Lock a channel
/unlock [channel] - Unlock a channel
/slowmode <seconds> [channel] - Set slowmode for channel
```

### Role Management
```
/roleadd <user> <role> - Add role to user
/roleremove <user> <role> - Remove role from user
/nick <user> [nickname] - Change user's nickname
```

---

## 🤖 Utilities

### Information Commands
```
/userinfo [user] - View detailed user information
/serverinfo - View server information
/roleinfo <role> - View role information
/channelinfo [channel] - View channel information
/avatar [user] - Get user avatar
/banner [user] - Get user banner
/botinfo - View bot information
/invite - Get bot invite link
```

### System Commands
```
/ping - Check bot latency
/uptime - View bot uptime
/spam <message> <count> - Spam message (admin only)
/afk [reason] - Set AFK status
```

### Stats
```
/serverstats - View server statistics
```

---

## 🎨 Antinuke Configuration

```
/antinuke enable - Enable antinuke
/antinuke disable - Disable antinuke
/antinuke threshold <action> <value> [window] - Set detection threshold
/antinuke punishment <type> - Set default punishment
```

**Threshold Actions:** `ban`, `kick`, `channel_delete`, `channel_create`, `role_delete`, `role_create`, `role_update`, `webhook_create`, `webhook_delete`, `server_update`, `bot_add`, `emoji_delete`, `sticker_delete`

**Punishment Types:** `ban`, `kick`, `strip`, `timeout`

---

## 🤖 AutoMod Configuration

```
/automod enable - Enable automod
/automod disable - Disable automod
/automod anti_spam <enable> - Toggle spam protection
/automod anti_invite <enable> - Toggle invite filtering
/automod anti_link <enable> - Toggle link filtering
/automod anti_caps <enable> - Toggle caps filter
/automod anti_mention <enable> - Toggle mention filter
/automod anti_emoji <enable> - Toggle emoji spam filter
/automod spam_threshold <number> - Set spam threshold
/automod spam_window <seconds> - Set spam time window
/automod mention_limit <number> - Set mention limit
/automod caps_percent <number> - Set caps percentage threshold
/automod emoji_limit <number> - Set emoji limit
```

---

## 🎛️ Configuration

### Server Settings
```
/setup - Interactive setup wizard
/config <setting> <value> - Set configuration value
```

### Logging
```
/logs mod_channel <channel> - Set moderation log channel
/logs guild_channel <channel> - Set guild log channel
/logs all_message <channel> - Set all messages log channel
/logs voice <channel> - Set voice log channel
/logs thread <channel> - Set thread log channel
```

### Verification Settings
```
/verification channel <channel> - Set verification channel
/verification role <role> - Set verification role
/verification enabled <0/1> - Toggle verification
```

### Welcome Settings
```
/welcome channel <channel> - Set welcome channel
/welcome msg <message> - Set welcome message
/farewell channel <channel> - Set farewell channel
/farewell msg <message> - Set farewell message
/autorole <role> - Set auto-role
```

### Antinuke Settings
```
/antinuke enabled <0/1> - Toggle antinuke
/antinuke punishment <type> - Set default punishment
/antinuke threshold <action> <value> <window> - Set threshold
```

### AutoMod Settings
```
/automod enabled <0/1> - Toggle automod
/automod anti_spam <0/1> - Toggle spam protection
/automod anti_invite <0/1> - Toggle invite filter
/automod anti_link <0/1> - Toggle link filter
/automod anti_caps <0/1> - Toggle caps filter
/automod anti_mention <0/1> - Toggle mention filter
```

---

## 🎭 Leveling

```
/xp multiplier <multiplier> - Set XP multiplier
/xp cooldown <seconds> - Set XP cooldown
/level channel <channel> - Set level-up channel
/level dm <true/false> - Toggle level-up DMs
```

---

## ⚙️ Reaction Roles

```
/reaction add <message> <emoji> <role> - Add reaction role
/reaction remove <message> <emoji> - Remove reaction role
/reaction list - List all reaction roles
```

---

## 📜 Custom Commands

```
/custom add <command> <response> - Add custom command
/custom remove <command> - Remove custom command
/custom list - List all custom commands
```

---

## 💾 Backup & Restore

```
/backup create - Create backup
/backup restore <backup_id> - Restore from backup
/backup list - List all backups
```

---

## 🔍 Help

```
/help - View command categories
/help <command> - View detailed command help
```

---

## Permission Requirements

### Administrator Required
- All `/antinuke` commands
- All `/automod` commands
- All `/config` commands
- All `/ticket` commands (except creating tickets)
- `/defense escalate`, `/defense lockdown`
- `/spam`

### Manage Channels Required
- `/lock`, `/unlock`, `/slowmode`

### Manage Roles Required
- `/roleadd`, `/roleremove`
- Autorole modification

### Manage Messages Required
- `/purge`, `/purgeuser`
- All `/warn` commands

### Ban Members Required
- `/ban`, `/unban`, `/hardban`, `/unhardban`

### Kick Members Required
- `/kick`

### Moderate Members Required
- `/timeout`, `/untimeout`

### Specific Permission Notes
- `/nick` requires Manage Nicknames
- Channel-specific actions often require specific permissions in that channel