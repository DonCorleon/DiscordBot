"""
Pluggable speech recognition engines.

Provides abstraction for swapping between different speech recognition
implementations (Vosk, Whisper, etc.) without changing voice connection logic.
"""

from .base import SpeechEngine
from .vosk import VoskEngine
from .whisper import WhisperEngine
from .faster_whisper import FasterWhisperEngine
from .dual_path_sink import DualPathSink
from .config import SpeechConfig
import logging

logger = logging.getLogger("discordbot.speech_engines")


def create_speech_engine(
    bot,
    callback,
    engine_type: str = "vosk",
    ducking_callback=None
) -> SpeechEngine:
    """
    Factory function to create speech recognition engines.

    Args:
        bot: Discord bot instance
        callback: Function called with (member, transcribed_text) when speech is recognized
        engine_type: Engine to use ("vosk", "whisper", or "faster-whisper")
        ducking_callback: Optional callback for audio ducking events (guild_id, member, is_speaking)

    Returns:
        SpeechEngine instance

    Raises:
        ValueError: If engine_type is unknown
    """

    if engine_type == "vosk":
        # Get Vosk config from bot's ConfigManager
        try:
            speech_cfg = bot.config_manager.for_guild("Speech")
            model_path = speech_cfg.vosk_model_path
        except Exception:
            # Fallback to defaults if config not available
            model_path = "data/speechrecognition/vosk"

        return VoskEngine(
            bot,
            callback,
            model_path=model_path,
            ducking_callback=ducking_callback
        )

    elif engine_type == "whisper":
        # Get Whisper config from bot's ConfigManager
        try:
            speech_cfg = bot.config_manager.for_guild("Speech")
            model_size = speech_cfg.whisper_model
            buffer_duration = speech_cfg.whisper_buffer_duration
            debounce_seconds = speech_cfg.whisper_debounce_seconds
        except Exception:
            # Fallback to defaults
            model_size = "tiny.en"
            buffer_duration = 3.0
            debounce_seconds = 1.0

        return WhisperEngine(
            bot,
            callback,
            model_size=model_size,
            buffer_duration=buffer_duration,
            debounce_seconds=debounce_seconds,
            ducking_callback=ducking_callback
        )

    elif engine_type == "faster-whisper":
        # Get faster-whisper config from bot's ConfigManager
        try:
            speech_cfg = bot.config_manager.for_guild("Speech")
            model_size = speech_cfg.faster_whisper_model
            device = speech_cfg.faster_whisper_device
            compute_type = speech_cfg.faster_whisper_compute_type
        except Exception:
            # Fallback to defaults
            model_size = "base"
            device = "cpu"
            compute_type = "int8"

        return FasterWhisperEngine(
            bot,
            callback,
            model_size=model_size,
            device=device,
            compute_type=compute_type,
            ducking_callback=ducking_callback
        )

    else:
        raise ValueError(
            f"Unknown speech engine: '{engine_type}'. "
            f"Valid options: 'vosk', 'whisper', 'faster-whisper'"
        )


def create_quality_model(speech_cfg):
    """
    Attempt to load a faster-whisper model for the quality transcription path.

    Returns:
        (model, config_dict) on success, (None, None) on any failure.
        All failures are logged as warnings and never raised.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.warning(
            "Quality path: faster-whisper not installed. "
            "Install with: pip install faster-whisper"
        )
        return None, None

    try:
        model_size = speech_cfg.quality_model
        device = speech_cfg.quality_device
        compute_type = speech_cfg.quality_compute_type

        logger.info(
            f"Quality path: loading faster-whisper model "
            f"(model={model_size}, device={device}, compute_type={compute_type})..."
        )

        model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type
        )

        config_dict = {
            "model": model_size,
            "device": device,
            "compute_type": compute_type,
            "beam_size": speech_cfg.quality_beam_size,
            "max_workers": speech_cfg.quality_max_workers,
        }

        logger.info(f"Quality path: model loaded successfully ({model_size})")
        return model, config_dict

    except Exception as e:
        logger.warning(f"Quality path: failed to load model: {e}", exc_info=True)
        return None, None


__all__ = [
    "SpeechEngine",
    "VoskEngine",
    "WhisperEngine",
    "FasterWhisperEngine",
    "DualPathSink",
    "SpeechConfig",
    "create_speech_engine",
    "create_quality_model",
]
