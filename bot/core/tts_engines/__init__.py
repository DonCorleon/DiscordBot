"""
TTS Engine abstraction system.

Provides pluggable TTS engines similar to the speech recognition system.
Engines: pyttsx3 (local), edge-tts (cloud), piper (neural local)
"""

from .base import TTSEngine
from .factory import create_tts_engine

__all__ = ["TTSEngine", "create_tts_engine"]
