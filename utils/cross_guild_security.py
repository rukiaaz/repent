"""
Repent - Cross-Guild Attack Correlation System

Tracks security events across all guilds to identify coordinated attacks
and share threat intelligence between servers.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field
import json

from database import log_action
from utils.logger import get_logger


@dataclass
class SecurityEvent:
    """Represents a security event that can be correlated across guilds."""
    event_id: str
    event_type: str  # raid, bot_add, webhook_threat, spam_wave, etc.
    guild_id: int
    attacker_id: int
    timestamp: datetime
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    details: dict = field(default_factory=dict)
    resolved: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "guild_id": self.guild_id,
            "attacker_id": self.attacker_id,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity,
            "details": self.details,
            "resolved": self.resolved
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SecurityEvent':
        """Create from dictionary."""
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            guild_id=data["guild_id"],
            attacker_id=data["attacker_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            severity=data["severity"],
            details=data.get("details", {}),
            resolved=data.get("resolved", False)
        )


@dataclass
class AttackerProfile:
    """Profile for an attacker across multiple guilds."""
    attacker_id: int
    first_seen: datetime
    last_seen: datetime
    attack_count: int = 0
    guilds_targeted: Set[int] = field(default_factory=set)
    attack_types: Dict[str, int] = field(default_factory=dict)  # attack_type -> count
    severity_scores: List[int] = field(default_factory=list)
    threat_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    is_blacklisted: bool = False
    
    def calculate_threat_level(self) -> str:
        """Calculate threat level based on attack patterns."""
        if self.attack_count >= 10 or len(self.guilds_targeted) >= 5:
            return "CRITICAL"
        elif self.attack_count >= 5 or len(self.guilds_targeted) >= 3:
            return "HIGH"
        elif self.attack_count >= 2 or len(self.guilds_targeted) >= 2:
            return "MEDIUM"
        return "LOW"


class CrossGuildSecurityCorrelation:
    """Cross-guild attack correlation and threat intelligence system."""
    
    def __init__(self):
        # Event tracking
        self.security_events: Dict[str, SecurityEvent] = {}  # event_id -> event
        self.events_by_guild: Dict[int, Set[str]] = defaultdict(set)  # guild_id -> event_ids
        self.events_by_attacker: Dict[int, Set[str]] = defaultdict(set)  # attacker_id -> event_ids
        
        # Attacker profiling
        self.attacker_profiles: Dict[int, AttackerProfile] = {}  # attacker_id -> profile
        self.global_blacklist: Set[int] = set()  # attacker_ids blacklisted globally
        
        # Attack pattern detection
        self.attack_patterns: Dict[str, List[SecurityEvent]] = defaultdict(list)  # pattern_name -> events
        self.correlation_window: timedelta = timedelta(minutes=30)  # Time window for correlation
        
        # Threat intelligence sharing
        self.guild_intelligence: Dict[int, Dict] = defaultdict(dict)  # guild_id -> intelligence data
        self.shared_blacklists: Dict[int, Set[int]] = defaultdict(set)  # guild_id -> shared blacklists
        
        self.logger = get_logger()
        
        # Coordinated attack detection
        self.active_coordinated_attacks: Dict[str, Dict] = {}  # attack_id -> attack data
        self.coordinated_attack_threshold = 3  # Minimum guilds to trigger coordinated attack alert
    
    def record_security_event(self, event_type: str, guild_id: int, attacker_id: int, 
                           severity: str, details: dict = None) -> SecurityEvent:
        """Record a security event for correlation analysis."""
        event_id = f"{guild_id}_{event_type}_{attacker_id}_{datetime.now(timezone.utc).timestamp()}"
        
        event = SecurityEvent(
            event_id=event_id,
            event_type=event_type,
            guild_id=guild_id,
            attacker_id=attacker_id,
            timestamp=datetime.now(timezone.utc),
            severity=severity,
            details=details or {}
        )
        
        # Store event
        self.security_events[event_id] = event
        self.events_by_guild[guild_id].add(event_id)
        self.events_by_attacker[attacker_id].add(event_id)
        
        # Update attacker profile
        self._update_attacker_profile(attacker_id, event)
        
        # Check for coordinated attacks
        self._check_coordinated_attacks(event)
        
        # Log to database
        asyncio.create_task(log_action(guild_id, "cross_guild_event", attacker_id, {
            "event_type": event_type,
            "severity": severity,
            "event_id": event_id,
            "cross_guild_analysis": self._get_attacker_cross_guild_data(attacker_id)
        }))
        
        return event
    
    def _update_attacker_profile(self, attacker_id: int, event: SecurityEvent):
        """Update attacker profile with new event data."""
        if attacker_id not in self.attacker_profiles:
            self.attacker_profiles[attacker_id] = AttackerProfile(
                attacker_id=attacker_id,
                first_seen=event.timestamp,
                last_seen=event.timestamp
            )
        
        profile = self.attacker_profiles[attacker_id]
        profile.last_seen = event.timestamp
        profile.attack_count += 1
        profile.guilds_targeted.add(event.guild_id)
        
        # Update attack type counts
        profile.attack_types[event.event_type] = profile.attack_types.get(event.event_type, 0) + 1
        
        # Add severity score
        severity_score = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}.get(event.severity, 1)
        profile.severity_scores.append(severity_score)
        
        # Recalculate threat level
        profile.threat_level = profile.calculate_threat_level()
        
        # Auto-blacklist if threat level is critical
        if profile.threat_level == "CRITICAL":
            self.global_blacklist.add(attacker_id)
            profile.is_blacklisted = True
    
    def _check_coordinated_attacks(self, new_event: SecurityEvent):
        """Check if this event is part of a coordinated attack."""
        # Get recent events from other guilds
        cutoff = datetime.now(timezone.utc) - self.correlation_window
        
        coordinated_events = []
        for event_id, event in self.security_events.items():
            if (event.event_type == new_event.event_type and 
                event.guild_id != new_event.guild_id and
                event.timestamp > cutoff and
                event.timestamp <= new_event.timestamp):
                coordinated_events.append(event)
        
        # Check if we have enough events to indicate coordinated attack
        unique_guilds = set(event.guild_id for event in coordinated_events) | {new_event.guild_id}
        
        if len(unique_guilds) >= self.coordinated_attack_threshold:
            # This appears to be a coordinated attack
            attack_id = f"coordinated_{new_event.event_type}_{new_event.timestamp.strftime('%Y%m%d_%H%M%S')}"
            
            self.active_coordinated_attacks[attack_id] = {
                "attack_type": new_event.event_type,
                "start_time": min(event.timestamp for event in coordinated_events + [new_event]),
                "affected_guilds": unique_guilds,
                "event_count": len(coordinated_events) + 1,
                "attackers": set(event.attacker_id for event in coordinated_events + [new_event]),
                "severity": new_event.severity,
                "status": "ACTIVE"
            }
            
            self.logger.security("COORDINATED_ATTACK_DETECTED",
                f"Coordinated {new_event.event_type} attack detected across {len(unique_guilds)} guilds",
                extra={
                    "attack_id": attack_id,
                    "attack_type": new_event.event_type,
                    "affected_guilds": list(unique_guilds),
                    "event_count": len(coordinated_events) + 1
                })
    
    def get_attacker_profile(self, attacker_id: int) -> Optional[AttackerProfile]:
        """Get the profile for a specific attacker."""
        return self.attacker_profiles.get(attacker_id)
    
    def is_globally_blacklisted(self, attacker_id: int) -> bool:
        """Check if attacker is on the global blacklist."""
        return attacker_id in self.global_blacklist
    
    def get_cross_guild_attacks(self, attacker_id: int) -> List[SecurityEvent]:
        """Get all attacks by an attacker across different guilds."""
        event_ids = self.events_by_attacker.get(attacker_id, set())
        return [self.security_events[eid] for eid in event_ids if eid in self.security_events]
    
    def get_guild_attack_history(self, guild_id: int, hours: int = 24) -> List[SecurityEvent]:
        """Get attack history for a specific guild."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        event_ids = self.events_by_guild.get(guild_id, set())
        
        return [
            self.security_events[eid] 
            for eid in event_ids 
            if eid in self.security_events and self.security_events[eid].timestamp > cutoff
        ]
    
    def get_active_coordinated_attacks(self) -> Dict[str, Dict]:
        """Get all currently active coordinated attacks."""
        # Clean up old attacks (older than 1 hour)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        
        active_attacks = {}
        for attack_id, attack_data in self.active_coordinated_attacks.items():
            if attack_data["start_time"] > cutoff:
                active_attacks[attack_id] = attack_data
            else:
                # Mark as resolved
                attack_data["status"] = "RESOLVED"
        
        return active_attacks
    
    def add_to_guild_blacklist(self, guild_id: int, attacker_id: int):
        """Add attacker to a guild-specific blacklist."""
        self.shared_blacklists[guild_id].add(attacker_id)
    
    def remove_from_guild_blacklist(self, guild_id: int, attacker_id: int):
        """Remove attacker from a guild-specific blacklist."""
        self.shared_blacklists[guild_id].discard(attacker_id)
    
    def get_guild_blacklist(self, guild_id: int) -> Set[int]:
        """Get the combined blacklist for a guild (global + guild-specific)."""
        return self.global_blacklist | self.shared_blacklists[guild_id]
    
    def share_threat_intelligence(self, source_guild: int, target_guilds: List[int]) -> Dict:
        """Share threat intelligence from one guild to others."""
        if source_guild not in self.events_by_guild:
            return {"success": False, "reason": "No events for source guild"}
        
        intelligence = {
            "source_guild": source_guild,
            "recent_attacks": [],
            "high_risk_attackers": [],
            "active_threats": []
        }
        
        # Get recent attacks from source guild
        recent_events = self.get_guild_attack_history(source_guild, hours=24)
        intelligence["recent_attacks"] = [event.to_dict() for event in recent_events]
        
        # Get high-risk attackers
        for event in recent_events:
            if event.severity in ["HIGH", "CRITICAL"]:
                profile = self.get_attacker_profile(event.attacker_id)
                if profile:
                    intelligence["high_risk_attackers"].append({
                        "attacker_id": event.attacker_id,
                        "threat_level": profile.threat_level,
                        "guilds_targeted": len(profile.guilds_targeted),
                        "attack_count": profile.attack_count
                    })
        
        # Get active threats
        intelligence["active_threats"] = list(self.get_active_coordinated_attacks().values())
        
        # Store intelligence for target guilds
        for target_guild in target_guilds:
            self.guild_intelligence[target_guild][source_guild] = intelligence
        
        return {"success": True, "intelligence": intelligence}
    
    def get_threat_intelligence(self, guild_id: int) -> Dict:
        """Get all threat intelligence available to a guild."""
        guild_intel = self.guild_intelligence.get(guild_id, {})
        
        # Get guild-specific blacklist
        guild_blacklist = self.get_guild_blacklist(guild_id)
        
        # Get recent coordinated attacks
        coordinated_attacks = list(self.get_active_coordinated_attacks().values())
        
        return {
            "guild_blacklist": list(guild_blacklist),
            "coordinated_attacks": coordinated_attacks,
            "shared_intelligence": guild_intel,
            "global_blacklist": list(self.global_blacklist)
        }
    
    def _get_attacker_cross_guild_data(self, attacker_id: int) -> Dict:
        """Get cross-guild data for an attacker."""
        profile = self.get_attacker_profile(attacker_id)
        if not profile:
            return {}
        
        attacks = self.get_cross_guild_attacks(attacker_id)
        
        return {
            "threat_level": profile.threat_level,
            "guilds_targeted": len(profile.guilds_targeted),
            "attack_count": profile.attack_count,
            "attack_types": profile.attack_types,
            "is_blacklisted": profile.is_blacklisted,
            "recent_attacks": [event.to_dict() for event in attacks[-10:]]
        }
    
    def cleanup_old_events(self, days: int = 7):
        """Remove events older than specified days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        to_remove = []
        for event_id, event in self.security_events.items():
            if event.timestamp < cutoff:
                to_remove.append(event_id)
        
        for event_id in to_remove:
            self._remove_event(event_id)
        
        return len(to_remove)
    
    def _remove_event(self, event_id: str):
        """Remove an event and clean up references."""
        event = self.security_events.pop(event_id, None)
        if not event:
            return
        
        # Remove from guild mapping
        if event.guild_id in self.events_by_guild:
            self.events_by_guild[event.guild_id].discard(event_id)
            if not self.events_by_guild[event.guild_id]:
                del self.events_by_guild[event.guild_id]
        
        # Remove from attacker mapping
        if event.attacker_id in self.events_by_attacker:
            self.events_by_attacker[event.attacker_id].discard(event_id)
            if not self.events_by_attacker[event.attacker_id]:
                del self.events_by_attacker[event.attacker_id]
    
    def get_statistics(self) -> Dict:
        """Get system statistics."""
        return {
            "total_events": len(self.security_events),
            "total_guilds": len(self.events_by_guild),
            "total_attackers": len(self.attacker_profiles),
            "global_blacklist_size": len(self.global_blacklist),
            "active_coordinated_attacks": len(self.get_active_coordinated_attacks()),
            "threat_distribution": self._get_threat_distribution()
        }
    
    def _get_threat_distribution(self) -> Dict[str, int]:
        """Get distribution of threat levels."""
        distribution = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        
        for profile in self.attacker_profiles.values():
            distribution[profile.threat_level] = distribution.get(profile.threat_level, 0) + 1
        
        return distribution