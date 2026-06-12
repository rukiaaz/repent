"""
Repent - Announcement System
Manages bot update announcements and automatic channel creation.
"""

from datetime import datetime, timezone
from typing import List, Dict
import json
import os

# Path to store announcement data
ANNOUNCEMENTS_FILE = "data/announcements.json"


def load_announcements() -> List[Dict[str, str]]:
    """Load announcements from file."""
    if not os.path.exists(ANNOUNCEMENTS_FILE):
        return []
    
    try:
        with open(ANNOUNCEMENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def save_announcements(announcements: List[Dict[str, str]]):
    """Save announcements to file."""
    os.makedirs(os.path.dirname(ANNOUNCEMENTS_FILE), exist_ok=True)
    with open(ANNOUNCEMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, indent=2)


def add_announcement(title: str, description: str, importance: str = "normal") -> Dict[str, str]:
    """
    Add a new announcement.
    
    Args:
        title: Announcement title
        description: Detailed description of changes
        importance: 'low', 'normal', 'high', 'critical'
    
    Returns:
        The created announcement dict
    """
    announcements = load_announcements()
    
    announcement = {
        "id": len(announcements) + 1,
        "title": title,
        "description": description,
        "importance": importance,
        "date": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0"  # Can be updated per release
    }
    
    # Add to beginning of list (newest first)
    announcements.insert(0, announcement)
    
    # Keep only last 20 announcements
    if len(announcements) > 20:
        announcements = announcements[:20]
    
    save_announcements(announcements)
    return announcement


def get_recent_announcements(limit: int = 5) -> List[Dict[str, str]]:
    """Get the most recent announcements."""
    announcements = load_announcements()
    return announcements[:limit]


# Initialize with current session's fixes
def initialize_current_session_announcements():
    """Add announcements for the current development session fixes."""
    existing = load_announcements()
    
    # Check if we already added these announcements
    if any("database initialization" in ann.get("title", "").lower() for ann in existing):
        return  # Already initialized
    
    # Add today's fixes as announcements
    announcements_to_add = [
        {
            "title": "🔧 Database Initialization Fixed",
            "description": "Fixed 'no such table: main.warnings' error by improving table creation logic with individual statements and verification steps.",
            "importance": "high"
        },
        {
            "title": "🛡️ Antinuke Type Error Fixed", 
            "description": "Fixed TypeError in user whitelist role checking by adding set-to-list conversion for better compatibility.",
            "importance": "high"
        },
        {
            "title": "📊 Leveling Cog Syntax Fixed",
            "description": "Fixed f-string syntax error in leveling.py that prevented the cog from loading properly.",
            "importance": "normal"
        },
        {
            "title": "🎨 Discord UI View Rows Fixed",
            "description": "Fixed ValueError in /setup command by reorganizing UI components to fit within Discord's 5-row limit.",
            "importance": "normal"
        },
        {
            "title": "🚀 Auto-Announcement System Added",
            "description": "New automatic announcement system that creates announcement channels and notifies servers about bot updates and changes.",
            "importance": "normal"
        }
    ]
    
    for ann in announcements_to_add:
        add_announcement(ann["title"], ann["description"], ann["importance"])


def add_optimization_announcement():
    """Add announcement for the optimization update."""
    existing = load_announcements()
    
    # Check if we already added this announcement
    if any("security and performance" in ann.get("title", "").lower() for ann in existing):
        return  # Already added
    
    add_announcement(
        "🚀 Major Security & Performance Update",
        "Implemented advanced token protection with Discord token leak detection, added phishing detection system, fixed critical bugs (ThreatLevel comparisons, command conflicts), enhanced database performance with comprehensive indexes, and added missing dependencies. Created comprehensive optimization plan for future enhancements.",
        "high"
    )


def add_antinuke_improvements_announcement():
    """Add announcement for antinuke improvements."""
    existing = load_announcements()
    
    # Check if we already added this announcement
    if any("antinuke improvements" in ann.get("title", "").lower() for ann in existing):
        return  # Already added
    
    add_announcement(
        "🛡️ Antinuke System Overhaul - Zero Tolerance Protection",
        "Completely redesigned antinuke detection with zero-tolerance policies. Instant ban on first channel rename (no rate limiting), automatic channel name restoration from latest snapshot, 5-minute auto-snapshot system with intelligent cleanup, and smart announcement tracking. Fixed channel rename bypass where attackers renamed 15+ channels before being caught. Now restores all channel names immediately using latest snapshot data. Added comprehensive protection against all sophisticated nuke codes including Scylla, FX Selfbot, and JavaScript nukers.",
        "critical"
    )


# Initialize on import
initialize_current_session_announcements()
add_optimization_announcement()
add_antinuke_improvements_announcement()