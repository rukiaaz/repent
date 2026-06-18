"""
Repent - AutoMod System
Message-based automod: anti-spam, anti-invite, anti-mention, anti-caps, bad words, etc.
Enhanced with ML-based pattern recognition and adaptive filtering.
"""

import re
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import asyncio
from typing import Dict, List, Set, Tuple
import difflib
import unicodedata

from database import (
    get_automod_config, get_bad_words, get_ignored_channels,
    log_action, get_guild, add_strike, clear_strikes, get_strikes,
)
from utils.embeds import alert_embed, success_embed, error_embed, info_embed
from config import OWNER_ID
from utils.logger import get_logger
from utils.webhook_security import WebhookThreatDetector


INVITE_REGEX = re.compile(r"(discord\.gg\/[a-zA-Z0-9\-]+|discord(?:app)?\.com\/invite\/[a-zA-Z0-9\-]+)", re.IGNORECASE)
URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)
MENTION_REGEX = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_REGEX = re.compile(r"<@&(\d+)>")
EMOJI_REGEX = re.compile(r"<a?:\w+:\d+>")


class MLSpamDetector:
    """ML-based spam detection with pattern recognition and adaptive learning."""
    
    def __init__(self):
        # Spam patterns learned from detection
        self.spam_patterns: Dict[str, float] = {}  # pattern -> confidence score
        self.ham_patterns: Dict[str, float] = {}  # legitimate patterns -> confidence
        
        # Evasion techniques
        self.evasion_patterns = {
            'leetspeak': r'[4@]|\[3\]|\/\\/\|/',
            'zero_width': r'[\u200B-\u200D\uFEFF]',
            'homoglyphs': r'[а-я]',  # Cyrillic characters that look like Latin
            'repetition': r'(.)\1{4,}',  # 5+ repeated characters
            'spaces': r'\s{3,}',  # 3+ consecutive spaces
        }
        
        # Multi-language spam indicators
        self.language_indicators = {
            'chinese_spam': r'[\u4e00-\u9fff]{5,}',  # 5+ Chinese characters
            'arabic_spam': r'[\u0600-\u06ff]{5,}',  # 5+ Arabic characters
            'cyrillic_spam': r'[\u0400-\u04ff]{5,}',  # 5+ Cyrillic characters
        }
        
        # Content similarity threshold for duplicate detection
        self.similarity_threshold = 0.85
        
        # Learning parameters
        self.learning_rate = 0.1
        self.false_positive_memory: Dict[str, int] = {}  # content -> false positive count
        self.false_negative_memory: Dict[str, int] = {}  # content -> false negative count
    
    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using sequence matching."""
        # Normalize texts
        text1 = self.normalize_text(text1)
        text2 = self.normalize_text(text2)
        
        if not text1 or not text2:
            return 0.0
        
        # Use difflib for sequence matching
        similarity = difflib.SequenceMatcher(None, text1, text2).ratio()
        return similarity
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison by removing common evasion techniques."""
        # Remove zero-width characters
        text = re.sub(self.evasion_patterns['zero_width'], '', text)
        
        # Normalize unicode characters
        text = unicodedata.normalize('NFKC', text)
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def detect_evasion_techniques(self, text: str) -> Dict[str, bool]:
        """Detect various evasion techniques used in spam."""
        detected = {}
        
        for technique, pattern in self.evasion_patterns.items():
            if re.search(pattern, text):
                detected[technique] = True
        
        return detected
    
    def detect_language_spam(self, text: str) -> List[str]:
        """Detect spam in non-Latin scripts."""
        detected = []
        
        for language, pattern in self.language_indicators.items():
            if re.search(pattern, text):
                detected.append(language)
        
        return detected
    
    def analyze_message_patterns(self, messages: List[str]) -> Dict[str, any]:
        """Analyze patterns across multiple messages for spam detection."""
        if len(messages) < 2:
            return {"is_spam": False, "confidence": 0.0, "reason": "Not enough messages"}
        
        analysis = {
            "avg_length": sum(len(m) for m in messages) / len(messages),
            "length_variance": max(len(m) for m in messages) - min(len(m) for m in messages),
            "similar_messages": 0,
            "evasion_techniques": defaultdict(int),
            "language_spam": defaultdict(int),
        }
        
        # Check for similar messages
        for i in range(len(messages)):
            for j in range(i + 1, len(messages)):
                similarity = self.calculate_text_similarity(messages[i], messages[j])
                if similarity >= self.similarity_threshold:
                    analysis["similar_messages"] += 1
        
        # Analyze evasion techniques
        for message in messages:
            evasion = self.detect_evasion_techniques(message)
            for technique in evasion:
                analysis["evasion_techniques"][technique] += 1
            
            # Check for language spam
            lang_spam = self.detect_language_spam(message)
            for language in lang_spam:
                analysis["language_spam"][language] += 1
        
        # Calculate spam confidence
        spam_confidence = 0.0
        
        # High similarity indicates spam
        if analysis["similar_messages"] >= len(messages) * 0.7:
            spam_confidence += 0.4
        
        # Low variance with high similarity is suspicious
        if analysis["length_variance"] < 20 and analysis["similar_messages"] >= len(messages) * 0.5:
            spam_confidence += 0.3
        
        # Evasion techniques increase suspicion
        evasion_count = sum(analysis["evasion_techniques"].values())
        if evasion_count > 0:
            spam_confidence += min(evasion_count / len(messages) * 0.2, 0.2)
        
        # Non-Latin script spam
        lang_spam_count = sum(analysis["language_spam"].values())
        if lang_spam_count > 0:
            spam_confidence += min(lang_spam_count / len(messages) * 0.1, 0.1)
        
        return {
            "is_spam": spam_confidence >= 0.5,
            "confidence": spam_confidence,
            "reason": self._get_spam_reason(analysis),
            "details": analysis
        }
    
    def _get_spam_reason(self, analysis: dict) -> str:
        """Generate human-readable reason for spam detection."""
        reasons = []
        
        if analysis["similar_messages"] >= 2:
            reasons.append(f"Similar messages detected: {analysis['similar_messages']}")
        
        if analysis["length_variance"] < 20:
            reasons.append("Low message length variance")
        
        if analysis["evasion_techniques"]:
            techniques = ", ".join(analysis["evasion_techniques"].keys())
            reasons.append(f"Evasion techniques: {techniques}")
        
        if analysis["language_spam"]:
            languages = ", ".join(analysis["language_spam"].keys())
            reasons.append(f"Non-Latin spam: {languages}")
        
        return "; ".join(reasons) if reasons else "Pattern-based detection"
    
    def learn_from_feedback(self, content: str, is_false_positive: bool):
        """Learn from false positives/negatives to improve detection."""
        normalized = self.normalize_text(content)
        
        if is_false_positive:
            self.false_positive_memory[normalized] = self.false_positive_memory.get(normalized, 0) + 1
            # Reduce confidence for similar patterns
            for pattern in list(self.spam_patterns.keys()):
                if self.calculate_text_similarity(normalized, pattern) > 0.7:
                    self.spam_patterns[pattern] = max(0, self.spam_patterns[pattern] - self.learning_rate)
        else:
            self.false_negative_memory[normalized] = self.false_negative_memory.get(normalized, 0) + 1
            # Increase confidence for similar patterns
            for pattern in list(self.spam_patterns.keys()):
                if self.calculate_text_similarity(normalized, pattern) > 0.7:
                    self.spam_patterns[pattern] = min(1.0, self.spam_patterns[pattern] + self.learning_rate)


class ViolationTracker:
    """Track violations for enhanced security - faster escalation for repeat offenders."""
    
    def __init__(self):
        # {guild_id: {user_id: [(timestamp, violation_type, severity)]}}
        self._data = defaultdict(lambda: defaultdict(list))
        self._lock = asyncio.Lock()
    
    async def add_violation(self, guild_id: int, user_id: int, violation_type: str, severity: int = 1):
        """Add a violation record. Severity 1-3 (1=minor, 2=moderate, 3=severe)."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            self._data[guild_id][user_id].append((now, violation_type, severity))
            
            # Keep only last 50 violations per user
            if len(self._data[guild_id][user_id]) > 50:
                self._data[guild_id][user_id] = self._data[guild_id][user_id][-50:]
    
    async def get_severity_score(self, guild_id: int, user_id: int, window_minutes: int = 10) -> int:
        """Calculate total severity score for a user within time window."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(minutes=window_minutes)
            violations = [v for v in self._data[guild_id][user_id] if v[0] > cutoff]
            return sum(v[2] for v in violations)
    
    async def cleanup(self):
        """Remove violation records older than 1 hour."""
        async with self._lock:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
            for gid in list(self._data.keys()):
                for uid in list(self._data[gid].keys()):
                    self._data[gid][uid] = [v for v in self._data[gid][uid] if v[0] > cutoff]
                    if not self._data[gid][uid]:
                        del self._data[gid][uid]
                if not self._data[gid]:
                    del self._data[gid]


class SpamTracker:
    """In-memory message rate tracker per guild per user."""

    def __init__(self):
        # {guild_id: {user_id: [(timestamp, message_id, content)]}}
        self._data = defaultdict(lambda: defaultdict(list))
        self._lock = asyncio.Lock()

    async def add(self, guild_id: int, user_id: int, message_id: int, content: str):
        async with self._lock:
            self._data[guild_id][user_id].append((datetime.now(timezone.utc), message_id, content))

    async def check(self, guild_id: int, user_id: int, threshold: int, window: int) -> list:
        """Return list of message IDs to delete if user is spamming."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(seconds=window)
            entries = [e for e in self._data[guild_id][user_id] if e[0] > cutoff]
            self._data[guild_id][user_id] = entries
            if len(entries) >= threshold:
                return [e[1] for e in entries]
            return []

    async def check_duplicates(self, guild_id: int, user_id: int, limit: int = 3, window: int = 10) -> list:
        """Return list of duplicate message IDs if limit is exceeded."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(seconds=window)
            entries = [e for e in self._data[guild_id][user_id] if e[0] > cutoff]
            self._data[guild_id][user_id] = entries

            # Group messages by content
            counts = defaultdict(list)
            for timestamp, msg_id, content in entries:
                counts[content].append(msg_id)

            for content, msg_ids in counts.items():
                if len(msg_ids) >= limit:
                    return msg_ids
            return []

    async def cleanup(self):
        """Remove entries older than 60 seconds."""
        async with self._lock:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
            for gid in list(self._data.keys()):
                for uid in list(self._data[gid].keys()):
                    self._data[gid][uid] = [e for e in self._data[gid][uid] if e[0] > cutoff]
                    if not self._data[gid][uid]:
                        del self._data[gid][uid]
                if not self._data[gid]:
                    del self._data[gid]


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spam_tracker = SpamTracker()
        self.violation_tracker = ViolationTracker()  # Enhanced violation tracking
        self.ml_detector = MLSpamDetector()  # ML-based spam detection
        self.webhook_detector = WebhookThreatDetector()  # Advanced webhook threat detection
        self._cleanup_task = None
        self._alert_cooldowns = {}
        self.logger = get_logger()
        
        # Per-guild message history for pattern analysis
        self.message_history: Dict[int, Dict[int, List[str]]] = {}  # guild_id -> user_id -> [messages]
        
        # Webhook info cache to avoid repeated API calls
        self.webhook_cache: Dict[int, Tuple[discord.Webhook, datetime]] = {}  # webhook_id -> (webhook, cached_at)
        self.webhook_cache_ttl = 300  # 5 minutes cache TTL
        
        # Rate limit tracking for webhook operations
        self.webhook_api_cooldowns: Dict[int, datetime] = {}  # webhook_id -> last_api_call

    async def cog_load(self):
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def cog_unload(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()

    async def _cleanup_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(30)
            await self.spam_tracker.cleanup()
            await self.violation_tracker.cleanup()  # Cleanup violation tracker
            
            # Cleanup webhook cache (remove entries older than TTL)
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.webhook_cache_ttl)
            for webhook_id in list(self.webhook_cache.keys()):
                webhook, cached_at = self.webhook_cache[webhook_id]
                if cached_at < cutoff:
                    del self.webhook_cache[webhook_id]
            
            # Cleanup message history (remove entries older than 1 hour)
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
            for guild_id in list(self.message_history.keys()):
                for user_id in list(self.message_history[guild_id].keys()):
                    # Keep only recent messages (simplified cleanup)
                    if len(self.message_history[guild_id][user_id]) > 10:
                        self.message_history[guild_id][user_id] = self.message_history[guild_id][user_id][-10:]
                    
                    # Remove empty user entries
                    if not self.message_history[guild_id][user_id]:
                        del self.message_history[guild_id][user_id]
                
                # Remove empty guild entries
                if not self.message_history[guild_id]:
                    del self.message_history[guild_id]

    async def _fetch_webhook_with_cache(self, webhook_id: int) -> discord.Webhook | None:
        """Fetch webhook with caching and rate limit handling to avoid API abuse."""
        # Check cache first
        if webhook_id in self.webhook_cache:
            webhook, cached_at = self.webhook_cache[webhook_id]
            # Cache is still valid
            if (datetime.now(timezone.utc) - cached_at).total_seconds() < self.webhook_cache_ttl:
                return webhook
        
        # Check if we're rate limited for this webhook
        if webhook_id in self.webhook_api_cooldowns:
            last_call = self.webhook_api_cooldowns[webhook_id]
            if (datetime.now(timezone.utc) - last_call).total_seconds() < 2:  # 2 second cooldown
                return None  # Skip this fetch to avoid rate limits
        
        # Fetch with rate limit handling
        try:
            webhook = await self.bot.fetch_webhook(webhook_id)
            
            # Cache the result
            self.webhook_cache[webhook_id] = (webhook, datetime.now(timezone.utc))
            self.webhook_api_cooldowns[webhook_id] = datetime.now(timezone.utc)
            
            return webhook
        except discord.errors.HTTPException as e:
            if e.status == 429:  # Rate limit hit
                self.logger.warning(f"Rate limited while fetching webhook {webhook_id}, skipping")
                self.webhook_api_cooldowns[webhook_id] = datetime.now(timezone.utc)
                return None
            elif e.status == 404:  # Webhook not found
                self.logger.warning(f"Webhook {webhook_id} not found, removing from cache")
                self.webhook_cache.pop(webhook_id, None)
                return None
            else:
                self.logger.error(f"Failed to fetch webhook {webhook_id}: {e}")
                return None
        except Exception as e:
            self.logger.error(f"Unexpected error fetching webhook {webhook_id}: {e}")
            return None

    async def _should_ignore(self, message: discord.Message, module: str = "automod") -> bool:
        """Check if message should be ignored by AutoMod."""
        if not message.guild:
            return True
        if message.author.id == self.bot.user.id:
            return True
        # Skip normal bots but keep scanning Webhooks
        if message.author.bot and not message.webhook_id:
            return True
        
        # Check if author has administrator permission (handle User vs Member objects)
        # User objects don't have guild_permissions, need to get Member object
        if isinstance(message.author, discord.Member):
            if message.author.guild_permissions.administrator:
                return True  # Admins bypass automod
        elif message.guild:
            # If author is a User object, try to get their Member object
            member = message.guild.get_member(message.author.id)
            if member and member.guild_permissions.administrator:
                return True  # Admins bypass automod

        settings = await get_guild(message.guild.id)
        if not settings.get("automod_enabled", 1):
            return True

        ignored = await get_ignored_channels(message.guild.id, module)
        if message.channel.id in ignored:
            return True
        return False

    async def _log_automod(self, guild: discord.Guild, rule: str, user: discord.Member | discord.User, content: str, action: str, channel: discord.TextChannel = None):
        """Log automod action with rate-limiting to prevent log channel spam."""
        await log_action(guild.id, "automod", user.id, {
            "rule": rule,
            "content_preview": content[:200],
            "action": action,
        })

        # Cooldown checks: limit logs for the same user + rule to once every 10 seconds
        cooldown_key = (guild.id, user.id, rule)
        now = datetime.now(timezone.utc)
        if cooldown_key in self._alert_cooldowns:
            if now < self._alert_cooldowns[cooldown_key] + timedelta(seconds=10):
                return
        self._alert_cooldowns[cooldown_key] = now

        settings = await get_guild(guild.id)
        log_ch_id = settings.get("log_channel", 0)
        if log_ch_id:
            ch = guild.get_channel(log_ch_id)
            if ch:
                ch_mention = channel.mention if channel else "Unknown"
                embed = alert_embed(
                    f"AutoMod: {rule}",
                    f"**User:** {user.mention} (`{user.id}`)\n"
                    f"**Channel:** {ch_mention}\n"
                    f"**Action:** {action}\n"
                    f"**Preview:** {content[:500]}"
                )
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass

    async def _timeout_user(self, member: discord.Member, minutes: int, reason: str):
        try:
            until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            await member.timeout(until, reason=reason)
        except Exception:
            pass

    async def _delete_messages(self, channel: discord.TextChannel, message_ids: list):
        """Bulk delete messages by ID."""
        for mid in message_ids:
            try:
                msg = await channel.fetch_message(mid)
                await msg.delete()
            except Exception:
                pass

    async def _punish_user(self, message: discord.Message, rule: str, reason: str):
        """Escalate strike counts and apply corresponding punishments."""
        guild = message.guild
        author = message.author
        content = message.content

        # ── Webhook Special Handling ──
        if message.webhook_id:
            # Track webhook message for analysis
            self.webhook_detector.track_webhook_message(message.webhook_id, content, author.id)
            
            # Advanced webhook threat detection
            content_threat = self.webhook_detector.analyze_content_threat(content)
            behavior_threat = self.webhook_detector.analyze_webhook_behavior(message.webhook_id)
            
            action = "Webhook Message Deleted"
            
            # Use cached webhook fetching with rate limit protection
            webhook = await self._fetch_webhook_with_cache(message.webhook_id)
            
            if webhook:
                # Enhanced webhook verification: check if webhook is managed by bot or trusted user
                webhook_creator = getattr(webhook, 'user', None)
                is_trusted_webhook = False
                
                if webhook_creator:
                    # Check if webhook creator is whitelisted or is a bot
                    try:
                        from database import get_whitelist_entry
                        creator_whitelist = await get_whitelist_entry(guild.id, webhook_creator.id)
                        if creator_whitelist and creator_whitelist.get('trust_level', 0) >= 1:
                            is_trusted_webhook = True
                    except Exception as e:
                        self.logger.error(f"Error checking webhook creator whitelist: {e}")
                
                # Check rate limits
                rate_limited, rate_reason = self.webhook_detector.check_rate_limit(message.webhook_id)
                
                # Determine action based on threat levels and trust
                should_delete_webhook = False
                should_delete_message = True
                
                if not is_trusted_webhook:
                    # Check for critical threats ONLY - be less aggressive to avoid rate limits
                    if content_threat['threat_level'] == 'CRITICAL' or behavior_threat['risk_level'] == 'CRITICAL':
                        should_delete_webhook = True
                        self.webhook_detector.record_violation(message.webhook_id, "critical_threat")
                    
                    # Only delete webhook for critical threats to avoid rate limits
                    # High threats will still have their messages deleted but webhooks preserved
                    elif content_threat['threat_level'] == 'HIGH' or behavior_threat['risk_level'] == 'HIGH':
                        # Just delete the message, not the webhook
                        should_delete_webhook = False
                        self.webhook_detector.record_violation(message.webhook_id, "high_risk_behavior")
                
                # Execute webhook deletion with proper error handling
                if should_delete_webhook:
                    try:
                        await webhook.delete(reason=f"[Repent AutoMod] Webhook deleted for security violation: {reason}")
                        action = f"Webhook Deleted (Security Risk: {reason})"
                        self.logger.security("WEBHOOK_DELETE", 
                            f"Webhook {webhook.id} deleted - Content Threat: {content_threat['threat_level']}, Behavior Risk: {behavior_threat['risk_level']}", 
                            guild_id=guild.id, extra={
                                "webhook_id": webhook.id, 
                                "content_threat": content_threat, 
                                "behavior_threat": behavior_threat,
                                "rate_limited": not rate_limited,
                                "rate_reason": rate_reason
                            })
                    except discord.errors.HTTPException as e:
                        if e.status == 429:  # Rate limit hit during deletion
                            self.logger.warning(f"Rate limited while deleting webhook {webhook.id}, skipping deletion")
                            action = f"Webhook Message Deleted (Rate Limited, Webhook Preserved) - {reason}"
                        else:
                            self.logger.error(f"HTTP error deleting webhook {webhook.id}: {e}")
                            action = f"Webhook Message Deleted (Deletion Failed: {e}) - {reason}"
                    except Exception as e:
                        self.logger.error(f"Error deleting webhook {webhook.id}: {e}")
                        action = f"Webhook Message Deleted (Deletion Error: {e}) - {reason}"
                elif is_trusted_webhook:
                    action = f"Trusted Webhook Message Deleted (Webhook Preserved) - {reason}"
                    self.logger.warning(f"Trusted webhook {webhook.id} violated automod but was preserved")
                else:
                    action = f"Webhook Message Deleted (Safe Webhook Preserved) - {reason}"
                
                # Log detailed threat analysis
                if content_threat['is_threat'] or behavior_threat['is_suspicious']:
                    try:
                        await log_action(guild.id, "webhook_threat_detected", webhook.id, {
                            "content_threat": content_threat,
                            "behavior_threat": behavior_threat,
                            "rule_violated": rule,
                            "reason": reason
                        })
                    except Exception as e:
                        self.logger.error(f"Error logging webhook threat: {e}")
            else:
                # Webhook fetch failed or was rate limited
                action = f"Webhook Message Deleted (Webhook Unavailable) - {reason}"
                self.logger.warning(f"Could not fetch webhook {message.webhook_id}, proceeding with message deletion only")

            await self._log_automod(guild, rule, author, content, action, message.channel)
            return

        # ── Guild Member Handling ──
        strikes = await add_strike(guild.id, author.id)
        action = ""

        if strikes == 1:
            action = "Warning"
            try:
                await author.send(f"⚠️ **Warning**: You received an AutoMod warning in **{guild.name}** for: {reason}.")
            except Exception:
                pass
            try:
                await message.channel.send(f"{author.mention} Please follow the rules: {reason}.", delete_after=5)
            except Exception:
                pass
        elif strikes == 2:
            action = "Timeout (10m)"
            await self._timeout_user(author, 10, f"[AutoMod] {reason}")
            try:
                await message.channel.send(f"🔇 {author.mention} has been timed out for 10 minutes (Strikes: 2). Reason: {reason}.", delete_after=10)
            except Exception:
                pass
        elif strikes == 3:
            action = "Timeout (1h)"
            await self._timeout_user(author, 60, f"[AutoMod] {reason}")
            try:
                await message.channel.send(f"🔇 {author.mention} has been timed out for 1 hour (Strikes: 3). Reason: {reason}.", delete_after=10)
            except Exception:
                pass
        else:
            action = "Ban"
            try:
                await guild.ban(author, reason=f"[AutoMod] {reason} (Max strikes: {strikes})", delete_message_days=0)
                await clear_strikes(guild.id, author.id)
            except Exception:
                pass
            try:
                await message.channel.send(f"🔨 {author.name} has been banned from the server (Max strikes reached). Reason: {reason}.", delete_after=10)
            except Exception:
                pass

        await self._log_automod(guild, rule, author, content, action, message.channel)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if await self._should_ignore(message):
            return

        guild = message.guild
        author = message.author
        content = message.content
        config = await get_automod_config(guild.id)

        # ── Anti-Spam ──
        if config.get("anti_spam", 1):
            threshold = config.get("spam_threshold", 5)
            window = config.get("spam_window", 5)
            await self.spam_tracker.add(guild.id, author.id, message.id, content)

            # Add to message history for ML analysis
            if guild.id not in self.message_history:
                self.message_history[guild.id] = {}
            if author.id not in self.message_history[guild.id]:
                self.message_history[guild.id][author.id] = []
            self.message_history[guild.id][author.id].append(content)
            
            # Keep only last 20 messages per user
            if len(self.message_history[guild.id][author.id]) > 20:
                self.message_history[guild.id][author.id] = self.message_history[guild.id][author.id][-20:]

            # Check message rate
            spam_ids = await self.spam_tracker.check(guild.id, author.id, threshold, window)
            if spam_ids:
                # Track violation for enhanced security
                await self.violation_tracker.add_violation(guild.id, author.id, "spam", severity=3)
                
                await self._delete_messages(message.channel, spam_ids)
                await self._punish_user(message, "anti_spam", "Spamming messages")
                return

            # Check duplicate content
            dup_ids = await self.spam_tracker.check_duplicates(guild.id, author.id, limit=3, window=10)
            if dup_ids:
                # Track violation for enhanced security
                await self.violation_tracker.add_violation(guild.id, author.id, "duplicate", severity=2)
                
                await self._delete_messages(message.channel, dup_ids)
                await self._punish_user(message, "anti_spam_duplicate", "Sending duplicate messages")
                return

            # ML-based pattern detection
            user_messages = self.message_history[guild.id].get(author.id, [])
            if len(user_messages) >= 3:  # Need at least 3 messages for pattern analysis
                ml_analysis = self.ml_detector.analyze_message_patterns(user_messages)
                if ml_analysis["is_spam"] and ml_analysis["confidence"] > 0.7:
                    # Get recent message IDs to delete
                    recent_msg_ids = []
                    async for msg in message.channel.history(limit=10):
                        if msg.author == author:
                            recent_msg_ids.append(msg.id)
                    
                    if recent_msg_ids:
                        await self._delete_messages(message.channel, recent_msg_ids)
                        await self._punish_user(message, "ml_spam_detection", 
                            f"ML pattern detection: {ml_analysis['reason']} (Confidence: {ml_analysis['confidence']:.2f})")
                        self.logger.security("ML_SPAM_DETECTION", 
                            f"ML detected spam: {ml_analysis['reason']}", 
                            guild_id=guild.id, user_id=author.id,
                            extra={"confidence": ml_analysis["confidence"], "details": ml_analysis["details"]})
                        return

            # Check character limit
            if config.get("char_limit_enabled", 1):
                char_limit = config.get("char_limit", 3000)
                if len(content) > char_limit:
                    # Track violation for enhanced security
                    await self.violation_tracker.add_violation(guild.id, author.id, "char_limit", severity=2)
                    
                    # Check if user is a repeat offender (fast escalation)
                    severity_score = await self.violation_tracker.get_severity_score(guild.id, author.id, window_minutes=5)
                    
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    
                    # Enhanced punishment for repeat offenders
                    if severity_score >= 6:  # 3+ violations in 5 minutes
                        # Skip to timeout/ban immediately
                        await self._punish_user(message, "char_limit_repeat", f"Repeated character limit violations (Severity: {severity_score})")
                    else:
                        await self._punish_user(message, "char_limit", f"Message too long ({len(content)} > {char_limit} characters)")
                    
                    self.logger.security("CHAR_LIMIT_EXCEEDED", 
                        f"User {author.id} exceeded character limit: {len(content)} > {char_limit}", 
                        guild_id=guild.id, user_id=author.id,
                        extra={"length": len(content), "limit": char_limit, "severity_score": severity_score})
                    return

            # Check line limit (enhanced wall of text detection)
            if config.get("line_limit_enabled", 1):
                line_limit = config.get("line_limit", 15)
                line_count = content.count('\n') + 1  # +1 to count the first line
                if line_count > line_limit:
                    # Track violation for enhanced security
                    await self.violation_tracker.add_violation(guild.id, author.id, "line_limit", severity=2)
                    
                    # Check if user is a repeat offender (fast escalation)
                    severity_score = await self.violation_tracker.get_severity_score(guild.id, author.id, window_minutes=5)
                    
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    
                    # Enhanced punishment for repeat offenders
                    if severity_score >= 6:  # 3+ violations in 5 minutes
                        # Skip to timeout/ban immediately
                        await self._punish_user(message, "line_limit_repeat", f"Repeated line limit violations (Severity: {severity_score})")
                    else:
                        await self._punish_user(message, "line_limit", f"Wall of text ({line_count} > {line_limit} lines)")
                    
                    self.logger.security("LINE_LIMIT_EXCEEDED", 
                        f"User {author.id} exceeded line limit: {line_count} > {line_limit}", 
                        guild_id=guild.id, user_id=author.id,
                        extra={"lines": line_count, "limit": line_limit, "severity_score": severity_score})
                    return
            
            # Evasion technique detection
            evasion_detected = self.ml_detector.detect_evasion_techniques(content)
            if evasion_detected and config.get("anti_evasion", 1):
                techniques = ", ".join(evasion_detected.keys())
                # Track violation for enhanced security
                await self.violation_tracker.add_violation(guild.id, author.id, "evasion", severity=3)
                
                try:
                    await message.delete()
                except Exception:
                    pass
                await self._punish_user(message, "evasion_techniques", f"Evasion techniques detected: {techniques}")
                self.logger.security("EVASION_DETECTED", 
                    f"Evasion techniques: {techniques}", 
                    guild_id=guild.id, user_id=author.id,
                    extra={"techniques": list(evasion_detected.keys())})
                return
            
            # Multi-language spam detection
            lang_spam = self.ml_detector.detect_language_spam(content)
            if lang_spam and config.get("anti_lang_spam", 1):
                languages = ", ".join(lang_spam)
                # Track violation for enhanced security
                await self.violation_tracker.add_violation(guild.id, author.id, "lang_spam", severity=2)
                
                try:
                    await message.delete()
                except Exception:
                    pass
                await self._punish_user(message, "language_spam", f"Non-Latin spam detected: {languages}")
                self.logger.security("LANGUAGE_SPAM", 
                    f"Language spam: {languages}", 
                    guild_id=guild.id, user_id=author.id,
                    extra={"languages": lang_spam})
                return

        # ── Anti-Mass-Mention ──
        if config.get("anti_mention", 1) and not (hasattr(author, "guild_permissions") and author.guild_permissions.mention_everyone):
            user_mentions = len(MENTION_REGEX.findall(content))
            role_mentions = len(ROLE_MENTION_REGEX.findall(content))
            total_mentions = user_mentions + role_mentions
            limit = config.get("mention_limit", 5)
            if total_mentions > limit:
                # Track violation for enhanced security
                await self.violation_tracker.add_violation(guild.id, author.id, "mass_mention", severity=3)
                
                try:
                    await message.delete()
                except Exception:
                    pass
                await self._punish_user(message, "anti_mention", f"Mass mentions ({total_mentions} > {limit})")
                return

        # ── Anti-Invite ──
        if config.get("anti_invite", 1) and not (hasattr(author, "guild_permissions") and author.guild_permissions.manage_guild):
            invites = INVITE_REGEX.findall(content)
            if invites:
                try:
                    await message.delete()
                except Exception:
                    pass
                await self._punish_user(message, "anti_invite", "Posting server invites")
                return

        # ── Anti-Link ──
        if config.get("anti_link", 0) and not (hasattr(author, "guild_permissions") and author.guild_permissions.manage_messages):
            links = URL_REGEX.findall(content)
            if links:
                try:
                    await message.delete()
                except Exception:
                    pass
                await self._punish_user(message, "anti_link", "Posting links")
                return

        # ── Anti-Caps ──
        if config.get("anti_caps", 1) and len(content) >= 10:
            caps_percent = config.get("caps_percent", 70)
            letters = [c for c in content if c.isalpha()]
            if letters and (sum(1 for c in letters if c.isupper()) / len(letters)) * 100 >= caps_percent:
                try:
                    await message.delete()
                except Exception:
                    pass
                await self._punish_user(message, "anti_caps", "Excessive caps")
                return

        # ── Anti-Emoji Spam ──
        if config.get("anti_emoji", 1):
            emojis = EMOJI_REGEX.findall(content)
            if len(emojis) > config.get("emoji_limit", 8):
                try:
                    await message.delete()
                except Exception:
                    pass
                await self._punish_user(message, "anti_emoji", "Excessive emoji spam")
                return

        # ── Bad Word Filter ──
        bad_words = await get_bad_words(guild.id)
        if bad_words:
            lower = content.lower()
            for word in bad_words:
                if word in lower:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    await self._punish_user(message, "bad_word", f"Using forbidden word: {word}")
                    return

        # ── Token Protection ──
        settings = await get_guild(guild.id)
        if settings.get("anti_token_enabled", 0):
            # Get sensitivity level and corresponding patterns
            sensitivity = settings.get("anti_token_sensitivity", "medium")
            
            # Token patterns by sensitivity level
            token_patterns = {
                "high": [
                    r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}",  # Discord bot tokens
                    r"mfa\.[A-Za-z0-9_-]{20,}",  # MFA tokens
                    r"sk_live_[a-zA-Z0-9]{20,}",  # Stripe live keys
                    r"sk_test_[a-zA-Z0-9]{20,}",  # Stripe test keys
                ],
                "medium": [
                    r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}",  # Discord bot tokens
                    r"mfa\.[A-Za-z0-9_-]{20,}",  # MFA tokens
                ],
                "low": [
                    r"[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}",  # Discord bot tokens only
                ]
            }
            
            patterns = token_patterns.get(sensitivity, token_patterns["medium"])
            tokens = []
            for pattern in patterns:
                tokens.extend(re.findall(pattern, content))
            
            if tokens:
                try:
                    await message.delete()
                except Exception:
                    pass
                await self._punish_user(message, "token_leak", f"Posting Discord tokens ({len(tokens)} found)")
                # Log the incident for security monitoring
                self.logger.security("TOKEN_LEAK", f"Detected {len(tokens)} token(s) in message (sensitivity: {sensitivity})", 
                                   guild_id=guild.id, user_id=author.id, 
                                   extra={"tokens_found": len(tokens), "sensitivity": sensitivity, "channel_id": message.channel.id})
                return

        # ── Phishing Detection ──
        # Known suspicious domains and patterns
        suspicious_domains = [
            'discord-login.com', 'discord-gift.com', 'discord-nitro.com',
            'free-discord-nitro.com', 'discord-steal.com', 'discord-token.com',
            'discord-verify.com', 'discord-confirm.com', 'discord-support.com'
        ]
        suspicious_patterns = [
            r'login.*discord', r'verify.*discord', r'confirm.*discord',
            r'gift.*nitro', r'free.*nitro', r'steal.*token'
        ]
        
        # Check for suspicious domains
        for domain in suspicious_domains:
            if domain in content.lower():
                try:
                    await message.delete()
                except Exception:
                    pass
                await self._punish_user(message, "phishing", f"Posting phishing link ({domain})")
                self.logger.security("PHISHING_ATTEMPT", f"Detected suspicious domain: {domain}",
                                   guild_id=guild.id, user_id=author.id,
                                   extra={"domain": domain, "channel_id": message.channel.id})
                return
        
        # Check for suspicious patterns
        for pattern in suspicious_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                # If it contains a URL, it might be phishing
                if URL_REGEX.search(content):
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    await self._punish_user(message, "phishing", f"Suspicious pattern detected: {pattern}")
                    self.logger.security("PHISHING_ATTEMPT", f"Detected suspicious pattern: {pattern}",
                                       guild_id=guild.id, user_id=author.id,
                                       extra={"pattern": pattern, "channel_id": message.channel.id})
                    return

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        await self.on_message(after)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Anti-Ghost-Ping listener."""
        if not message.guild or message.author.bot:
            return

        # Filter mentions to find non-bots who are not the author
        if message.mentions:
            real_mentions = [m for m in message.mentions if not m.bot and m.id != message.author.id]
            if real_mentions:
                mentions_str = ", ".join(m.mention for m in real_mentions)
                await log_action(message.guild.id, "ghost_ping", message.author.id, {
                    "mentions": [m.id for m in real_mentions],
                    "content": message.content[:200]
                })

                settings = await get_guild(message.guild.id)
                log_ch_id = settings.get("log_channel", 0)
                if log_ch_id:
                    ch = message.guild.get_channel(log_ch_id)
                    if ch:
                        embed = discord.Embed(
                            title="👻 Ghost Ping Detected",
                            description=f"**User:** {message.author.mention} (`{message.author.id}`)\n"
                                        f"**Channel:** {message.channel.mention}\n"
                                        f"**Pinged Users:** {mentions_str}\n"
                                        f"**Content:** {message.content[:500]}",
                            color=0xFFAA00
                        )
                        embed.timestamp = datetime.now(timezone.utc)
                        try:
                            await ch.send(embed=embed)
                        except Exception:
                            pass

    # ── AutoMod Slash Commands ──

    @discord.app_commands.command(name="automod", description="Enable or disable automod (Admin only)")
    @discord.app_commands.describe(action="enable or disable")
    async def automod(self, interaction: discord.Interaction, action: str):
        if not interaction.user.guild_permissions.administrator and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        from database import update_guild
        enabled = 1 if action.lower() in ("enable", "on", "true") else 0
        await update_guild(interaction.guild.id, automod_enabled=enabled)
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            embed=success_embed("AutoMod Updated", f"AutoMod has been **{status}** in this server."),
            ephemeral=False,
        )

    @discord.app_commands.command(name="badword", description="Add or remove bad words (Admin only)")
    @discord.app_commands.describe(action="add or remove", word="The word to add/remove")
    async def badword(self, interaction: discord.Interaction, action: str, word: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        from database import add_bad_word, remove_bad_word, get_bad_words
        word = word.lower().strip()
        if action.lower() == "add":
            await add_bad_word(interaction.guild.id, word)
            await interaction.response.send_message(
                embed=success_embed("Bad Word Added", f"`{word}` has been added to the filter."),
                ephemeral=False,
            )
        elif action.lower() in ("remove", "delete", "rm"):
            await remove_bad_word(interaction.guild.id, word)
            await interaction.response.send_message(
                embed=success_embed("Bad Word Removed", f"`{word}` has been removed from the filter."),
                ephemeral=False,
            )
        elif action.lower() == "list":
            words = await get_bad_words(interaction.guild.id)
            if not words:
                return await interaction.response.send_message(
                    embed=info_embed("Bad Words", "No bad words configured."), ephemeral=False
                )
            await interaction.response.send_message(
                embed=info_embed("Bad Words", ", ".join(f"`{w}`" for w in words)), ephemeral=False
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Invalid action. Use: add, remove, or list."), ephemeral=True
            )

    @discord.app_commands.command(name="ignore", description="Ignore a channel from automod (Admin only)")
    @discord.app_commands.describe(channel="Channel to ignore", module="Which module to ignore (default: all)")
    async def ignore(self, interaction: discord.Interaction, channel: discord.TextChannel, module: str = "all"):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        from database import add_ignored_channel
        await add_ignored_channel(interaction.guild.id, channel.id, module)
        await interaction.response.send_message(
            embed=success_embed("Channel Ignored", f"{channel.mention} is now ignored for `{module}` automod rules."),
            ephemeral=False,
        )

    @discord.app_commands.command(name="unignore", description="Remove a channel from automod ignore list (Admin only)")
    @discord.app_commands.describe(channel="Channel to unignore")
    async def unignore(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        from database import remove_ignored_channel
        await remove_ignored_channel(interaction.guild.id, channel.id, "all")
        await interaction.response.send_message(
            embed=success_embed("Channel Unignored", f"{channel.mention} is no longer ignored."),
            ephemeral=False,
        )

    # ── Individual Automod Toggles ──
    @discord.app_commands.command(name="antinsfw", description="Toggle anti-NSFW filter (Admin only)")
    @app_commands.describe(action="enable or disable")
    async def antinsfw(self, interaction: discord.Interaction, action: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        from database import update_guild
        enabled = 1 if action.lower() in ("enable", "on", "true") else 0
        await update_guild(interaction.guild.id, automod_anti_nsfw=enabled)
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            embed=success_embed("Anti-NSFW Updated", f"Anti-NSFW filter has been **{status}**."),
            ephemeral=False,
        )

    @discord.app_commands.command(name="antilink", description="Toggle anti-link filter (Admin only)")
    @app_commands.describe(action="enable or disable")
    async def antilink(self, interaction: discord.Interaction, action: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        from database import update_guild, get_automod_config
        config = await get_automod_config(interaction.guild.id)
        current = config.get("anti_link", 0)
        enabled = 1 if action.lower() in ("enable", "on", "true") else 0
        
        # Update by setting the config directly
        from database import _get_db
        db = await _get_db()
        await db.execute(
            "UPDATE automod_config SET anti_link = ? WHERE guild_id = ?",
            (enabled, interaction.guild.id)
        )
        await db.commit()
        
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            embed=success_embed("Anti-Link Updated", f"Anti-link filter has been **{status}**."),
            ephemeral=False,
        )

    @discord.app_commands.command(name="antimention", description="Toggle anti-mention filter (Admin only)")
    @app_commands.describe(action="enable or disable")
    async def antimention(self, interaction: discord.Interaction, action: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        from database import get_automod_config, _get_db
        config = await get_automod_config(interaction.guild.id)
        enabled = 1 if action.lower() in ("enable", "on", "true") else 0
        
        db = await _get_db()
        await db.execute(
            "UPDATE automod_config SET anti_mention = ? WHERE guild_id = ?",
            (enabled, interaction.guild.id)
        )
        await db.commit()
        
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            embed=success_embed("Anti-Mention Updated", f"Anti-mention filter has been **{status}**."),
            ephemeral=False,
        )

    @discord.app_commands.command(name="antispam", description="Toggle anti-spam filter (Admin only)")
    @app_commands.describe(action="enable or disable")
    async def antispam(self, interaction: discord.Interaction, action: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        from database import get_automod_config, _get_db
        config = await get_automod_config(interaction.guild.id)
        enabled = 1 if action.lower() in ("enable", "on", "true") else 0
        
        db = await _get_db()
        await db.execute(
            "UPDATE automod_config SET anti_spam = ? WHERE guild_id = ?",
            (enabled, interaction.guild.id)
        )
        await db.commit()
        
        status = "enabled" if enabled else "disabled"
        await interaction.response.send_message(
            embed=success_embed("Anti-Spam Updated", f"Anti-spam filter has been **{status}**."),
            ephemeral=False,
        )

    @discord.app_commands.command(name="charlimit", description="Set character limit for messages (Admin only)")
    @app_commands.describe(action="enable, disable, or set", limit="Maximum characters (for 'set' action)")
    async def charlimit(self, interaction: discord.Interaction, action: str, limit: int = None):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        from database import update_automod_config, get_automod_config
        
        if action.lower() == "set":
            if limit is None or limit < 100 or limit > 10000:
                return await interaction.response.send_message(
                    embed=error_embed("Invalid limit. Must be between 100 and 10000 characters."), 
                    ephemeral=True
                )
            await update_automod_config(interaction.guild.id, char_limit=limit, char_limit_enabled=1)
            await interaction.response.send_message(
                embed=success_embed("Character Limit Set", f"Character limit has been set to **{limit}** characters."),
                ephemeral=False,
            )
        elif action.lower() in ("enable", "on"):
            await update_automod_config(interaction.guild.id, char_limit_enabled=1)
            config = await get_automod_config(interaction.guild.id)
            current_limit = config.get("char_limit", 3000)
            await interaction.response.send_message(
                embed=success_embed("Character Limit Enabled", f"Character limit has been enabled (**{current_limit}** characters)."),
                ephemeral=False,
            )
        elif action.lower() in ("disable", "off"):
            await update_automod_config(interaction.guild.id, char_limit_enabled=0)
            await interaction.response.send_message(
                embed=success_embed("Character Limit Disabled", "Character limit has been disabled."),
                ephemeral=False,
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Invalid action. Use: enable, disable, or set."), 
                ephemeral=True
            )

    @discord.app_commands.command(name="linelimit", description="Set line limit for messages (Admin only)")
    @app_commands.describe(action="enable, disable, or set", limit="Maximum lines (for 'set' action)")
    async def linelimit(self, interaction: discord.Interaction, action: str, limit: int = None):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        from database import update_automod_config, get_automod_config
        
        if action.lower() == "set":
            if limit is None or limit < 5 or limit > 100:
                return await interaction.response.send_message(
                    embed=error_embed("Invalid limit. Must be between 5 and 100 lines."), 
                    ephemeral=True
                )
            await update_automod_config(interaction.guild.id, line_limit=limit, line_limit_enabled=1)
            await interaction.response.send_message(
                embed=success_embed("Line Limit Set", f"Line limit has been set to **{limit}** lines."),
                ephemeral=False,
            )
        elif action.lower() in ("enable", "on"):
            await update_automod_config(interaction.guild.id, line_limit_enabled=1)
            config = await get_automod_config(interaction.guild.id)
            current_limit = config.get("line_limit", 15)
            await interaction.response.send_message(
                embed=success_embed("Line Limit Enabled", f"Line limit has been enabled (**{current_limit}** lines)."),
                ephemeral=False,
            )
        elif action.lower() in ("disable", "off"):
            await update_automod_config(interaction.guild.id, line_limit_enabled=0)
            await interaction.response.send_message(
                embed=success_embed("Line Limit Disabled", "Line limit has been disabled."),
                ephemeral=False,
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Invalid action. Use: enable, disable, or set."), 
                ephemeral=True
            )

    @discord.app_commands.command(name="antiraid", description="Toggle anti-raid mode (Admin only)")
    @app_commands.describe(action="enable or disable")
    async def antiraid(self, interaction: discord.Interaction, action: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(embed=error_embed("Administrator required."), ephemeral=True)

        from database import update_guild
        raid_mode = 1 if action.lower() in ("enable", "on", "true") else 0
        await update_guild(interaction.guild.id, raid_mode=raid_mode)
        status = "enabled" if raid_mode else "disabled"
        
        if raid_mode:
            embed = success_embed("Anti-Raid Enabled", "Anti-raid mode is now active. New members will be restricted.")
        else:
            embed = success_embed("Anti-Raid Disabled", "Anti-raid mode is now disabled. Normal member joining resumed.")
        
        await interaction.response.send_message(embed=embed, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
