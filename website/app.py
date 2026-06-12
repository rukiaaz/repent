from flask import Flask, render_template, redirect, url_for, session, request, jsonify
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import os
import secrets
import requests

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

# Bot API URL
BOT_API_URL = os.environ.get('BOT_API_URL', 'http://127.0.0.1:8000')

def proxy_to_bot_api(endpoint: str, method: str = 'GET', data: dict = None):
    """Proxy request to bot API server."""
    url = f"{BOT_API_URL}{endpoint}"
    headers = {'Authorization': f"Bearer {session.get('token')}"}
    
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data)
        elif method == 'PUT':
            response = requests.put(url, headers=headers, json=data)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers)
        else:
            return jsonify({'error': 'Invalid method'}), 400
        
        return response.json(), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Failed to connect to bot API: {str(e)}'}), 503

# Discord OAuth Configuration
oauth = OAuth(app)
discord = oauth.register(
    name='discord',
    client_id=os.environ.get('DISCORD_CLIENT_ID'),
    client_secret=os.environ.get('DISCORD_CLIENT_SECRET'),
    access_token_url='https://discord.com/api/oauth2/token',
    access_token_params=None,
    authorize_url='https://discord.com/api/oauth2/authorize',
    authorize_params=None,
    api_base_url='https://discord.com/api/',
    client_kwargs={'scope': 'identify guilds'},
    fetch_token=lambda: {'access_token': session.get('token'), 'token_type': session.get('token_type', 'Bearer')}
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Fetch guilds on demand and filter by administrator permissions
    all_guilds = []
    admin_guilds = []
    try:
        guilds_resp = discord.get('users/@me/guilds')
        if guilds_resp.status_code == 200:
            all_guilds = guilds_resp.json()
            print(f"Fetched {len(all_guilds)} total guilds")
            
            # Filter guilds where user has administrator permission (0x8)
            ADMIN_PERMISSION = 0x8
            for guild in all_guilds:
                permissions = int(guild.get('permissions', 0))
                if permissions & ADMIN_PERMISSION:
                    admin_guilds.append(guild)
            
            print(f"Filtered to {len(admin_guilds)} guilds with admin permissions")
    except Exception as e:
        print(f"Failed to fetch guilds: {e}")
    
    return render_template('dashboard_modern.html', user=session['user'], guilds=admin_guilds, total_guilds=len(all_guilds))

@app.route('/login')
def login():
    redirect_uri = url_for('callback', _external=True)
    print(f"Login redirect URI: {redirect_uri}")
    print(f"Client ID: {os.environ.get('DISCORD_CLIENT_ID')}")
    # Add state parameter to track popup login
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    session['popup_login'] = True  # Mark this as a popup login
    return discord.authorize_redirect(redirect_uri, state=state)

@app.route('/callback')
def callback():
    try:
        print("=" * 50)
        print("CALLBACK ROUTE HIT!")
        print("=" * 50)
        print(f"Full request URL: {request.url}")
        print(f"Request args: {dict(request.args)}")
        print(f"Request method: {request.method}")
        
        # Check if we have the authorization code
        if 'code' not in request.args:
            print("ERROR: No authorization code in request")
            return redirect(url_for('index') + '?error=no_code')
        
        print(f"Authorization code received: {request.args.get('code')[:20]}...")
        
        # Get the token from Discord
        print("Attempting to get token from Discord...")
        token = discord.authorize_access_token()
        print(f"Token received: {token is not None}")
        
        if not token:
            print("ERROR: No token received from Discord")
            return redirect(url_for('index') + '?error=no_token')
        
        print(f"Token data: {token}")
        
        # Save ONLY essential token data in session
        session['token'] = token.get('access_token')
        session['token_type'] = token.get('token_type', 'Bearer')
        print("Essential token data saved to session")
        
        # Get user info
        print("Attempting to get user info...")
        resp = discord.get('users/@me')
        print(f"User info response status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"ERROR: Failed to get user info: {resp.text}")
            return redirect(url_for('index') + '?error=user_info_failed')
        
        user = resp.json()
        print(f"User info retrieved: {user.get('username', 'unknown')}")
        session['user'] = user
        print("User saved to session")
        
        # DON'T store guilds in session to avoid size issues
        # We'll fetch them on demand instead
        print("Skipping guild storage to avoid session size issues")
        
        print("Login successful!")
        
        # Check if this is a popup login (from session flag)
        is_popup_login = session.pop('popup_login', False)
        print(f"Popup login: {is_popup_login}")
        
        if is_popup_login:
            # Return HTML to close the popup and notify parent window
            return '''
            <html>
            <head><title>Login Successful</title></head>
            <body>
            <script>
                window.opener.postMessage({login_success: true}, '*');
                window.close();
            </script>
            <p>Login successful! You can close this window.</p>
            </body>
            </html>
            '''
        else:
            print("Redirecting to dashboard...")
            return redirect(url_for('dashboard'))
        
    except Exception as e:
        print("=" * 50)
        print(f"EXCEPTION IN CALLBACK: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("=" * 50)
        import traceback
        traceback.print_exc()
        return redirect(url_for('index') + f'?error={type(e).__name__}')

@app.route('/test-callback')
def test_callback():
    """Test route to see if callback URL is reachable"""
    return "Callback route is working! This means the routing is fine."

@app.route('/api/check-auth')
def check_auth():
    """Check if user is logged in (for popup OAuth flow)"""
    return jsonify({'logged_in': 'user' in session})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/api/guild/<guild_id>/members')
def get_guild_members(guild_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api(f'/api/v1/guilds/{guild_id}/members')
    return jsonify(data), status

@app.route('/api/guild/<guild_id>/channels')
def get_guild_channels(guild_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api(f'/api/v1/guilds/{guild_id}/channels')
    return jsonify(data), status

@app.route('/api/guild/<guild_id>/roles')
def get_guild_roles(guild_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api(f'/api/v1/guilds/{guild_id}/roles')
    return jsonify(data), status

@app.route('/api/moderation/ban', methods=['POST'])
def ban_member():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/moderation/ban', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/moderation/kick', methods=['POST'])
def kick_member():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/moderation/kick', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/moderation/timeout', methods=['POST'])
def timeout_member():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/moderation/timeout', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/moderation/warn', methods=['POST'])
def warn_member():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/moderation/warn', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/moderation/purge', methods=['POST'])
def purge_messages():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/moderation/purge', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/channel/lock', methods=['POST'])
def lock_channel():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/channel/lock', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/channel/unlock', methods=['POST'])
def unlock_channel():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/channel/unlock', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/channel/slowmode', methods=['POST'])
def set_slowmode():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/channel/slowmode', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/role/add', methods=['POST'])
def add_role():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/role/add', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/role/remove', methods=['POST'])
def remove_role():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/role/remove', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/whitelist/add', methods=['POST'])
def add_whitelist():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/whitelist/add', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/whitelist/remove', methods=['POST'])
def remove_whitelist():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/whitelist/remove', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/whitelist/list/<guild_id>')
def list_whitelist(guild_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api(f'/api/v1/whitelist/{guild_id}')
    return jsonify(data), status

@app.route('/api/antinuke/config', methods=['POST'])
def update_antinuke_config():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/antinuke/config', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/logs/<guild_id>')
def get_logs(guild_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api(f'/api/v1/logs/{guild_id}')
    return jsonify(data), status

@app.route('/api/backup/create', methods=['POST'])
def create_backup():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/backup/create', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/backup/restore', methods=['POST'])
def restore_backup():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/backup/restore', 'POST', request.json)
    return jsonify(data), status

@app.route('/api/config/update', methods=['POST'])
def update_config():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data, status = proxy_to_bot_api('/api/v1/config/update', 'POST', request.json)
    return jsonify(data), status

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)