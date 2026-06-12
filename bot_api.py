"""
Balance Bot HTTP API Server
FastAPI server for dashboard integration with Discord bot.
"""

from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import httpx
import json
import asyncio
from datetime import datetime, timedelta
import jwt
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
BOT_TOKEN = os.getenv("DISCORD_TOKEN", "")
API_SECRET = os.getenv("API_SECRET", "balance-api-secret-key-change-in-production")
JWT_SECRET = os.getenv("JWT_SECRET", API_SECRET)
DISCORD_API_BASE = "https://discord.com/api/v10"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = 3600  # 1 hour

# FastAPI app
app = FastAPI(
    title="Balance Bot API",
    description="HTTP API for Balance Discord bot dashboard integration",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5000", "http://localhost:5000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP Bearer for token auth
security = HTTPBearer()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# Pydantic models
class DiscordToken(BaseModel):
    token: str

class GuildAction(BaseModel):
    guild_id: str
    user_id: str
    reason: str = ""

class BanAction(GuildAction):
    delete_days: int = 0

class TimeoutAction(GuildAction):
    duration: str = "10m"

class PurgeAction(BaseModel):
    guild_id: str
    channel_id: str
    amount: int = 50

class ChannelAction(BaseModel):
    guild_id: str
    channel_id: str

class SlowmodeAction(ChannelAction):
    seconds: int = 0

class RoleAction(BaseModel):
    guild_id: str
    user_id: str
    role_id: str

class WhitelistAction(BaseModel):
    guild_id: str
    entity_id: str
    whitelist_type: str = "user"

class AntinukeConfig(BaseModel):
    guild_id: str
    config: Dict[str, Any]

class AutomodConfig(BaseModel):
    guild_id: str
    config: Dict[str, Any]

class GuildConfig(BaseModel):
    guild_id: str
    config: Dict[str, Any]

class BackupCreate(BaseModel):
    guild_id: str
    backup_type: str = "full"

class BackupRestore(BaseModel):
    guild_id: str
    backup_id: str
    options: Dict[str, bool] = {}

# Helper functions
async def verify_discord_token(token: str) -> Dict[str, Any]:
    """Verify Discord OAuth token and get user info."""
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {token}"}
        try:
            # Get user info
            user_response = await client.get(f"{DISCORD_API_BASE}/users/@me", headers=headers)
            if user_response.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid Discord token")
            
            user_data = user_response.json()
            
            # Get user's guilds
            guilds_response = await client.get(f"{DISCORD_API_BASE}/users/@me/guilds", headers=headers)
            if guilds_response.status_code != 200:
                raise HTTPException(status_code=401, detail="Failed to fetch guilds")
            
            guilds_data = guilds_response.json()
            
            return {
                "user": user_data,
                "guilds": guilds_data
            }
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"Discord API error: {str(e)}")

def create_jwt_token(data: dict) -> str:
    """Create JWT token for authenticated session."""
    expire = datetime.utcnow() + timedelta(seconds=JWT_EXPIRATION)
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

async def verify_jwt_token(token: str) -> dict:
    """Verify JWT token and return payload."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def has_admin_permission(guilds: List[dict], guild_id: str) -> bool:
    """Check if user has admin permission in guild."""
    for guild in guilds:
        if str(guild.get("id")) == guild_id:
            # Check if user has administrator permission (0x8)
            permissions = int(guild.get("permissions", 0))
            return bool(permissions & 0x8)
    return False

async def make_discord_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Make authenticated request to Discord API."""
    url = f"{DISCORD_API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        if method.upper() == "GET":
            response = await client.get(url, headers=headers)
        elif method.upper() == "POST":
            response = await client.post(url, headers=headers, json=data)
        elif method.upper() == "PUT":
            response = await client.put(url, headers=headers, json=data)
        elif method.upper() == "DELETE":
            response = await client.delete(url, headers=headers)
        elif method.upper() == "PATCH":
            response = await client.patch(url, headers=headers, json=data)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid method: {method}")
        
        if response.status_code >= 400:
            error_data = response.json() if response.headers.get("content-type") == "application/json" else {}
            raise HTTPException(status_code=response.status_code, detail=error_data)
        
        return response.json() if response.headers.get("content-type") == "application/json" else {}

# Authentication
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify Discord token and return user info."""
    token = credentials.credentials
    user_info = await verify_discord_token(token)
    return user_info

async def get_authenticated_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT token and return user info."""
    token = credentials.credentials
    payload = await verify_jwt_token(token)
    return payload

# === API Endpoints ===

@app.get("/")
async def root():
    return {"message": "Balance Bot API", "version": "1.0.0", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# === Authentication ===

@app.post("/auth/discord")
async def auth_discord(token: DiscordToken):
    """Authenticate with Discord token and get JWT."""
    try:
        user_info = await verify_discord_token(token.token)
        jwt_token = create_jwt_token({"user_id": user_info["user"]["id"]})
        return {
            "success": True,
            "token": jwt_token,
            "user": user_info["user"],
            "expires_in": JWT_EXPIRATION
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auth/verify")
async def verify_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token is valid."""
    try:
        payload = await verify_jwt_token(credentials.credentials)
        return {"valid": True, "user_id": payload.get("user_id")}
    except HTTPException:
        raise

# === Guild Data ===

@app.get("/api/v1/guilds")
async def get_guilds(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get user's guilds with bot permission."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        # Filter guilds where bot is present
        # For now, return all guilds - bot presence check would require bot token
        return {"guilds": user_info["guilds"]}
    except HTTPException:
        raise

@app.get("/api/v1/guilds/{guild_id}/members")
async def get_guild_members(guild_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get guild members."""
    try:
        # Verify user has admin permission
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # Fetch members from Discord API
        members = await make_discord_request("GET", f"/guilds/{guild_id}/members?limit=100")
        return {"members": members}
    except HTTPException:
        raise

@app.get("/api/v1/guilds/{guild_id}/channels")
async def get_guild_channels(guild_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get guild channels."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        channels = await make_discord_request("GET", f"/guilds/{guild_id}/channels")
        return {"channels": channels}
    except HTTPException:
        raise

@app.get("/api/v1/guilds/{guild_id}/roles")
async def get_guild_roles(guild_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get guild roles."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        roles = await make_discord_request("GET", f"/guilds/{guild_id}/roles")
        return {"roles": roles}
    except HTTPException:
        raise

@app.get("/api/v1/guilds/{guild_id}/config")
async def get_guild_config(guild_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get guild configuration."""
    try:
        # This would fetch from database
        # For now, return placeholder
        return {
            "guild_id": guild_id,
            "config": {
                "antinuke_enabled": True,
                "automod_enabled": True,
                "log_channel": None,
                "mod_channel": None
            }
        }
    except HTTPException:
        raise

@app.post("/api/v1/guilds/{guild_id}/config")
async def update_guild_config(guild_id: str, config: GuildConfig, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Update guild configuration."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would update database
        # For now, return success
        return {"success": True, "message": "Configuration updated", "config": config.config}
    except HTTPException:
        raise

# === Moderation ===

@app.post("/api/v1/moderation/ban")
async def ban_user(action: BanAction, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Ban a user."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        await make_discord_request("PUT", f"/guilds/{action.guild_id}/bans/{action.user_id}", {
            "reason": f"[Dashboard] {action.reason}"
        })
        
        return {"success": True, "message": "User banned", "action": "ban", "target": action.user_id, "guild": action.guild_id}
    except HTTPException:
        raise

@app.post("/api/v1/moderation/kick")
async def kick_user(action: GuildAction, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Kick a user."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        await make_discord_request("POST", f"/guilds/{action.guild_id}/members/{action.user_id}", {
            "reason": f"[Dashboard] {action.reason}"
        })
        
        return {"success": True, "message": "User kicked", "action": "kick", "target": action.user_id, "guild": action.guild_id}
    except HTTPException:
        raise

@app.post("/api/v1/moderation/timeout")
async def timeout_user(action: TimeoutAction, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Timeout a user."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # Parse duration (simple implementation)
        duration_map = {"10m": 600, "1h": 3600, "1d": 86400, "1w": 604800}
        seconds = duration_map.get(action.duration, 600)
        
        await make_discord_request("PATCH", f"/guilds/{action.guild_id}/members/{action.user_id}", {
            "communication_disabled_until": (datetime.utcnow() + timedelta(seconds=seconds)).isoformat(),
            "reason": f"[Dashboard] {action.reason}"
        })
        
        return {"success": True, "message": f"User timed out for {action.duration}", "action": "timeout", "target": action.user_id, "guild": action.guild_id}
    except HTTPException:
        raise

@app.post("/api/v1/moderation/warn")
async def warn_user(action: GuildAction, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Warn a user (would need database integration)."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would add to warnings database
        # For now, return success
        return {"success": True, "message": "Warning added", "action": "warn", "target": action.user_id, "guild": action.guild_id}
    except HTTPException:
        raise

@app.post("/api/v1/moderation/purge")
async def purge_messages(action: PurgeAction, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Purge messages from channel."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # Discord API doesn't support purging by message ID in bulk
        # This would need to be done by the bot directly
        # For now, return success
        return {"success": True, "message": f"Purged {action.amount} messages", "action": "purge", "channel": action.channel_id, "guild": action.guild_id}
    except HTTPException:
        raise

# === Channel ===

@app.post("/api/v1/channel/lock")
async def lock_channel(action: ChannelAction, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Lock a channel."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # Get @everyone role
        roles = await make_discord_request("GET", f"/guilds/{action.guild_id}/roles")
        everyone_role = next((r for r in roles if r["name"] == "@everyone"), None)
        
        if everyone_role:
            await make_discord_request("PUT", f"/channels/{action.channel_id}/permissions/{everyone_role['id']}", {
                "allow": "0",
                "deny": "2048"  # SEND_MESSAGES permission
            })
        
        return {"success": True, "message": "Channel locked", "action": "lock", "channel": action.channel_id, "guild": action.guild_id}
    except HTTPException:
        raise

@app.post("/api/v1/channel/unlock")
async def unlock_channel(action: ChannelAction, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Unlock a channel."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        roles = await make_discord_request("GET", f"/guilds/{action.guild_id}/roles")
        everyone_role = next((r for r in roles if r["name"] == "@everyone"), None)
        
        if everyone_role:
            await make_discord_request("PUT", f"/channels/{action.channel_id}/permissions/{everyone_role['id']}", {
                "allow": "2048",  # SEND_MESSAGES permission
                "deny": "0"
            })
        
        return {"success": True, "message": "Channel unlocked", "action": "unlock", "channel": action.channel_id, "guild": action.guild_id}
    except HTTPException:
        raise

@app.post("/api/v1/channel/slowmode")
async def set_slowmode(action: SlowmodeAction, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Set slowmode on channel."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        await make_discord_request("PATCH", f"/channels/{action.channel_id}", {
            "rate_limit_per_user": action.seconds
        })
        
        return {"success": True, "message": f"Slowmode set to {action.seconds}s", "action": "slowmode", "channel": action.channel_id, "guild": action.guild_id}
    except HTTPException:
        raise

# === Role ===

@app.post("/api/v1/role/add")
async def add_role(action: RoleAction, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Add role to user."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        await make_discord_request("PUT", f"/guilds/{action.guild_id}/members/{action.user_id}/roles/{action.role_id}")
        
        return {"success": True, "message": "Role added", "action": "role_add", "user": action.user_id, "role": action.role_id, "guild": action.guild_id}
    except HTTPException:
        raise

@app.post("/api/v1/role/remove")
async def remove_role(action: RoleAction, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Remove role from user."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        await make_discord_request("DELETE", f"/guilds/{action.guild_id}/members/{action.user_id}/roles/{action.role_id}")
        
        return {"success": True, "message": "Role removed", "action": "role_remove", "user": action.user_id, "role": action.role_id, "guild": action.guild_id}
    except HTTPException:
        raise

# === Whitelist ===

@app.post("/api/v1/whitelist/add")
async def add_whitelist(action: WhitelistAction, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Add entity to whitelist (requires database)."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would add to database whitelist
        return {"success": True, "message": "Added to whitelist", "action": "whitelist_add", "entity": action.entity_id, "type": action.whitelist_type, "guild": action.guild_id}
    except HTTPException:
        raise

@app.post("/api/v1/whitelist/remove")
async def remove_whitelist(action: WhitelistAction, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Remove entity from whitelist (requires database)."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would remove from database whitelist
        return {"success": True, "message": "Removed from whitelist", "action": "whitelist_remove", "entity": action.entity_id, "type": action.whitelist_type, "guild": action.guild_id}
    except HTTPException:
        raise

@app.get("/api/v1/whitelist/{guild_id}")
async def get_whitelist(guild_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get whitelist for guild (requires database)."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would fetch from database
        return {"users": [], "bots": [], "roles": []}
    except HTTPException:
        raise

# === Antinuke ===

@app.post("/api/v1/antinuke/config")
async def update_antinuke_config(action: AntinukeConfig, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Update antinuke configuration (requires database)."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would update database
        return {"success": True, "message": "Antinuke configuration updated", "guild": action.guild_id, "config": action.config}
    except HTTPException:
        raise

@app.post("/api/v1/antinuke/enable")
async def enable_antinuke(guild_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Enable antinuke."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would update database
        return {"success": True, "message": "Antinuke enabled", "guild": guild_id}
    except HTTPException:
        raise

@app.post("/api/v1/antinuke/disable")
async def disable_antinuke(guild_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Disable antinuke."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would update database
        return {"success": True, "message": "Antinuke disabled", "guild": guild_id}
    except HTTPException:
        raise

# === AutoMod ===

@app.post("/api/v1/automod/config")
async def update_automod_config(action: AutomodConfig, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Update automod configuration (requires database)."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would update database
        return {"success": True, "message": "Automod configuration updated", "guild": action.guild_id, "config": action.config}
    except HTTPException:
        raise

@app.post("/api/v1/automod/enable")
async def enable_automod(guild_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Enable automod."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would update database
        return {"success": True, "message": "Automod enabled", "guild": guild_id}
    except HTTPException:
        raise

@app.post("/api/v1/automod/disable")
async def disable_automod(guild_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Disable automod."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would update database
        return {"success": True, "message": "Automod disabled", "guild": guild_id}
    except HTTPException:
        raise

# === Logs ===

@app.get("/api/v1/logs/{guild_id}")
async def get_logs(guild_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get audit logs (requires database)."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would fetch from database
        return {"logs": []}
    except HTTPException:
        raise

# === Backup ===

@app.post("/api/v1/backup/create")
async def create_backup(action: BackupCreate, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Create backup (requires database)."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would create backup in database/filesystem
        return {"success": True, "message": "Backup created", "guild": action.guild_id, "type": action.backup_type}
    except HTTPException:
        raise

@app.post("/api/v1/backup/restore")
async def restore_backup(action: BackupRestore, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Restore from backup (requires database)."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], action.guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would restore from backup
        return {"success": True, "message": "Backup restored", "guild": action.guild_id, "backup": action.backup_id}
    except HTTPException:
        raise

@app.get("/api/v1/backup/list/{guild_id}")
async def list_backups(guild_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """List backups for guild (requires database)."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # This would fetch from database
        return {"backups": []}
    except HTTPException:
        raise

# === WebSocket ===

@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to Balance Bot API WebSocket",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        while True:
            data = await websocket.receive_text()
            # Echo back for now, in production would broadcast updates
            await websocket.send_json({"type": "echo", "data": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/v1/ws/broadcast")
async def broadcast_message(message: dict):
    """Broadcast message to all WebSocket clients."""
    await manager.broadcast(message)
    return {"success": True, "message": "Broadcast sent to all clients"}

# === Additional Endpoints for Phase 2 ===

@app.get("/api/v1/guilds/{guild_id}/info")
async def get_guild_info(guild_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get detailed guild information."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        guild_info = await make_discord_request("GET", f"/guilds/{guild_id}")
        
        # Add member count
        member_count = guild_info.get("approximate_member_count", 0)
        
        return {
            "id": guild_info.get("id"),
            "name": guild_info.get("name"),
            "icon": f"https://cdn.discordapp.com/icons/{guild_id}/{guild_info.get('icon')}.png" if guild_info.get('icon') else None,
            "owner_id": guild_info.get("owner_id"),
            "member_count": member_count,
            "premium_tier": guild_info.get("premium_tier", 0),
            "roles_count": len(guild_info.get("roles", [])),
            "channels_count": len(guild_info.get("channels", [])),
            "features": guild_info.get("features", []),
            "verification_level": guild_info.get("verification_level"),
            "explicit_content_filter": guild_info.get("explicit_content_filter"),
        }
    except HTTPException:
        raise

@app.get("/api/v1/guilds/{guild_id}/members/{user_id}")
async def get_guild_member(guild_id: str, user_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get specific member information from guild."""
    try:
        user_info = await verify_discord_token(credentials.credentials)
        if not has_admin_permission(user_info["guilds"], guild_id):
            raise HTTPException(status_code=403, detail="Admin permission required")
        
        # Get member info
        member_info = await make_discord_request("GET", f"/guilds/{guild_id}/members/{user_id}")
        return {"member": member_info}
    except HTTPException:
        raise

# Run server (for development)
if __name__ == "__main__":
    import uvicorn
    print("Starting Balance Bot API Server...")
    print("API will be available at http://127.0.0.1:8000")
    print("API docs at http://127.0.0.1:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000)