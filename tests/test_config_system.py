"""
Unit tests for the new configuration system (Phase 1).

Tests:
- ConfigField validation (types, ranges, choices)
- ConfigManager hierarchy (default -> global -> guild)
- ConfigManager caching (O(1) lookups)
- ConfigManager save/load (nested JSON format)
- ConfigManager hot-reload
- Config proxy (Option C property access)
"""

import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from bot.core.config_system import (
    ConfigField,
    CogConfigSchema,
    ConfigManager,
    ConfigProxy,
)
from bot.core.config_base import ConfigBase, config_field


class TestConfigField(unittest.TestCase):
    """Test ConfigField validation."""

    def test_type_validation_int(self):
        """Test integer type validation."""
        field = ConfigField(
            name="test_int",
            type=int,
            default=10,
            description="Test integer",
            category="Test"
        )

        # Valid
        is_valid, error = field.validate(5)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

        # Invalid type (but convertible)
        is_valid, error = field.validate("10")
        self.assertTrue(is_valid)

        # Invalid type (not convertible)
        is_valid, error = field.validate("abc")
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    def test_type_validation_bool(self):
        """Test boolean type validation."""
        field = ConfigField(
            name="test_bool",
            type=bool,
            default=True,
            description="Test boolean",
            category="Test"
        )

        # Valid
        is_valid, error = field.validate(False)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_range_validation(self):
        """Test min/max range validation."""
        field = ConfigField(
            name="test_range",
            type=float,
            default=0.5,
            description="Test range",
            category="Test",
            min_value=0.0,
            max_value=1.0
        )

        # Valid
        is_valid, error = field.validate(0.5)
        self.assertTrue(is_valid)

        # Below minimum
        is_valid, error = field.validate(-0.1)
        self.assertFalse(is_valid)
        self.assertIn("below minimum", error)

        # Above maximum
        is_valid, error = field.validate(1.5)
        self.assertFalse(is_valid)
        self.assertIn("above maximum", error)

    def test_choices_validation(self):
        """Test choices validation."""
        field = ConfigField(
            name="test_choices",
            type=str,
            default="option1",
            description="Test choices",
            category="Test",
            choices=["option1", "option2", "option3"]
        )

        # Valid
        is_valid, error = field.validate("option2")
        self.assertTrue(is_valid)

        # Invalid choice
        is_valid, error = field.validate("option4")
        self.assertFalse(is_valid)
        self.assertIn("not in valid choices", error)


class TestCogConfigSchema(unittest.TestCase):
    """Test CogConfigSchema creation from dataclass."""

    def test_from_dataclass(self):
        """Test schema extraction from dataclass."""

        @dataclass
        class TestConfig(ConfigBase):
            volume: float = config_field(
                default=0.5,
                description="Volume level",
                category="Audio",
                guild_override=True,
                min_value=0.0,
                max_value=1.0
            )

            enabled: bool = config_field(
                default=True,
                description="Enable feature",
                category="General"
            )

        schema = CogConfigSchema.from_dataclass("TestCog", TestConfig)

        self.assertEqual(schema.cog_name, "TestCog")
        self.assertEqual(len(schema.fields), 2)

        # Check volume field
        self.assertIn("volume", schema.fields)
        volume_field = schema.fields["volume"]
        self.assertEqual(volume_field.type, float)
        self.assertEqual(volume_field.default, 0.5)
        self.assertEqual(volume_field.category, "Audio")
        self.assertTrue(volume_field.guild_override)
        self.assertEqual(volume_field.min_value, 0.0)
        self.assertEqual(volume_field.max_value, 1.0)

        # Check enabled field
        self.assertIn("enabled", schema.fields)
        enabled_field = schema.fields["enabled"]
        self.assertEqual(enabled_field.type, bool)
        self.assertEqual(enabled_field.default, True)
        self.assertFalse(enabled_field.guild_override)


class TestConfigManager(unittest.TestCase):
    """Test ConfigManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = ConfigManager()

        # Create a test schema
        @dataclass
        class TestConfig(ConfigBase):
            volume: float = config_field(
                default=0.5,
                description="Volume level",
                category="Audio",
                guild_override=True,
                min_value=0.0,
                max_value=1.0
            )

            enabled: bool = config_field(
                default=True,
                description="Enable feature",
                category="General",
                guild_override=True
            )

            admin_setting: str = config_field(
                default="default_value",
                description="Admin setting",
                category="Admin",
                guild_override=False,  # Global only
                admin_only=True
            )

        self.schema = CogConfigSchema.from_dataclass("TestCog", TestConfig)
        self.manager.register_schema("TestCog", self.schema)

    def test_register_schema(self):
        """Test schema registration."""
        self.assertIn("TestCog", self.manager.schemas)
        self.assertEqual(len(self.manager.schemas["TestCog"].fields), 3)

    def test_get_default_value(self):
        """Test getting default value (no overrides)."""
        value = self.manager.get("TestCog", "volume")
        self.assertEqual(value, 0.5)

        value = self.manager.get("TestCog", "enabled")
        self.assertEqual(value, True)

    def test_hierarchy_global_override(self):
        """Test hierarchy: global override takes precedence over default."""
        # Set global override
        success, error = self.manager.set("TestCog", "volume", 0.8)
        self.assertTrue(success)
        self.assertIsNone(error)

        # Get value (should return global override)
        value = self.manager.get("TestCog", "volume")
        self.assertEqual(value, 0.8)

    def test_hierarchy_guild_override(self):
        """Test hierarchy: guild override takes precedence over global."""
        # Set global override
        self.manager.set("TestCog", "volume", 0.8)

        # Set guild override
        success, error = self.manager.set("TestCog", "volume", 0.3, guild_id=123)
        self.assertTrue(success)

        # Get value for guild (should return guild override)
        value = self.manager.get("TestCog", "volume", guild_id=123)
        self.assertEqual(value, 0.3)

        # Get value without guild (should return global override)
        value = self.manager.get("TestCog", "volume")
        self.assertEqual(value, 0.8)

        # Get value for different guild (should return global override)
        value = self.manager.get("TestCog", "volume", guild_id=456)
        self.assertEqual(value, 0.8)

    def test_validation_on_set(self):
        """Test validation when setting values."""
        # Valid value
        success, error = self.manager.set("TestCog", "volume", 0.7)
        self.assertTrue(success)
        self.assertIsNone(error)

        # Invalid value (out of range)
        success, error = self.manager.set("TestCog", "volume", 1.5)
        self.assertFalse(success)
        self.assertIsNotNone(error)

        # Value should not have changed
        value = self.manager.get("TestCog", "volume")
        self.assertEqual(value, 0.7)

    def test_guild_override_not_allowed(self):
        """Test that non-guild-overridable settings reject guild overrides."""
        success, error = self.manager.set("TestCog", "admin_setting", "new_value", guild_id=123)
        self.assertFalse(success)
        self.assertIn("does not support guild overrides", error)

    def test_caching(self):
        """Test that caching works (O(1) lookups)."""
        # First access (not cached)
        value1 = self.manager.get("TestCog", "volume")

        # Check cache
        cache_key = ("TestCog", "volume", None)
        self.assertIn(cache_key, self.manager._cache)
        self.assertEqual(self.manager._cache[cache_key], 0.5)

        # Second access (should use cache)
        value2 = self.manager.get("TestCog", "volume")
        self.assertEqual(value1, value2)

    def test_cache_invalidation(self):
        """Test that cache is invalidated on set."""
        # Get value (caches it)
        value = self.manager.get("TestCog", "volume")
        self.assertEqual(value, 0.5)

        # Set new value (should invalidate cache)
        self.manager.set("TestCog", "volume", 0.8)

        # Get value again (should return new value)
        value = self.manager.get("TestCog", "volume")
        self.assertEqual(value, 0.8)

    def test_config_proxy(self):
        """Test ConfigProxy (Option C property access)."""
        # Set some values
        self.manager.set("TestCog", "volume", 0.7)
        self.manager.set("TestCog", "enabled", False)

        # Get proxy
        cfg = self.manager.for_guild("TestCog")

        # Access via properties
        self.assertEqual(cfg.volume, 0.7)
        self.assertEqual(cfg.enabled, False)

        # Test with guild
        self.manager.set("TestCog", "volume", 0.3, guild_id=123)
        cfg_guild = self.manager.for_guild("TestCog", guild_id=123)
        self.assertEqual(cfg_guild.volume, 0.3)

    def test_save_and_load_global(self):
        """Test saving and loading global config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Override config paths
            from bot.core import config_system
            original_base = config_system.BASE_CONFIG_FILE
            config_system.BASE_CONFIG_FILE = Path(tmpdir) / "base_config.json"

            try:
                # Set some global values
                self.manager.set("TestCog", "volume", 0.8)
                self.manager.set("TestCog", "enabled", False)

                # Save
                self.manager.save()

                # Check file exists and has correct format
                self.assertTrue(config_system.BASE_CONFIG_FILE.exists())

                with open(config_system.BASE_CONFIG_FILE, 'r') as f:
                    data = json.load(f)

                # Should be nested format
                self.assertIn("TestCog", data)
                self.assertEqual(data["TestCog"]["volume"], 0.8)
                self.assertEqual(data["TestCog"]["enabled"], False)

                # Create new manager and load
                manager2 = ConfigManager()
                manager2.register_schema("TestCog", self.schema)

                # Values should be loaded
                self.assertEqual(manager2.get("TestCog", "volume"), 0.8)
                self.assertEqual(manager2.get("TestCog", "enabled"), False)

            finally:
                config_system.BASE_CONFIG_FILE = original_base

    def test_save_and_load_guild(self):
        """Test saving and loading guild configs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Override config paths
            from bot.core import config_system
            original_guilds = config_system.GUILDS_CONFIG_DIR
            config_system.GUILDS_CONFIG_DIR = Path(tmpdir) / "guilds"
            config_system.GUILDS_CONFIG_DIR.mkdir()

            try:
                # Set guild-specific values
                self.manager.set("TestCog", "volume", 0.3, guild_id=123)
                self.manager.set("TestCog", "enabled", False, guild_id=123)
                self.manager.set("TestCog", "volume", 0.9, guild_id=456)

                # Save
                self.manager.save()

                # Check guild files exist
                guild_123_file = config_system.GUILDS_CONFIG_DIR / "123.json"
                guild_456_file = config_system.GUILDS_CONFIG_DIR / "456.json"

                self.assertTrue(guild_123_file.exists())
                self.assertTrue(guild_456_file.exists())

                # Check format
                with open(guild_123_file, 'r') as f:
                    data = json.load(f)

                self.assertIn("TestCog", data)
                self.assertEqual(data["TestCog"]["volume"], 0.3)
                self.assertEqual(data["TestCog"]["enabled"], False)

                # Create new manager and load
                manager2 = ConfigManager()
                manager2.register_schema("TestCog", self.schema)

                # Values should be loaded
                self.assertEqual(manager2.get("TestCog", "volume", guild_id=123), 0.3)
                self.assertEqual(manager2.get("TestCog", "enabled", guild_id=123), False)
                self.assertEqual(manager2.get("TestCog", "volume", guild_id=456), 0.9)

            finally:
                config_system.GUILDS_CONFIG_DIR = original_guilds

    def test_hot_reload(self):
        """Test hot-reload functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Override config paths
            from bot.core import config_system
            original_base = config_system.BASE_CONFIG_FILE
            config_system.BASE_CONFIG_FILE = Path(tmpdir) / "base_config.json"

            try:
                # Set initial value
                self.manager.set("TestCog", "volume", 0.5)
                self.manager.save()

                # Manually edit config file
                with open(config_system.BASE_CONFIG_FILE, 'w') as f:
                    json.dump({"TestCog": {"volume": 0.9}}, f)

                # Reload
                self.manager.reload()

                # Value should be updated
                self.assertEqual(self.manager.get("TestCog", "volume"), 0.9)

            finally:
                config_system.BASE_CONFIG_FILE = original_base


if __name__ == "__main__":
    unittest.main()
