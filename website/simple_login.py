"""
Simple alternative login for testing without OAuth
This creates a fake user session for dashboard testing
"""
from flask import Flask, render_template, redirect, url_for, session, request, jsonify
from dotenv import load_dotenv
import os
import secrets

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

# Fake user for testing
TEST_USER = {
    'id': '123456789',
    'username': 'TestUser',
    'discriminator': '1234',
    'avatar': None,
    'global_name': 'Test User'
}

TEST_GUILDS = [
    {
        'id': '987654321',
        'name': 'Test Server',
        'icon': None,
        'owner': True,
        'permissions': '8'
    }
]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('simple_login'))
    return render_template('dashboard.html', user=session['user'], guilds=session.get('guilds', []))

@app.route('/login')
def login():
    return redirect(url_for('simple_login'))

@app.route('/simple-login')
def simple_login():
    """Simple login for testing without OAuth"""
    session['user'] = TEST_USER
    session['guilds'] = TEST_GUILDS
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# Keep the API endpoints the same
@app.route('/api/guild/<guild_id>/members')
def get_guild_members(guild_id):
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify({'members': [], 'channels': [], 'roles': []})

@app.route('/api/moderation/ban', methods=['POST'])
def ban_member():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify({'success': True, 'message': 'Ban command sent'})

@app.route('/api/moderation/kick', methods=['POST'])
def kick_member():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify({'success': True, 'message': 'Kick command sent'})

@app.route('/api/moderation/timeout', methods=['POST'])
def timeout_member():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify({'success': True, 'message': 'Timeout command sent'})

if __name__ == '__main__':
    print("=== SIMPLE LOGIN MODE ===")
    print("This uses a fake user for testing without Discord OAuth")
    print("Dashboard: http://localhost:5000/dashboard")
    print("Simple Login: http://localhost:5000/simple-login")
    app.run(debug=True, port=5000)