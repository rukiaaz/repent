# Auto Restore & Antinuke System - Gap Analysis & Implementation Plan

## Current State Analysis

### Existing Capabilities ✅
- Basic channel restoration (name, type, overwrites, topic, nsfw, slowmode)
- Basic role restoration (name, permissions, color, hoist, mentionable, position)
- Single snapshot system in `guild_snapshots` table
- Targeted restore (only specific channel/role IDs)
- Guild name restoration
- Instant punishment for critical actions

### Identified Gaps ❌

#### 1. Consecutive Nuke Protection - CRITICAL GAP
**Problem:** Current system only stores ONE snapshot per guild. If a nuke happens, and then another nuke happens before restoration, the original snapshot data is overwritten with the corrupted state.

**Impact:** Cannot recover from multi-stage attacks.

#### 2. Channel Position & Category Ordering - CRITICAL GAP
**Problem:** Current restore sets channel position to cached value but doesn't ensure categories are in the right order or that channels within categories maintain their relative positions.

**Impact:** Channels may end up in wrong positions or wrong categories after restore.

#### 3. Role Hierarchy Restoration - CRITICAL GAP
**Problem:** Role position is restored, but the entire role hierarchy tree isn't systematically rebuilt. Dependencies between roles (e.g., @everyone at bottom) aren't guaranteed.

**Impact:** Role hierarchy may be broken after restore.

#### 4. No State Versioning - HIGH GAP
**Problem:** No way to restore to a specific point in time. Only "latest snapshot" is available.

**Impact:** Cannot rollback to before-attack state if multiple attacks occur.

#### 5. Snapshot Wiping Vulnerability - CRITICAL GAP
**Problem:** If an attacker gains admin access and runs a malicious script, they could wipe the snapshot table or insert fake snapshot data.

**Impact:** Complete loss of restore capability.

#### 6. Category Channel Relationships - MEDIUM GAP
**Problem:** When restoring channels, the category must exist first. Current system doesn't guarantee category creation before channel restoration.

**Impact:** Channel restore may fail if category was also deleted.

#### 7. Permission Overwrite Edge Cases - MEDIUM GAP
**Problem:** Overwrites reference roles/users by ID. If roles are deleted and recreated with different IDs, overwrites break.

**Impact:** Permissions may be incorrect after restore.

#### 8. Voice Channel Settings - LOW GAP
**Problem:** Voice channels have additional settings (bitrate, user limit) that aren't captured/restored.

**Impact:** Voice channel settings lost after restore.

#### 9. Thread Parent Relationships - LOW GAP
**Problem:** Threads reference parent channel IDs. If parent is deleted/recreated with new ID, threads break.

**Impact:** Threads may be orphaned after restore.

#### 10. Webhook References - LOW GAP
**Problem:** Channels may have webhooks associated. These aren't restored.

**Impact:** Webhooks lost after restore.

---

## Proposed Solution: Multi-Layer Backup System

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Antinuke Defense Layers                   │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Real-time Cache (In-Memory)                       │
│  - Last 5 minutes of changes                                │
│  - Fast access for immediate restore                        │
│  - Volatile, lost on restart                                │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Database Snapshots (Persistent)                    │
│  - Last 5 snapshots (hourly/daily/weekly)                   │
│  - Can restore to any snapshot                               │
│  - Protected against tampering                               │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Critical State Checkpoints (Immutable)             │
│  - Snapshot of admin role configuration                      │
│  - Snapshot of bot permissions                               │
│  - Cannot be deleted or modified                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Attack Detection & Lockdown                        │
│  - Consecutive attack detection                               │
│  - Automatic snapshot creation on detection                 │
│  - Emergency mode with enhanced monitoring                  │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Plan

#### Phase 1: Multi-Snapshot System (Consecutive Nuke Protection)

**1.1 Database Schema Updates**

```sql
-- Add snapshot versioning
ALTER TABLE guild_snapshots ADD COLUMN version INTEGER DEFAULT 1;
ALTER TABLE guild_snapshots ADD COLUMN checksum TEXT;  -- SHA-256 for tamper detection
ALTER TABLE guild_snapshots ADD COLUMN is_protected INTEGER DEFAULT 0;  -- Cannot delete protected snapshots
ALTER TABLE guild_snapshots ADD COLUMN trigger_event TEXT;  -- What triggered this snapshot
ALTER TABLE guild_snapshots ADD COLUMN previous_snapshot_id INTEGER;  -- Chain snapshots together
```

**1.2 Snapshot Creation Strategy**

```python
# Automatic snapshot schedule
- Hourly snapshots (keep last 24 hours = 24 snapshots)
- Daily snapshots (keep last 7 days = 7 snapshots)
- Weekly snapshots (keep last 4 weeks = 4 snapshots)
- On-demand snapshots (before risky operations)

# Maximum: 35 snapshots per guild
```

**1.3 Snapshot Selection Logic**

```python
def select_best_snapshot(guild_id, attack_timestamp):
    """Select the best snapshot to restore from based on attack time."""
    snapshots = get_snapshots(guild_id)
    
    # Find snapshot closest to but BEFORE attack_timestamp
    best_snapshot = None
    min_time_diff = float('inf')
    
    for snapshot in snapshots:
        snap_time = snapshot['timestamp']
        if snap_time < attack_timestamp:
            time_diff = attack_timestamp - snap_time
            if time_diff < min_time_diff:
                min_time_diff = time_diff
                best_snapshot = snapshot
    
    # If no snapshot before attack, use oldest available
    if not best_snapshot and snapshots:
        best_snapshot = snapshots[-1]  # Oldest snapshot
    
    return best_snapshot
```

#### Phase 2: Full State Restoration

**2.1 Enhanced Channel Restoration**

```python
async def restore_channels_full(guild, snapshot_data):
    """Restore channels with full state including category structure."""
    
    # 1. Create categories first (in correct order)
    categories = sorted(
        [c for c in snapshot_data['channels'] if c['type'] == 4],
        key=lambda x: x['position']
    )
    category_map = {}  # old_id -> new_id mapping
    
    for cat in categories:
        new_cat = await guild.create_category(
            name=cat['name'],
            position=cat['position'],
            overwrites=parse_overwrites(cat['overwrites']),
            reason="[Repent] Restore category"
        )
        category_map[cat['id']] = new_cat.id
    
    # 2. Create channels (in categories, correct position)
    non_category_channels = [
        c for c in snapshot_data['channels'] if c['type'] != 4
    ]
    
    for channel in non_category_channels:
        # Map old category_id to new category_id
        new_category_id = category_map.get(channel['category_id'])
        category = guild.get_channel(new_category_id) if new_category_id else None
        
        await create_channel_from_snapshot(guild, channel, category)
```

**2.2 Enhanced Role Restoration**

```python
async def restore_roles_full(guild, snapshot_data):
    """Restore roles with correct hierarchy."""
    
    # Sort roles by position (bottom to top)
    roles = sorted(
        snapshot_data['roles'],
        key=lambda x: x['position']
    )
    
    role_map = {}  # old_id -> new_id mapping
    
    for role in roles:
        # Skip @everyone (cannot be recreated)
        if role['name'] == '@everyone':
            role_map[role['id']] = guild.default_role.id
            continue
        
        new_role = await guild.create_role(
            name=role['name'],
            permissions=discord.Permissions(role['permissions']),
            color=discord.Color(role['color']),
            hoist=role['hoist'],
            mentionable=role['mentionable'],
            reason="[Repent] Restore role"
        )
        
        # Set position after creation
        await new_role.edit(position=role['position'])
        
        role_map[role['id']] = new_role.id
    
    return role_map
```

**2.3 Overwrite Mapping with New Role IDs**

```python
async def restore_overwrites_with_mapping(guild, channel, overwrites, role_map):
    """Restore permission overwrites with new role IDs."""
    new_overwrites = {}
    
    for target_id, allow, deny in overwrites:
        # Map old role ID to new role ID
        new_target_id = role_map.get(target_id, target_id)
        
        target = guild.get_role(new_target_id) or guild.get_member(new_target_id)
        if target:
            new_overwrites[target] = discord.PermissionOverwrite(
                overwrite=discord.Permissions(allow, deny)
            )
    
    await channel.edit(overwrites=new_overwrites)
```

#### Phase 3: Attack Resilience

**3.1 Consecutive Attack Detection**

```python
class ConsecutiveAttackDetector:
    def __init__(self):
        self.attack_history = {}  # guild_id -> list of attack timestamps
        self.consecutive_attack_window = 300  # 5 minutes
        self.consecutive_attack_threshold = 3  # 3 attacks in 5 minutes
    
    def is_consecutive_attack(self, guild_id):
        """Check if this is part of a consecutive attack sequence."""
        now = datetime.now(timezone.utc)
        window = timedelta(seconds=self.consecutive_attack_window)
        
        history = self.attack_history.get(guild_id, [])
        
        # Filter to attacks within window
        recent_attacks = [t for t in history if now - t < window]
        
        if len(recent_attacks) >= self.consecutive_attack_threshold:
            return True
        
        return False
    
    def record_attack(self, guild_id):
        """Record an attack for this guild."""
        now = datetime.now(timezone.utc)
        if guild_id not in self.attack_history:
            self.attack_history[guild_id] = []
        self.attack_history[guild_id].append(now)
```

**3.2 Emergency Mode Activation**

```python
async def activate_emergency_mode(self, guild):
    """Activate emergency mode for a guild under attack."""
    if guild.id in self._emergency_mode_active:
        return  # Already in emergency mode
    
    self._emergency_mode_active.add(guild.id)
    self._attack_detected_time[guild.id] = datetime.now(timezone.utc)
    
    # Create emergency snapshot BEFORE any restoration
    await self.create_protected_snapshot(guild, trigger="emergency_mode")
    
    # Increase monitoring frequency
    # Lock down risky operations
    # Alert server owner
```

**3.3 Protected Snapshots**

```python
async def create_protected_snapshot(self, guild, trigger="manual"):
    """Create a snapshot that cannot be deleted (except by owner)."""
    snapshot_data = build_snapshot_data(guild)
    checksum = calculate_sha256(json.dumps(snapshot_data))
    
    snapshot_id = await create_snapshot(
        guild.id,
        snapshot_data,
        is_protected=1,
        trigger_event=trigger,
        checksum=checksum
    )
    
    return snapshot_id
```

#### Phase 4: Tamper Protection

**4.1 Snapshot Verification**

```python
def verify_snapshot_integrity(snapshot):
    """Verify snapshot hasn't been tampered with."""
    expected_checksum = snapshot['checksum']
    data = json.loads(snapshot['data'])
    actual_checksum = calculate_sha256(json.dumps(data))
    
    return expected_checksum == actual_checksum
```

**4.2 Snapshot Chain Validation**

```python
def validate_snapshot_chain(guild_id):
    """Validate that snapshot chain is intact."""
    snapshots = get_snapshots(guild_id)
    
    for i in range(1, len(snapshots)):
        current = snapshots[i]
        previous = snapshots[i-1]
        
        # Verify current has correct previous_id reference
        if current['previous_snapshot_id'] != previous['id']:
            return False  # Chain broken
        
        # Verify current checksum
        if not verify_snapshot_integrity(current):
            return False  # Tampered
    
    return True
```

#### Phase 5: Voice Channel & Thread Support

**5.1 Voice Channel Settings**

```python
# Add to snapshot
'bitrate': channel.bitrate,
'user_limit': channel.user_limit,
'rtc_region': channel.rtc_region,

# Restore with
kwargs.update({
    'bitrate': channel_data.get('bitrate'),
    'user_limit': channel_data.get('user_limit'),
    'rtc_region': channel_data.get('rtc_region')
})
```

**5.2 Thread Restoration**

```python
async def restore_threads(guild, channel, snapshot_data):
    """Restore threads for a channel."""
    threads_data = snapshot_data.get('threads', [])
    
    for thread in threads_data:
        await channel.create_thread(
            name=thread['name'],
            type=discord.ChannelType[thread['type']],
            auto_archive_duration=thread['auto_archive_duration']
        )
```

---

## Implementation Order

### Priority 1: Critical Gaps (Must Have)
1. **Multi-snapshot system** - Prevent consecutive nuke data loss
2. **Snapshot versioning & selection** - Restore to correct point in time
3. **Category-first restoration** - Fix channel/category relationships
4. **Consecutive attack detection** - Auto-activate emergency mode
5. **Protected snapshots** - Prevent tampering

### Priority 2: High Gaps (Should Have)
6. **Role hierarchy restoration** - Fix role ordering
7. **Overwrite ID mapping** - Fix permissions after restore
8. **Emergency mode** - Enhanced monitoring during attacks

### Priority 3: Medium Gaps (Nice to Have)
9. **Snapshot checksum verification** - Tamper detection
10. **Snapshot chain validation** - Integrity checking

### Priority 4: Low Gaps (Future Enhancements)
11. **Voice channel settings** - Full voice restore
12. **Thread restoration** - Thread support
13. **Webhook restoration** - Webhook support

---

## Testing Strategy

### Test Scenarios

1. **Single Nuke Test**
   - Delete 10 channels
   - Verify restore recreates all channels
   - Verify channels in correct categories
   - Verify channels in correct positions

2. **Consecutive Nuke Test**
   - Delete 5 channels (attack 1)
   - Wait 1 minute
   - Delete 5 more channels (attack 2)
   - Verify restore uses snapshot before attack 1
   - Verify all 10 channels restored

3. **Category Delete Test**
   - Delete category with channels
   - Verify category restored first
   - Verify channels restored in category

4. **Role Hierarchy Test**
   - Delete role hierarchy (10 roles in specific order)
   - Verify roles restored in correct order
   - Verify role positions correct

5. **Tamper Test**
   - Manually modify snapshot in database
   - Verify checksum validation fails
   - Verify system rejects tampered snapshot

---

## Success Criteria

### Must Achieve
- ✅ Can restore from at least 5 previous snapshots
- ✅ Can withstand consecutive nukes (3+ attacks) without data loss
- ✅ Channels restore to correct categories and positions
- ✅ Roles restore with correct hierarchy
- ✅ Protected snapshots cannot be deleted by non-owners

### Should Achieve
- ✅ Restore completes within 30 seconds for 100 channels
- ✅ Snapshot creation takes < 5 seconds
- ✅ No performance impact on normal bot operations

### Nice to Have
- ✅ Full voice channel settings restored
- ✅ Threads restored
- ✅ Webhooks restored

---

## Risk Mitigation

### Database Growth
- **Risk:** Unlimited snapshots could bloat database
- **Mitigation:** Automatic cleanup of old snapshots (keep max 35 per guild)

### API Rate Limits
- **Risk:** Bulk restoration could hit Discord API limits
- **Mitigation:** Rate limiting with exponential backoff, priority queue for critical restores

### Performance Impact
- **Risk:** Frequent snapshotting could impact performance
- **Mitigation:** Asynchronous snapshot creation, throttle during high load

### False Positives
- **Risk:** Legitimate changes could trigger emergency mode
- **Mitigation:** Owner override, manual snapshot creation whitelist

---

## Implementation Timeline

### Week 1: Foundation
- Database schema updates
- Multi-snapshot system
- Snapshot versioning

### Week 2: Restoration Logic
- Category-first restoration
- Role hierarchy restoration
- Overwrite ID mapping

### Week 3: Attack Resilience
- Consecutive attack detection
- Emergency mode
- Protected snapshots

### Week 4: Testing & Polish
- Test suite creation
- Performance optimization
- Documentation updates
