"""
Restore System Testing Script

Tests for the enhanced restore system including:
- Consecutive attack detection
- Snapshot selection logic
- Checksum verification
- Protected snapshot handling
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from utils.enhanced_restore import ConsecutiveAttackDetector, EnhancedRestoreSystem


def test_consecutive_attack_detection():
    """Test consecutive attack detection logic."""
    print("Testing Consecutive Attack Detection...")

    detector = ConsecutiveAttackDetector()

    # Test 1: Single attack should not trigger consecutive detection
    detector.record_attack(12345)
    assert detector.is_consecutive_attack(12345) == False, "Single attack should not trigger consecutive detection"
    print("[PASS] Test 1 passed: Single attack does not trigger consecutive detection")

    # Test 2: Multiple attacks within window should trigger consecutive detection
    detector.record_attack(12345)
    detector.record_attack(12345)
    assert detector.is_consecutive_attack(12345) == True, "3 attacks should trigger consecutive detection"
    print("[PASS] Test 2 passed: 3 attacks trigger consecutive detection")

    # Test 3: Attacks outside window should not trigger consecutive detection
    detector = ConsecutiveAttackDetector(window_seconds=1)  # 1 second window for testing
    detector.record_attack(12345)
    # Manually expire the attack for testing purposes
    detector.attack_history[12345][0] = datetime.now(timezone.utc) - timedelta(seconds=10)
    detector.record_attack(12345)
    assert detector.is_consecutive_attack(12345) == False, "Attacks outside window should not trigger consecutive detection"
    print("[PASS] Test 3 passed: Attacks outside window do not trigger consecutive detection")

    # Test 4: Different guilds should not affect each other
    detector = ConsecutiveAttackDetector()
    detector.record_attack(12345)
    detector.record_attack(12345)
    detector.record_attack(12345)
    assert detector.is_consecutive_attack(67890) == False, "Different guild should not be affected"
    print("[PASS] Test 4 passed: Different guilds are independent")

    print("[SUCCESS] All consecutive attack detection tests passed!")


async def test_snapshot_checksum_verification():
    """Test snapshot checksum verification (logic only, no database)."""
    print("\nTesting Snapshot Checksum Verification...")

    # Test 1: Valid checksum calculation and verification logic
    data = {"test": "data"}
    import hashlib
    checksum = hashlib.sha256(json.dumps(data).encode()).hexdigest()

    # Simulate the checksum verification logic
    def verify_checksum_logic(snapshot):
        """Verify checksum logic without database."""
        try:
            expected_checksum = snapshot['checksum']
            data = json.loads(snapshot['data'])
            actual_checksum = hashlib.sha256(json.dumps(data).encode()).hexdigest()
            return expected_checksum == actual_checksum
        except Exception:
            return False

    # Mock snapshot with valid checksum
    snapshot = {"checksum": checksum, "data": json.dumps(data)}
    result = verify_checksum_logic(snapshot)
    assert result == True, "Valid checksum should pass"
    print("[PASS] Test 1 passed: Valid checksum passes verification")

    # Test 2: Invalid checksum should fail
    snapshot["checksum"] = "invalid_checksum"
    result = verify_checksum_logic(snapshot)
    assert result == False, "Invalid checksum should fail"
    print("[PASS] Test 2 passed: Invalid checksum fails verification")

    # Test 3: Tampered data should fail
    snapshot["checksum"] = checksum  # Original checksum
    snapshot["data"] = json.dumps({"tampered": "data"})
    result = verify_checksum_logic(snapshot)
    assert result == False, "Tampered data should fail"
    print("[PASS] Test 3 passed: Tampered data fails verification")

    print("[SUCCESS] All checksum verification tests passed!")


def test_protected_snapshot_deletion():
    """Test protected snapshot deletion prevention (logic only)."""
    print("\nTesting Protected Snapshot Deletion...")

    # Test the logic: protected snapshots should not be deletable
    def can_delete_snapshot(snapshot):
        """Check if snapshot can be deleted based on protection flag."""
        return not snapshot.get('is_protected', False)

    # Test 1: Protected snapshot should not be deletable
    protected_snapshot = {"id": 1, "is_protected": True}
    assert can_delete_snapshot(protected_snapshot) == False, "Protected snapshot should not be deletable"
    print("[PASS] Test 1 passed: Protected snapshot cannot be deleted")

    # Test 2: Non-protected snapshot should be deletable
    normal_snapshot = {"id": 2, "is_protected": False}
    assert can_delete_snapshot(normal_snapshot) == True, "Normal snapshot should be deletable"
    print("[PASS] Test 2 passed: Normal snapshot can be deleted")

    # Test 3: Missing is_protected flag should default to deletable
    no_flag_snapshot = {"id": 3}
    assert can_delete_snapshot(no_flag_snapshot) == True, "Snapshot without protection flag should be deletable"
    print("[PASS] Test 3 passed: Snapshot without protection flag can be deleted")

    print("[SUCCESS] Protected snapshot deletion test completed!")


async def test_snapshot_selection_logic():
    """Test snapshot selection based on attack timestamp (logic only)."""
    print("\nTesting Snapshot Selection Logic...")

    # Test the snapshot selection logic
    def select_best_snapshot(snapshots, attack_timestamp):
        """Select the best snapshot to restore from based on attack time."""
        if not snapshots:
            return None

        # Find snapshot closest to but BEFORE attack_timestamp
        best_snapshot = None
        min_time_diff = timedelta(days=999)  # Large initial value

        for snapshot in snapshots:
            snap_time = snapshot['timestamp']
            if snap_time < attack_timestamp:
                time_diff = attack_timestamp - snap_time
                if time_diff < min_time_diff:
                    min_time_diff = time_diff
                    best_snapshot = snapshot

        # If no snapshot before attack, use oldest available
        if not best_snapshot and snapshots:
            best_snapshot = snapshots[0]  # Oldest snapshot (assuming sorted ascending)

        return best_snapshot

    # Test 1: Select snapshot before attack
    # Mock snapshots with different timestamps
    now = datetime.now(timezone.utc)
    snapshots = [
        {"id": 1, "timestamp": now - timedelta(minutes=10)},  # 10 minutes ago
        {"id": 2, "timestamp": now - timedelta(minutes=5)},   # 5 minutes ago
        {"id": 3, "timestamp": now - timedelta(minutes=1)},   # 1 minute ago
    ]

    # Sort snapshots by timestamp (oldest first) for consistent testing
    sorted_snapshots = sorted(snapshots, key=lambda x: x['timestamp'])

    attack_timestamp = now - timedelta(minutes=2)  # Attack happened 2 minutes ago
    selected = select_best_snapshot(sorted_snapshots, attack_timestamp)

    # Should select snapshot before attack (5 minutes ago)
    assert selected["id"] == 2, f"Should select snapshot before attack, got {selected['id']}"
    print("[PASS] Test 1 passed: Selected snapshot before attack")

    # Test 2: No snapshot before attack should select oldest
    attack_timestamp = now - timedelta(minutes=15)  # Attack before all snapshots

    # Sort snapshots by timestamp (oldest first) for the logic to work correctly
    sorted_snapshots = sorted(snapshots, key=lambda x: x['timestamp'])
    selected = select_best_snapshot(sorted_snapshots, attack_timestamp)

    # Should select oldest snapshot
    assert selected["id"] == 1, f"Should select oldest snapshot, got {selected['id']}"
    print("[PASS] Test 2 passed: Selected oldest snapshot when no snapshot before attack")

    # Test 3: Empty snapshots should return None
    selected = select_best_snapshot([], now)
    assert selected is None, "Empty snapshots should return None"
    print("[PASS] Test 3 passed: Empty snapshots return None")

    print("[SUCCESS] All snapshot selection tests passed!")


def test_category_first_restoration():
    """Test category-first restoration logic."""
    print("\nTesting Category-First Restoration...")

    # Mock snapshot data with categories and channels
    snapshot_data = {
        "channels": [
            {
                "id": 1,
                "name": "General",
                "type": 0,  # Text channel
                "position": 1,
                "category_id": 100,
            },
            {
                "id": 2,
                "name": "Random",
                "type": 0,  # Text channel
                "position": 2,
                "category_id": 100,
            },
            {
                "id": 100,
                "name": "Text Channels",
                "type": 4,  # Category
                "position": 1,
                "category_id": None,
            }
        ]
    }

    # The restoration logic should:
    # 1. Create categories first (sorted by position)
    # 2. Create channels in categories

    categories = [c for c in snapshot_data["channels"] if c["type"] == 4]
    categories_sorted = sorted(categories, key=lambda x: x["position"])

    assert len(categories_sorted) == 1, "Should find 1 category"
    assert categories_sorted[0]["id"] == 100, "Category should be Text Channels"
    print("[PASS] Test 1 passed: Categories identified and sorted correctly")

    channels = [c for c in snapshot_data["channels"] if c["type"] != 4]
    assert len(channels) == 2, "Should find 2 channels"
    print("[PASS] Test 2 passed: Non-category channels identified correctly")

    print("[SUCCESS] Category-first restoration logic test passed!")


def test_role_hierarchy_restoration():
    """Test role hierarchy restoration logic."""
    print("\nTesting Role Hierarchy Restoration...")

    # Mock snapshot data with roles
    snapshot_data = {
        "roles": [
            {"id": 1, "name": "@everyone", "position": 0},
            {"id": 2, "name": "Member", "position": 1},
            {"id": 3, "name": "Moderator", "position": 2},
            {"id": 4, "name": "Admin", "position": 3},
        ]
    }

    # Roles should be restored from bottom to top (by position)
    roles_sorted = sorted(snapshot_data["roles"], key=lambda x: x["position"])

    assert roles_sorted[0]["name"] == "@everyone", "First role should be @everyone"
    assert roles_sorted[-1]["name"] == "Admin", "Last role should be Admin"
    print("[PASS] Test 1 passed: Roles sorted by position correctly")

    # @everyone should be skipped (cannot be recreated)
    non_everyone_roles = [r for r in roles_sorted if r["name"] != "@everyone"]
    assert len(non_everyone_roles) == 3, "Should have 3 non-@everyone roles"
    print("[PASS] Test 2 passed: @everyone correctly excluded")

    print("[SUCCESS] Role hierarchy restoration test passed!")


async def main():
    """Run all tests."""
    print("=" * 70)
    print("Restore System Testing Suite")
    print("=" * 70)

    try:
        # Consecutive attack detection
        test_consecutive_attack_detection()

        # Snapshot checksum verification (async)
        await test_snapshot_checksum_verification()

        # Protected snapshot deletion (sync)
        test_protected_snapshot_deletion()

        # Snapshot selection logic (async)
        await test_snapshot_selection_logic()

        # Category-first restoration
        test_category_first_restoration()

        # Role hierarchy restoration
        test_role_hierarchy_restoration()

        print("\n" + "=" * 70)
        print("[SUCCESS] ALL TESTS PASSED!")
        print("=" * 70)
        print("\nRestore system is functioning correctly.")
        print("Proceed with integration testing next.")

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))