# Balance Dashboard Setup Guide

## Overview
This guide will help you set up the Balance moderation dashboard with Discord OAuth2 login integration. The dashboard matches the existing website theme and provides full moderation capabilities.

## Prerequisites
- Python 3.8 or higher
- Discord Bot Application
- Web server or hosting solution

## Step 1: Discord OAuth2 Application Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application or select your existing Balance bot application
3. Navigate to "OAuth2" > "General"
4. Add the following redirect URL:
   - For local development: `http://localhost:5000/callback`
   - For production: `https://repent.world/callback`
5. Under "OAuth2 Scopes", ensure these are checked:
   - `identify` - Get user information
   - `guilds` - Get user's servers
6. Copy your Client ID and Client Secret

## Step 2: Environment Configuration

1. Copy the `.env.example` file to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your credentials:
   ```env
   SECRET_KEY=your_random_secret_key_here
   DISCORD_CLIENT_ID=your_discord_client_id
   DISCORD_CLIENT_SECRET=your_discord_client_secret
   ```

3. Generate a secure secret key:
   ```python
   import secrets
   print(secrets.token_hex(32))
   ```

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- Flask==3.0.0
- Authlib==3.2.0
- requests==2.31.0
- python-dotenv==1.0.0

## Step 4: Run the Dashboard

### Development
```bash
python app.py
```

The dashboard will be available at `http://localhost:5000`

### Production (using Gunicorn)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Step 5: Features Overview

### Dashboard Sections

1. **Overview**
   - Server statistics
   - Recent activity feed
   - Quick status updates

2. **Servers**
   - List of all servers where user has admin access
   - Server management quick actions
   - Direct access to moderation tools

3. **Moderation Panel**
   - Quick actions: Ban, Kick, Timeout, Purge
   - User lookup functionality
   - Mass actions: Mass Ban, Mass Kick, Lockdown
   - Server selector for targeting specific servers

4. **Audit Logs**
   - Filterable event log
   - Real-time moderation history
   - Export capabilities

5. **Settings**
   - Protection toggles (Antinuke, Anti-Raid, AutoMod)
   - Notification preferences
   - API configuration

## Step 6: Bot API Integration

The dashboard currently has placeholder API endpoints. To connect it to your Discord bot:

1. **Add bot token to environment:**
   ```env
   BOT_TOKEN=your_discord_bot_token
   ```

2. **Implement the API endpoints in `app.py`:**
   - Update `/api/guild/<guild_id>/members` to fetch real guild data
   - Update moderation endpoints to send actual Discord API calls
   - Add proper permission checking

3. **Example integration:**
   ```python
   @app.route('/api/moderation/ban', methods=['POST'])
   def ban_member():
       if 'user' not in session:
           return jsonify({'error': 'Unauthorized'}), 401
       
       data = request.json
       # Add your Discord bot API call here
       # This would use your bot token to perform the actual ban
       
       return jsonify({'success': True, 'message': 'User banned'})
   ```

## Step 7: Deployment

### Option 1: Traditional Hosting
1. Deploy to any Python-compatible hosting (Heroku, PythonAnywhere, etc.)
2. Set environment variables in your hosting control panel
3. Update Discord OAuth redirect URLs to your production domain

### Option 2: Docker Deployment
Create a `Dockerfile`:
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

Build and run:
```bash
docker build -t balance-dashboard .
docker run -p 5000:5000 --env-file .env balance-dashboard
```

## Security Considerations

1. **Never commit `.env` file** to version control
2. **Use HTTPS in production** for OAuth2 to work properly
3. **Implement rate limiting** on API endpoints
4. **Add proper permission checking** before allowing moderation actions
5. **Consider adding CSRF protection** for forms

## Troubleshooting

### OAuth2 Redirect Error
- Ensure redirect URL matches exactly in Discord Developer Portal
- Check that the URL includes `http://` or `https://` as appropriate
- Verify port number is correct (5000 by default)

### Session Issues
- Clear browser cookies and cache
- Check that SECRET_KEY is set and consistent
- Ensure cookies are enabled in your browser

### Static Files Not Loading
- Verify Flask static folder configuration
- Check file paths in templates
- Ensure CSS/JS files are in the correct location

## Theme Consistency

The dashboard uses the same design system as the main website:
- **Font:** Space Mono (monospace)
- **Colors:** Monochrome palette with subtle accents
- **Animations:** Smooth transitions using CSS cubic-bezier
- **Layout:** Minimalist, functional design

## Next Steps

1. Complete Discord OAuth2 application setup
2. Configure environment variables
3. Test the dashboard locally
4. Implement bot API integration
5. Deploy to production
6. Set up monitoring and logging

## Support

For issues or questions:
- Check the main project README
- Join the Balance Discord support server
- Review Discord OAuth2 documentation

## License

This dashboard is part of the Balance antinuke bot project.