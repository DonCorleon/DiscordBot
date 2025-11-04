"""
Bot version information.

Semantic versioning: MAJOR.MINOR.PATCH
- MAJOR: Incompatible API changes
- MINOR: Backwards-compatible functionality additions
- PATCH: Backwards-compatible bug fixes
"""

__version__ = "1.0.1"
__version_info__ = (1, 0, 1)

# Version history
VERSION_HISTORY = {
    "1.0.1": "Bug fixes: Prevent double auto-disconnect trigger, reduce transcription logging verbosity, prevent Whisper empty audio crashes",
    "1.0.0": "Initial version tracking - Added config migration system for auto_join_timeout → auto_disconnect_timeout"
}


def get_version() -> str:
    """Get the current bot version string."""
    return __version__


def get_version_info() -> tuple:
    """Get the current bot version as a tuple of integers."""
    return __version_info__
