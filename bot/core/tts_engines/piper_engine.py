"""
Piper TTS engine (local neural TTS).

Uses Piper for high-quality offline text-to-speech.
Quality: High (8/10) - Neural TTS, local
Speed: Fast inference
Size: Small models (10-50MB)
"""

import asyncio
import tempfile
import subprocess
import os
from typing import Optional, List, Dict, Any
from pathlib import Path
from .base import TTSEngine, logger

try:
    # Piper is typically installed as a binary, not a Python package
    # We'll check if it's available in PATH
    result = subprocess.run(
        ["piper", "--version"],
        capture_output=True,
        text=True,
        timeout=2
    )
    PIPER_AVAILABLE = result.returncode == 0
except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
    PIPER_AVAILABLE = False
    logger.warning("Piper TTS not found in PATH. Install from: https://github.com/rhasspy/piper")


class PiperEngine(TTSEngine):
    """Piper TTS-based engine."""

    # Common high-quality voices (model names)
    COMMON_VOICES = {
        "en_US-lessac-medium": "English (US) - Lessac (Medium)",
        "en_US-amy-medium": "English (US) - Amy (Medium)",
        "en_GB-alba-medium": "English (GB) - Alba (Medium)",
        "en_GB-danny-low": "English (GB) - Danny (Low)",
    }

    def __init__(self, bot):
        super().__init__(bot)

        if not PIPER_AVAILABLE:
            raise ImportError("Piper TTS is not available in PATH")

        # Model directory (will be created if it doesn't exist)
        self.model_dir = Path("data/tts/piper/models")
        self.model_dir.mkdir(parents=True, exist_ok=True)

        logger.info("PiperEngine initialized")

    async def generate_audio(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        volume: float = 1.0,
        guild_id: Optional[int] = None,
        **kwargs
    ) -> str:
        """Generate TTS audio using Piper."""
        # Get default voice if not provided
        if not voice:
            voice = self.get_default_voice(guild_id) or "en_US-lessac-medium"

        # Find model file
        model_path = self.model_dir / f"{voice}.onnx"

        if not model_path.exists():
            logger.warning(f"Piper model not found: {model_path}")
            logger.info(f"Download from: https://github.com/rhasspy/piper/releases/")
            raise FileNotFoundError(
                f"Piper model not found: {voice}. "
                f"Download from https://github.com/rhasspy/piper/releases/ "
                f"and place in {self.model_dir}"
            )

        # Create temp output file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_file.close()

        try:
            # Piper command: echo "text" | piper --model model.onnx --output_file output.wav
            # Rate control via --length-scale (1.0 = normal, <1 = faster, >1 = slower)
            length_scale = 1.0
            if rate:
                # Convert WPM to length scale (roughly)
                # 150 wpm = 1.0, 200 wpm = 0.75, 100 wpm = 1.5
                length_scale = 150 / rate

            cmd = [
                "piper",
                "--model", str(model_path),
                "--output_file", temp_file.name,
                "--length_scale", str(length_scale)
            ]

            # Run Piper
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate(input=text.encode())

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Piper TTS failed: {error_msg}")
                raise RuntimeError(f"Piper TTS failed: {error_msg}")

            logger.info(f"[Guild {guild_id}] Piper TTS: Generated audio with voice {voice}")
            return temp_file.name

        except Exception as e:
            logger.error(f"Piper TTS generation failed: {e}", exc_info=True)
            # Clean up temp file on error
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            raise

    async def list_voices(self) -> List[Dict[str, Any]]:
        """List available Piper voices (models in directory)."""
        voices = []

        # List downloaded models
        if self.model_dir.exists():
            for model_file in self.model_dir.glob("*.onnx"):
                voice_id = model_file.stem
                voice_name = self.COMMON_VOICES.get(voice_id, voice_id)

                # Extract language from voice ID (e.g., "en_US-lessac-medium" -> "en-US")
                lang = voice_id.split("-")[0].replace("_", "-") if "-" in voice_id else "unknown"

                voices.append({
                    "id": voice_id,
                    "name": voice_name,
                    "language": lang,
                    "gender": "unknown"
                })

        # If no models found, return the common voices list (user needs to download)
        if not voices:
            for voice_id, voice_name in self.COMMON_VOICES.items():
                lang = voice_id.split("-")[0].replace("_", "-")
                voices.append({
                    "id": voice_id,
                    "name": f"{voice_name} (not downloaded)",
                    "language": lang,
                    "gender": "unknown"
                })

        return voices

    def get_default_voice(self, guild_id: Optional[int] = None) -> Optional[str]:
        """Get default voice from config."""
        if guild_id and hasattr(self.bot, 'config_manager'):
            default = self.bot.config_manager.get("TTS", "tts_voice_piper", guild_id)
            if default:
                return default
        return "en_US-lessac-medium"
