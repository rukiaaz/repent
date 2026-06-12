"""
Debug script to check OAuth configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

print("=== OAuth Configuration Debug ===")
print(f"SECRET_KEY: {'✓ Set' if os.getenv('SECRET_KEY') else '✗ Missing'}")
print(f"DISCORD_CLIENT_ID: {os.getenv('DISCORD_CLIENT_ID')}")
print(f"DISCORD_CLIENT_SECRET: {'✓ Set' if os.getenv('DISCORD_CLIENT_SECRET') else '✗ Missing'}")

# Check if values are placeholders
client_id = os.getenv('DISCORD_CLIENT_ID')
client_secret = os.getenv('DISCORD_CLIENT_SECRET')

if client_id and 'placeholder' in client_id.lower():
    print("⚠️  WARNING: DISCORD_CLIENT_ID is still a placeholder!")
if client_secret and 'placeholder' in client_secret.lower():
    print("⚠️  WARNING: DISCORD_CLIENT_SECRET is still a placeholder!")

print("\n=== Expected Redirect URI ===")
print("For local development: http://localhost:5000/callback")
print("For production: https://repent.world/callback")
print("\nMake sure this exact URI is set in Discord Developer Portal → OAuth2 → Redirects")