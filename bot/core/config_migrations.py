"""
Configuration migration system for handling renamed/moved settings.

This module provides a framework for migrating legacy configuration keys
to their new equivalents, ensuring backward compatibility across versions.
"""

import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ConfigMigration:
    """Represents a single configuration migration."""
    old_key: str
    new_key: str
    version: str
    description: str
    transform: Optional[Callable[[Any], Any]] = None  # Optional value transformation


class ConfigMigrationManager:
    """Manages configuration migrations across versions."""

    def __init__(self):
        self.migrations: Dict[str, ConfigMigration] = {}
        self._register_migrations()

    def _register_migrations(self):
        """Register all known configuration migrations."""
        # Migration 1: auto_join_timeout → auto_disconnect_timeout
        self.register_migration(
            ConfigMigration(
                old_key="Voice.auto_join_timeout",
                new_key="Voice.auto_disconnect_timeout",
                version="1.0.0",
                description="Renamed auto_join_timeout to auto_disconnect_timeout for clarity"
            )
        )

    def register_migration(self, migration: ConfigMigration):
        """Register a single migration."""
        self.migrations[migration.old_key] = migration
        logger.debug(f"Registered migration: {migration.old_key} → {migration.new_key} (v{migration.version})")

    def migrate_config(self, config_data: Dict[str, Any]) -> tuple[Dict[str, Any], list[str]]:
        """
        Migrate configuration data from old keys to new keys.

        Args:
            config_data: Raw configuration dictionary loaded from JSON/database

        Returns:
            Tuple of (migrated_config_data, list_of_applied_migrations)
        """
        migrated = config_data.copy()
        applied_migrations = []

        for old_key, migration in self.migrations.items():
            # Check if old key exists in config
            if old_key in migrated:
                old_value = migrated[old_key]

                # Apply transformation if defined
                new_value = migration.transform(old_value) if migration.transform else old_value

                # Set new key
                migrated[migration.new_key] = new_value

                # Remove old key
                del migrated[old_key]

                # Log migration
                logger.info(
                    f"[Config Migration v{migration.version}] "
                    f"Migrated '{old_key}' → '{migration.new_key}': {old_value}"
                )

                applied_migrations.append(
                    f"{old_key} → {migration.new_key} (v{migration.version}): {migration.description}"
                )

        return migrated, applied_migrations

    def check_for_legacy_keys(self, config_data: Dict[str, Any]) -> list[str]:
        """
        Check if config contains any legacy keys that need migration.

        Args:
            config_data: Raw configuration dictionary

        Returns:
            List of legacy keys found
        """
        legacy_keys = []
        for old_key in self.migrations.keys():
            if old_key in config_data:
                legacy_keys.append(old_key)
        return legacy_keys


# Global migration manager instance
_migration_manager = ConfigMigrationManager()


def get_migration_manager() -> ConfigMigrationManager:
    """Get the global migration manager instance."""
    return _migration_manager


def migrate_config(config_data: Dict[str, Any]) -> tuple[Dict[str, Any], list[str]]:
    """
    Convenience function to migrate config data using the global manager.

    Args:
        config_data: Raw configuration dictionary

    Returns:
        Tuple of (migrated_config_data, list_of_applied_migrations)
    """
    return _migration_manager.migrate_config(config_data)
