"""
Repent - Advanced Webhook Threat Detection System

Comprehensive webhook security with profiling, content analysis, 
rate limiting, and threat intelligence.
"""

import asyncio
import re
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass

import discord
from discord import SyncWebhook

from database import get_guild, log_action
from utils.logger import get_logger


@dataclass
class WebhookProfile:
    """Profile for a webhook to track its behavior and trust level."""
    webhook_id: int
    guild_id: int
    creator_id: int
    created_at: datetime
    trust_level: int = 0  # -10 to 10
    message_count: int = 0
    last_message_time: Optional[datetime] = None
    violation_count: int = 0
    suspicious_patterns: List[str] = None
    
    def __post_init__(self):
        if self.suspicious_patterns is None:
            self.suspicious_patterns = []


class WebhookThreatDetector:
    """Advanced webhook threat detection and profiling."""
    
    # Suspicious URL patterns
    SUSPICIOUS_URL_PATTERNS = [
        r'discord-login\.com', r'discord-gift\.com', r'discord-nitro\.com',
        r'free-discord-nitro\.com', r'discord-steal\.com', r'discord-token\.com',
        r'discord-verify\.com', r'discord-confirm\.com', r'discord-support\.com',
        r'steamcommunity\.com', r'steam-gift\.com', r'free-steam\.com',
        r'bit\.ly.*discord', r'tinyurl.*discord', r'goo\.gl.*discord'
    ]
    
    # Token leakage patterns
    TOKEN_PATTERNS = [
        r'[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}',  # Discord bot token
        r'mfa\.[A-Za-z0-9_-]{20,}',  # MFA token
        r'sk_live_[a-zA-Z0-9]{20,}',  # Stripe live key
        r'sk_test_[a-zA-Z0-9]{20,}',  # Stripe test key
    ]
    
    # Suspicious message patterns
    SUSPICIOUS_CONTENT_PATTERNS = [
        r'free.*nitro', r'claim.*nitro', r'gift.*nitro',
        r'verify.*account', r'confirm.*account', r'secure.*account',
        r'login.*required', r'auth.*required', r'verify.*discord',
        r'steam.*gift', r'free.*steam', r'claim.*steam'
    ]
    
    def __init__(self):
        self.webhook_profiles: Dict[int, WebhookProfile] = {}  # webhook_id -> profile
        self.guild_webhooks: Dict[int, Set[int]] = {}  # guild_id -> set of webhook_ids
        self.creator_webhooks: Dict[int, Set[int]] = {}  # creator_id -> set of webhook_ids
        
        # Rate limiting per webhook
        self.webhook_rate_limits: Dict[int, Dict] = {}  # webhook_id -> {tokens, last_update}
        self.rate_limit_window = 60  # seconds
        self.rate_limit_burst = 10  # messages per window
        self.rate_limit_sustained = 30  # messages per minute sustained
        
        # Threat intelligence
        self.known_malicious_urls: Set[str] = set()
        self.webhook_reputation: Dict[int, int] = {}  # webhook_id -> reputation score (-10 to 10)
        
        # Message content analysis
        self.webhook_message_history: Dict[int, deque] = {}  # webhook_id -> deque of recent messages
        self.history_window = 100  # messages to keep
        
        self.logger = get_logger()
        
        # Initialize with known malicious domains
        self._initialize_known_threats()
    
    def _initialize_known_threats(self):
        """Initialize known malicious URLs and domains."""
        known_threats = [
            'discord-login.com', 'discord-gift.com', 'discord-nitro.com',
            'free-discord-nitro.com', 'discord-steal.com', 'discord-token.com',
            'discord-verify.com', 'discord-confirm.com', 'discord-support.com',
            'steamcommunity.com', 'steam-gift.com', 'free-steam.com',
        ]
        self.known_malicious_urls.update(known_threats)
    
    def create_profile(self, webhook_id: int, guild_id: int, creator_id: int) -> WebhookProfile:
        """Create a new webhook profile."""
        profile = WebhookProfile(
            webhook_id=webhook_id,
            guild_id=guild_id,
            creator_id=creator_id,
            created_at=datetime.now(timezone.utc)
        )
        self.webhook_profiles[webhook_id] = profile
        
        # Update guild and creator mappings
        if guild_id not in self.guild_webhooks:
            self.guild_webhooks[guild_id] = set()
        self.guild_webhooks[guild_id].add(webhook_id)
        
        if creator_id not in self.creator_webhooks:
            self.creator_webhooks[creator_id] = set()
        self.creator_webhooks[creator_id].add(webhook_id)
        
        return profile
    
    def get_profile(self, webhook_id: int) -> Optional[WebhookProfile]:
        """Get webhook profile if it exists."""
        return self.webhook_profiles.get(webhook_id)
    
    def track_webhook_message(self, webhook_id: int, content: str, author_id: int):
        """Track a message sent via webhook for analysis."""
        # Update profile
        profile = self.get_profile(webhook_id)
        if profile:
            profile.message_count += 1
            profile.last_message_time = datetime.now(timezone.utc)
        
        # Add to message history
        if webhook_id not in self.webhook_message_history:
            self.webhook_message_history[webhook_id] = deque(maxlen=self.history_window)
        
        self.webhook_message_history[webhook_id].append({
            'content': content,
            'timestamp': datetime.now(timezone.utc),
            'author_id': author_id
        })
        
        # Update rate limit tracking
        self._update_rate_limit(webhook_id)
    
    def _update_rate_limit(self, webhook_id: int):
        """Update rate limit tracking for a webhook."""
        now = datetime.now(timezone.utc)
        
        if webhook_id not in self.webhook_rate_limits:
            self.webhook_rate_limits[webhook_id] = {
                'tokens': self.rate_limit_burst,
                'last_update': now,
                'message_count': 1,
                'window_start': now
            }
            return
        
        rate_data = self.webhook_rate_limits[webhook_id]
        time_since_last = (now - rate_data['last_update']).total_seconds()
        
        # Replenish tokens
        rate_data['tokens'] = min(
            self.rate_limit_burst,
            rate_data['tokens'] + time_since_last * (self.rate_limit_burst / self.rate_limit_window)
        )
        
        # Update timing
        rate_data['last_update'] = now
        rate_data['message_count'] += 1
        
        # Reset window if needed
        if (now - rate_data['window_start']).total_seconds() >= self.rate_limit_window:
            rate_data['window_start'] = now
            rate_data['message_count'] = 1
    
    def check_rate_limit(self, webhook_id: int) -> Tuple[bool, str]:
        """Check if webhook has exceeded rate limits."""
        if webhook_id not in self.webhook_rate_limits:
            return True, "No rate limit data"
        
        rate_data = self.webhook_rate_limits[webhook_id]
        
        # Check burst limit
        if rate_data['tokens'] < 1:
            return False, f"Burst rate limit exceeded ({self.rate_limit_burst} messages per {self.rate_limit_window}s)"
        
        # Check sustained rate
        now = datetime.now(timezone.utc)
        window_seconds = (now - rate_data['window_start']).total_seconds()
        if window_seconds >= self.rate_limit_window:
            messages_per_minute = rate_data['message_count'] / (window_seconds / 60)
            if messages_per_minute > self.rate_limit_sustained:
                return False, f"Sustained rate limit exceeded ({messages_per_minute:.1f} messages/min)"
        
        return True, "Within rate limits"
    
    def analyze_content_threat(self, content: str) -> Dict[str, any]:
        """Analyze webhook message content for threats."""
        threats = []
        threat_score = 0.0
        
        # Check for suspicious URLs
        for pattern in self.SUSPICIOUS_URL_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                threats.append(f"suspicious_url:{pattern}")
                threat_score += 0.3
        
        # Check for token leakage
        for pattern in self.TOKEN_PATTERNS:
            if re.search(pattern, content):
                threats.append(f"token_leak:{pattern[:20]}")
                threat_score += 0.9  # Critical threat
        
        # Check for suspicious content patterns
        for pattern in self.SUSPICIOUS_CONTENT_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                threats.append(f"suspicious_content:{pattern}")
                threat_score += 0.2
        
        # Check for suspicious domains in URLs
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, content, re.IGNORECASE)
        for url in urls:
            for suspicious_url in self.known_malicious_urls:
                if suspicious_url in url:
                    threats.append(f"known_malicious:{suspicious_url}")
                    threat_score += 0.5
        
        return {
            "is_threat": threat_score >= 0.5,
            "threat_score": min(threat_score, 1.0),
            "threats_detected": threats,
            "threat_level": "CRITICAL" if threat_score >= 0.8 else "HIGH" if threat_score >= 0.5 else "MEDIUM" if threat_score >= 0.3 else "LOW"
        }
    
    def analyze_webhook_behavior(self, webhook_id: int) -> Dict[str, any]:
        """Analyze webhook behavior patterns for threats."""
        profile = self.get_profile(webhook_id)
        if not profile:
            return {"is_suspicious": False, "reason": "No profile data"}
        
        suspicious_indicators = []
        suspicion_score = 0.0
        
        # Check message frequency
        if profile.message_count > 100:
            suspicion_score += 0.2
            suspicious_indicators.append(f"high_message_count:{profile.message_count}")
        
        # Check creator's webhook history
        if profile.creator_id in self.creator_webhooks:
            webhook_count = len(self.creator_webhooks[profile.creator_id])
            if webhook_count > 5:
                suspicion_score += 0.3
                suspicious_indicators.append(f"prolific_creator:{webhook_count}")
        
        # Check trust level
        if profile.trust_level < -5:
            suspicion_score += 0.4
            suspicious_indicators.append(f"low_trust:{profile.trust_level}")
        
        # Check violation history
        if profile.violation_count > 3:
            suspicion_score += 0.3
            suspicious_indicators.append(f"violation_history:{profile.violation_count}")
        
        # Check message content patterns
        if webhook_id in self.webhook_message_history:
            messages = self.webhook_message_history[webhook_id]
            if len(messages) > 10:
                # Check for message similarity
                contents = [m['content'] for m in list(messages)[-10:]]
                similar_count = 0
                for i in range(len(contents)):
                    for j in range(i + 1, len(contents)):
                        similarity = self._calculate_similarity(contents[i], contents[j])
                        if similarity > 0.85:
                            similar_count += 1
                
                if similar_count > 5:
                    suspicion_score += 0.3
                    suspicious_indicators.append(f"repetitive_content:{similar_count}")
        
        return {
            "is_suspicious": suspicion_score >= 0.5,
            "suspicion_score": min(suspicion_score, 1.0),
            "indicators": suspicious_indicators,
            "risk_level": "CRITICAL" if suspicion_score >= 0.8 else "HIGH" if suspicion_score >= 0.5 else "MEDIUM" if suspicion_score >= 0.3 else "LOW"
        }
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts."""
        # Simple similarity based on common words
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def update_trust_level(self, webhook_id: int, delta: int):
        """Update webhook trust level."""
        profile = self.get_profile(webhook_id)
        if profile:
            profile.trust_level = max(-10, min(10, profile.trust_level + delta))
    
    def record_violation(self, webhook_id: int, violation_type: str):
        """Record a security violation for a webhook."""
        profile = self.get_profile(webhook_id)
        if profile:
            profile.violation_count += 1
            if violation_type not in profile.suspicious_patterns:
                profile.suspicious_patterns.append(violation_type)
            
            # Reduce trust on violations
            self.update_trust_level(webhook_id, -2)
    
    def add_malicious_url(self, url: str):
        """Add a URL to the known malicious URLs list."""
        self.known_malicious_urls.add(url)
    
    def scan_webhook_url(self, webhook_url: str) -> Dict[str, any]:
        """Scan webhook URL for malicious domains and patterns."""
        threats_found = []
        threat_score = 0.0
        
        # Check for known malicious domains
        for malicious_domain in self.known_malicious_urls:
            if malicious_domain in webhook_url.lower():
                threats_found.append(f"malicious_domain:{malicious_domain}")
                threat_score += 0.8  # High threat
        
        # Check for suspicious URL patterns
        for pattern in self.SUSPICIOUS_URL_PATTERNS:
            if re.search(pattern, webhook_url, re.IGNORECASE):
                threats_found.append(f"suspicious_pattern:{pattern}")
                threat_score += 0.3
        
        # Check for URL shorteners (potential phishing)
        shortener_patterns = [r'bit\.ly', r'tinyurl', r'goo\.gl', r'ow\.ly']
        for pattern in shortener_patterns:
            if re.search(pattern, webhook_url, re.IGNORECASE):
                threats_found.append(f"url_shortener:{pattern}")
                threat_score += 0.2
        
        return {
            "is_malicious": threat_score >= 0.5,
            "threat_score": min(threat_score, 1.0),
            "threats_detected": threats_found,
            "threat_level": "CRITICAL" if threat_score >= 0.8 else "HIGH" if threat_score >= 0.5 else "MEDIUM" if threat_score >= 0.3 else "LOW"
        }
    
    def cleanup_old_profiles(self, days: int = 7):
        """Remove profiles older than specified days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        to_remove = []
        for webhook_id, profile in self.webhook_profiles.items():
            if profile.last_message_time and profile.last_message_time < cutoff:
                to_remove.append(webhook_id)
        
        for webhook_id in to_remove:
            self._remove_profile(webhook_id)
        
        return len(to_remove)
    
    def _remove_profile(self, webhook_id: int):
        """Remove a webhook profile and clean up references."""
        profile = self.webhook_profiles.pop(webhook_id, None)
        if not profile:
            return
        
        # Remove from guild mapping
        if profile.guild_id in self.guild_webhooks:
            self.guild_webhooks[profile.guild_id].discard(webhook_id)
            if not self.guild_webhooks[profile.guild_id]:
                del self.guild_webhooks[profile.guild_id]
        
        # Remove from creator mapping
        if profile.creator_id in self.creator_webhooks:
            self.creator_webhooks[profile.creator_id].discard(webhook_id)
            if not self.creator_webhooks[profile.creator_id]:
                del self.creator_webhooks[profile.creator_id]
        
        # Clean up rate limits and history
        self.webhook_rate_limits.pop(webhook_id, None)
        self.webhook_message_history.pop(webhook_id, None)
        self.webhook_reputation.pop(webhook_id, None)