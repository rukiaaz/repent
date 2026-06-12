# Balance Dashboard Website

A modern, professional dashboard for managing the Balance Discord antinuke bot.

## Features

- **OAuth Authentication**: Secure Discord OAuth2 login
- **Server Management**: View and manage all servers with admin permissions
- **Moderation Actions**: Ban, kick, timeout, warn, and purge users
- **Channel Control**: Lock/unlock channels, set slowmode
- **Role Management**: Add and remove roles from users
- **Antinuke Configuration**: Configure protection thresholds and settings
- **Whitelist Management**: Manage users, bots, and roles with immunity
- **Backup & Restore**: Create server snapshots and restore from backups
- **Audit Logs**: View moderation and system activity logs
- **AutoMod Configuration**: Configure automated content filtering
- **Modern UI**: Clean, professional design with responsive layout

## Setup

### Prerequisites

- Python 3.8 or higher
- Discord Application (for OAuth)
- Discord Bot Token

### Installation

1. Install dependencies:
```bash
cd website
pip install -r requirements.txt
```

2. Configure environment variables:
Create a `.env` file in the parent directory with:
```
DISCORD_TOKEN=your_discord_bot_token
OWNER_ID=your_user_id
SECRET_KEY=your_secret_key_here
API_SECRET=balance-api-secret-key-change-in-production
JWT_SECRET=balance-jwt-secret-key-change-in-production
DISCORD_CLIENT_ID=your_discord_application_client_id
DISCORD_CLIENT_SECRET=your_discord_application_client_secret
BOT_API_URL=http://127.0.0.1:8000
```

3. Set up Discord OAuth:
- Go to https://discord.com/developers/applications
- Create or select your application
- Enable OAuth2
- Add redirect URL: `http://127.0.0.1:5000/callback` (adjust for production)
- Enable scopes: `identify`, `guilds`

## Running

### Option 1: Run Both Services (Development)

1. Start the Bot API server:
```bash
cd ..
python bot_api.py
```

2. Start the Flask website:
```bash
cd website
python app.py
```

Access the dashboard at: http://127.0.0.1:5000

### Option 2: Using uvicorn for Bot API (Production)

1. Start the Bot API server:
```bash
cd ..
uvicorn bot_api:app --host 127.0.0.1 --port 8000 --reload
```

2. Start the Flask website:
```bash
cd website
python app.py
```

## Development

### File Structure

```
website/
├── app.py                 # Flask application
├── bot_api.py            # FastAPI bot API (in parent directory)
├── requirements.txt      # Python dependencies
├── .env.example         # Environment variables template
├── templates/
│   ├── index.html      # Landing page
│   ├── dashboard_modern.html  # Main dashboard
│   └── error.html      # Error page
├── modern-theme.css    # Dashboard styling
├── dashboard_modern.js # Dashboard JavaScript
└── README.md           # This file
```

### API Integration

The dashboard communicates with the bot API for:
- Fetching guild members, channels, and roles
- Executing moderation actions
- Managing configurations

All API calls are proxied through Flask to handle authentication.

## Security Notes

- Keep your `.env` file secure and never commit it
- Use strong, unique secrets for SECRET_KEY, API_SECRET, and JWT_SECRET
- Enable HTTPS in production
- Set appropriate CORS origins in production
- Regularly update dependencies

## Troubleshooting

### OAuth Not Working
- Verify DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET are correct
- Check that the redirect URL matches exactly in Discord application settings
- Ensure the OAuth scopes include `identify` and `guilds`

### Bot API Connection Issues
- Verify BOT_API_URL is correct
- Check that the bot API server is running
- Ensure CORS is configured correctly
- Check firewall settings

### Dashboard Not Loading
- Check browser console for errors
- Verify all static files are accessible
- Check Flask logs for errors
- Ensure session cookie is being set

## Production Deployment

For production deployment:

1. Use a production WSGI server (gunicorn, uwsgi)
2. Enable HTTPS with SSL certificates
3. Set secure cookies
4. Configure proper CORS origins
5. Use environment-specific configuration
6. Enable logging and monitoring
7. Set up rate limiting
8. Use a reverse proxy (nginx)

## Support

For issues and questions:
- Check the main project documentation
- Open an issue on GitHub
- Join the support Discord server