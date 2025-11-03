"""
Test script for config migration system.

This script tests that the auto_join_timeout to auto_disconnect_timeout
migration works correctly.
"""

import json
import sys
import io
from pathlib import Path

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add bot directory to path
sys.path.insert(0, str(Path(__file__).parent))

from bot.core.config_migrations import migrate_config, get_migration_manager
from bot.version import get_version


def test_migration():
    """Test the config migration system."""
    print(f"Testing Config Migration System (Bot Version {get_version()})")
    print("=" * 60)

    # Test 1: Migrate old config key
    print("\nTest 1: Migrate old config key")
    print("-" * 60)
    old_config = {
        "Voice.auto_join_timeout": 600,
        "Voice.auto_join_enabled": True,
        "Soundboard.default_volume": 0.5
    }

    print(f"Old config: {json.dumps(old_config, indent=2)}")

    migrated, applied = migrate_config(old_config)

    print(f"\nMigrated config: {json.dumps(migrated, indent=2)}")
    print(f"\nApplied migrations ({len(applied)}):")
    for migration in applied:
        print(f"  - {migration}")

    # Verify
    assert "Voice.auto_join_timeout" not in migrated, "Old key should be removed"
    assert "Voice.auto_disconnect_timeout" in migrated, "New key should be present"
    assert migrated["Voice.auto_disconnect_timeout"] == 600, "Value should be preserved"
    assert migrated["Voice.auto_join_enabled"] == True, "Other keys should remain"
    print("\n✅ Test 1 PASSED")

    # Test 2: Config without old keys (no migration needed)
    print("\n\nTest 2: Config without old keys (no migration needed)")
    print("-" * 60)
    new_config = {
        "Voice.auto_disconnect_timeout": 300,
        "Voice.auto_join_enabled": True
    }

    print(f"Config: {json.dumps(new_config, indent=2)}")

    migrated, applied = migrate_config(new_config)

    print(f"\nMigrated config: {json.dumps(migrated, indent=2)}")
    print(f"\nApplied migrations: {len(applied)}")

    # Verify
    assert len(applied) == 0, "No migrations should be applied"
    assert migrated == new_config, "Config should be unchanged"
    print("\n✅ Test 2 PASSED")

    # Test 3: Check migration manager registry
    print("\n\nTest 3: Check migration manager registry")
    print("-" * 60)
    manager = get_migration_manager()
    print(f"Registered migrations: {len(manager.migrations)}")
    for old_key, migration in manager.migrations.items():
        print(f"  {old_key} → {migration.new_key} (v{migration.version})")
        print(f"    {migration.description}")
    print("\n✅ Test 3 PASSED")

    # Test 4: Check for legacy keys
    print("\n\nTest 4: Check for legacy keys in config")
    print("-" * 60)
    test_config = {
        "Voice.auto_join_timeout": 400,
        "System.token": "abc123"
    }
    legacy_keys = manager.check_for_legacy_keys(test_config)
    print(f"Config: {json.dumps(test_config, indent=2)}")
    print(f"Legacy keys found: {legacy_keys}")
    assert "Voice.auto_join_timeout" in legacy_keys, "Should detect legacy key"
    print("\n✅ Test 4 PASSED")

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_migration()
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
