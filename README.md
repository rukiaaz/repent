# Balance - Advanced Discord Antinuke & Security Bot

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)]
[![License](https://img.shields.io/badge/license-MIT-green.svg)]
[![Discord](https://img.shields.io/badge/discord.py-2.3+-orange.svg)]

A powerful Discord security bot providing antinuke protection, automated moderation, verification systems, and comprehensive server management.

## 🚀 Features

### Security Systems
- **Multi-Layer Defense** - Progressive threat detection and response
- **Zero-Trust Security** - Trust scores and adaptive verification
- **Behavioral Analysis** - Anomaly detection and pattern recognition
- **Antinuke Protection** - Instant response to nukes and raids
- **Webhook Monitoring** - Detect and remove malicious webhooks
- **Token Protection** - Auto-delete leaked Discord tokens

### Moderation
- Full moderation suite (ban, kick, timeout, warn, purge, hardban)
- Custom warnings with persistent tracking
- Hardban system with auto-reban on rejoin
- Audit logging and case management

### AutoMod
- Spam protection with configurable thresholds
- Invite link filtering
- Caps and mention limits
- Content filtering (banned words, domains, NSFW)
- Mass mention protection

### User Management
- Button-based verification with custom embeds
- Welcome and farewell messages with templates
- Auto-role assignment
- Boost notifications
- AFK system

### Utilities
- User info, server info, role info, channel info
- Avatar and banner display
- Bot statistics and uptime
- Ping and latency checks
- Custom commands

### Advanced Features
- **Ticket System** - Support tickets with transcripts
- **Captcha Verification** - Math captcha for suspicious joins
- **Anti-Raid** - Join raid detection and quarantine
- **Backup & Restore** - Server snapshots and recovery

### Dashboard
- Modern web-based dashboard with white/gray theme
- Real-time server management
- Execute moderation commands from web
- Configure antinuke and automod
- View audit logs and statistics

## 📦 Installation

### Option 1: Manual Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/balance.git
cd balance
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your Discord token and other settings
```

4. Run the bot:
```bash
python main.py
```

### Option 2: Docker Deployment

1. Build and run with Docker:
```bash
docker-compose up -d
```

### Option 3: With Dashboard

1. Install website dependencies:
```bash
cd website
pip install -r requirements.txt
```

2. Configure OAuth:
```bash
# Set up Discord application at https://discord.com/developers/applications
# Add REDIRECT URI: http://127.0.0.1:5000/callback
# Copy client ID and secret to .env
```

3. Run the dashboard:
```bash
python app.py
```

4. Access at `http://127.0.0.1:5000`

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_bot_token_here
OWNER_ID=your_user_id
SECRET_KEY=your_secret_key_here
API_SECRET=balance-api-secret-key
JWT_SECRET=balance-jwt-secret-key

# Website OAuth (optional)
DISCORD_CLIENT_ID=your_discord_client_id
DISCORD_CLIENT_SECRET=your_discord_client_secret
```

### Bot Configuration

Use slash commands to configure the bot:
- `/setup` - Interactive setup wizard
- `/antinuke` - Configure antinuke settings
- `/automod` - Configure automod rules
- `/verification` - Set up verification system
- `/welcome` - Configure welcome messages
- `/farewell` - Configure farewell messages
- `/ticket` - Configure ticket system

## 📖 Commands

### Security
- `/defense status` - View defense layer status
- `/defense escalate` - Escalate defense level
- `/defense lockdown` - Emergency lockdown

### Verification
- `/verification set <channel>` - Set verification channel
- `/verification role <role>` - Set verification role
- `/verification send` - Send verification message
- `/verification status` - View verification status

### Welcome/Farewell
- `/welcome set <channel>` - Set welcome channel
- `/welcome message <text>` - Set welcome message
- `/welcome autorole <role>` - Set auto-role
- `/farewell set <channel>` - Set farewell channel
- `/farewell message <text>` - Set farewell message

### Moderation
- `/ban <user> [reason]` - Ban a user
- `/kick <user> [reason]` - Kick a user
- `/timeout <user> <duration> [reason]` - Timeout a user
- `/warn <user> [reason]` - Warn a user
- `/purge <amount>` - Purge messages
- `/hardban <user> [reason]` - Hardban a user

### Utilities
- `/userinfo [user]` - Get user information
- `/serverinfo` - Get server information
- `/ping` - Check bot latency
- `/avatar [user]` - Get user avatar
- `/botinfo` - Get bot information

## 🤖 Contributing

Contributions are welcome! Please feel free to:
- Report bugs
- Suggest new features
- Submit pull requests
- Improve documentation

## 📄 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- discord.py for the amazing Python Discord API wrapper
- All contributors and testers

## 📞 Support

- Join our Discord: [Link]
- Create an issue on GitHub
- Check the documentation