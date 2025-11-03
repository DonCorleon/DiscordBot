# Current Work: Voice Connection Stability Fixes

**Branch:** `master`
**Last Updated:** 2025-11-03
**Status:** ✅ OpusError handling and keepalive fixes implemented

---

## 📍 Current Focus

**Status**: Fixed five critical issues:
1. ✅ OpusError crashes (COMPLETED - monkey patch working)
2. ✅ Keepalive struct.error (COMPLETED - added connection ready check)
3. ✅ pyttsx3 SEGFAULT (COMPLETED - removed engine.stop() calls)
4. ✅ Vosk executor shutdown (COMPLETED - defensive fix)
5. ✅ **Vosk KaldiRecognizer SEGFAULT** (COMPLETED - Reset() after Result()) **← THE REAL FIX**
6. ⚠️ OpusError reconnection timeout (OBSERVED - needs investigation)

**Goal**: Ensure stable voice connections and eliminate all crashes.

**Latest**: Vosk crash was caused by not resetting KaldiRecognizer after Result() call.
Internal queue state was corrupting, causing assertion failure in Vosk C++ code.

---

## 🔍 Problem Analysis

**Error Observed:**
```
[2025-11-03 18:22:52] [ERROR] discord.ext.voice_recv.router: Error in <PacketRouter> loop
discord.opus.OpusError: corrupted stream
```

**Root Cause:**
- `discord-ext-voice-recv` library crashes when Discord audio packets are corrupted/lost
- OpusError is raised in `discord.opus.Decoder.decode()` during packet decoding
- Exception bubbles up through `PacketDecoder._decode_packet()` → `PacketRouter._do_run()`
- **Entire PacketRouter thread dies** → Speech recognition stops completely
- User must manually restart listening with `~start` command

**Impact:** Complete loss of speech recognition until manual intervention.

---

## 💡 Proposed Solution

### Approach: Monkey Patch + Threshold-Based Reconnection

**Primary Behavior:**
- Patch `PacketDecoder._decode_packet()` to catch OpusError
- Skip bad packets (return None for pcm)
- Continue with existing connection (no disruption to users)

**Threshold-Based Reconnection:**
- Track OpusErrors per guild with timestamps
- When X errors occur within Y seconds: auto-reconnect
- Configurable thresholds via ConfigManager

**Logging:**
- WARNING level for visibility
- Rate-limited (log every Nth error) to prevent spam
- Include error count and window stats

### User Requirements (from clarification):
1. ✅ Continue with existing connection (skip bad packets)
2. ✅ Add threshold-based reconnection with ConfigManager vars
3. ✅ WARNING level with rate limiting (mixture of approaches)

---

## 📋 Implementation Plan

### 1. Config Fields (VoiceConfig)
Add to `bot/cogs/audio/voice_speech.py` (~line 79-103):
```python
opus_error_threshold: int = 5  # Errors before reconnecting
opus_error_window: int = 10    # Time window in seconds
opus_error_log_interval: int = 5  # Log every Nth error
```

### 2. Monkey Patch
Add to `bot/cogs/audio/voice_speech.py` (~line 137-220):
- Patch `discord.ext.voice_recv.opus.PacketDecoder._decode_packet()`
- Wrap `self._decoder.decode()` in try/except OpusError
- On error: call `VoiceSpeechCog._handle_opus_error()`, return None
- Continue with original data structure return

### 3. Error Tracking
Add to `VoiceSpeechCog.__init__` (~line 176):
```python
self.opus_error_tracker = {}  # {guild_id: {"timestamps": deque, "logged_count": int}}
```

### 4. Error Handler Method
Add to `VoiceSpeechCog` (~line 442-510):
- `_handle_opus_error(guild_id, error, packet)`:
  - Track error timestamp in sliding window
  - Rate-limited logging (every Nth error)
  - Check threshold: if exceeded, schedule reconnection task
  - Clear tracker to prevent duplicate reconnections

### 5. Reconnection Method
Add to `VoiceSpeechCog` (~line 512-575):
- `_reconnect_voice_after_opus_errors(guild_id)`:
  - Stop listening, disconnect, wait 1.5s
  - Reconnect to same channel
  - Restart speech listener
  - Clear error tracker (fresh start)

### 6. Cleanup
Update `cog_unload()` (~line 439):
- Clear `self.opus_error_tracker`

---

## 📁 Files to Modify

**Single File:**
- `bot/cogs/audio/voice_speech.py`
  - Add 3 config fields
  - Add monkey patch function
  - Add error tracker to __init__
  - Add 2 new methods (_handle_opus_error, _reconnect_voice_after_opus_errors)
  - Update cog_unload

**No other files need changes** - self-contained fix.

---

## ✅ 7. Unified TTS Engine System (Committed)
   - ✅ Created TTS engine abstraction layer (bot/core/tts_engines/)
   - ✅ Base TTSEngine class with generate_audio(), list_voices(), get_default_voice()
   - ✅ Three engine implementations:
     - Pyttsx3Engine: Local TTS (espeak/SAPI)
     - EdgeEngine: Microsoft Edge TTS (cloud neural)
     - PiperEngine: Piper TTS (local neural, high quality)
   - ✅ Added tts_engine config field to switch engines via web UI
   - ✅ Refactored tts.py to use engine system with per-guild caching
   - ✅ Updated ~voices command to show engine-specific voices
   - ✅ Engine auto-switches when config changes
   - ✅ Fallback to pyttsx3 if selected engine unavailable
   - ✅ Committed (commit: f0a3237)

   **Note**: edge_tts.py cog still exists with separate `~edge` commands. It can be removed/deprecated now that functionality is merged into main TTS system.

## ✅ Previously Completed (Earlier Session)

### 1. Version Tracking System

**Created `bot/version.py`**:
- Semantic versioning (MAJOR.MINOR.PATCH)
- Current version: 1.0.0
- `get_version()` and `get_version_info()` functions
- `VERSION_HISTORY` dict for change descriptions
- Version logged on bot startup in `bot/main.py:303-308`

### 2. Config Migration System

**Created `bot/core/config_migrations.py`**:
- `ConfigMigration` dataclass for representing migrations
- `ConfigMigrationManager` class to manage all migrations
- Automatic detection and application of legacy config keys
- Full logging of applied migrations

**Integrated into `bot/core/config_system.py`**:
- Migrations applied automatically on global config load
- Migrations applied automatically on guild config load
- Migrated configs saved to disk immediately
- Helper methods: `_flatten_config()`, `_unflatten_config()`

**First Migration**: `auto_join_timeout` → `auto_disconnect_timeout`
- Old name was misleading (controls disconnect, not join timeout)
- Automatic backward compatibility for old configs
- Updated all code references and documentation

### 3. Removed Duplicate/Dead Config Settings (4 total)

**❌ `ducking_transition_ms` (SoundboardConfig)**:
- Location: `bot/cogs/audio/soundboard.py`
- Reason: Dead code - never used anywhere
- System uses `audio_duck_transition_ms` from SystemConfig instead

**❌ `sound_playback_timeout` (SoundboardConfig)**:
- Location: `bot/cogs/audio/soundboard.py`
- Reason: Duplicate - only VoiceConfig version was used
- Kept VoiceConfig version

**❌ `sound_queue_warning_size` (SoundboardConfig)**:
- Location: `bot/cogs/audio/soundboard.py`
- Reason: Dead code - never used anywhere
- Kept VoiceConfig version (runtime warnings) and SystemConfig version (health monitoring) - they serve different purposes

**❌ `keepalive_interval` (VoiceConfig)**:
- Location: `bot/cogs/audio/voice_speech.py`
- Reason: Duplicate - consolidated to SystemConfig
- Updated `voice_speech.py:635` to use SystemConfig version
- More permissive max (300s vs 120s)

### 4. Reorganized Config Categories (9 settings)

**Auto-Disconnect Feature** - Now grouped together:
```
enable_auto_disconnect (System) → "Audio/Voice Channels/Auto-Disconnect"
auto_disconnect_timeout (Voice) → "Audio/Voice Channels/Auto-Disconnect"
```

**Auto-Join Feature**:
```
auto_join_enabled (Voice) → "Audio/Voice Channels/Auto-Join"
```

**Speech Recognition** - Hierarchical structure:
```
enable_speech_recognition (System) → "Audio/Speech Recognition" (master toggle)
engine (Speech) → "Audio/Speech Recognition" (engine selector)
vosk_model_path (Speech) → "Audio/Speech Recognition/Vosk"
whisper_model (Speech) → "Audio/Speech Recognition/Whisper"
whisper_buffer_duration (Speech) → "Audio/Speech Recognition/Whisper"
whisper_debounce_seconds (Speech) → "Audio/Speech Recognition/Whisper"
```

**Voice Channels**:
```
keepalive_interval (System) → "Audio/Voice Channels"
```

---

## 📦 Files Changed (This Session)

### Created Files:
- `bot/version.py` - Version tracking system
- `bot/core/config_migrations.py` - Config migration framework
- `test_migration.py` - Test script for migration system (all tests pass ✅)
- `docs/VERSION_AND_MIGRATION_SYSTEM.md` - Version/migration documentation
- `docs/CONFIG_CLEANUP_AND_REORGANIZATION.md` - Cleanup documentation

### Modified Files:
- `bot/main.py` - Added version logging on startup
- `bot/core/config_system.py` - Integrated migration system, added flatten/unflatten helpers
- `bot/cogs/audio/soundboard.py` - Removed 3 dead/duplicate settings
- `bot/cogs/audio/voice_speech.py` - Removed 1 duplicate, updated categories, updated keepalive usage, renamed auto_join_timeout
- `bot/core/system_config.py` - Updated 3 categories
- `bot/core/audio/speech_engines/config.py` - Organized engine-specific settings into sub-categories
- `docs/CONFIG_SYSTEM.md` - Updated field name
- `docs/CONFIG_CATEGORY_MIGRATION.md` - Noted legacy name
- `docs/config_inventory.json` - Updated with legacy_name

---

## 🔄 Recent Commits

From `backup-2025-11-01-current` branch:
```
c40cb74 fix: restore write() error handling to prevent sink crashes on reconnection
f276c9a fix: remove unnecessary PyAudio initialization causing ALSA/JACK spam
224eea1 fix: remove write() error handling that was hiding real exceptions
851c08e fix: add timeout to PacketRouter wait to prevent infinite blocking
bac70b8 fix: catch JSONDecodeError from speech recognition text
```

---

## 🔄 Completed Tasks (Current Session)

### ✅ 1. OpusError Monkey Patch (Committed)
   - ✅ Added 3 config fields to VoiceConfig (lines 115-144)
   - ✅ Added monkey patch for PacketDecoder._decode_packet() (lines 169-229)
   - ✅ Added error tracker to VoiceSpeechCog.__init__ (line 272)
   - ✅ Added _handle_opus_error() method (lines 912-958)
   - ✅ Added _reconnect_voice_after_opus_errors() method (lines 960-1020)
   - ✅ Updated cog_unload() cleanup (line 536)
   - ✅ Fixed TypeError in monkey patch return value
   - ✅ Committed and pushed

### ✅ 2. TTS Dynamic Voice System (Committed)
   - ✅ Removed hardcoded Windows-only voices
   - ✅ Added _discover_voices() for cross-platform compatibility
   - ✅ Added tts_default_voice config field
   - ✅ Updated voice selection to use discovered voices
   - ✅ Fixed tuple choice validation in config system
   - ✅ Fixed web UI dropdown handling for tuple choices
   - ✅ Committed and pushed

### ✅ 3. Keepalive struct.error Fix (Committed)
   - ✅ Added check for MISSING/invalid ssrc before sending packets
   - ✅ Prevents struct.error when connection not fully established
   - ✅ Added debug logging for skipped keepalives
   - ✅ Committed (commit: 03e6cc1)

### ✅ 4. pyttsx3 SEGFAULT Fix (Committed)
   - ✅ Removed engine.stop() from _discover_voices()
   - ✅ Removed engine.stop() from generate_tts()
   - ✅ Added comments explaining why stop() causes segfaults
   - ✅ Prevents crashes on bot startup and TTS usage
   - ✅ Committed (commit: 3c345cb)

### ✅ 5. Vosk ThreadPoolExecutor SEGFAULT Fix (Committed)
   - ✅ Changed executor.shutdown(wait=False) to wait=True
   - ✅ Prevents forceful termination of Vosk native code
   - ✅ Committed (commit: ebca5d4)
   - ⚠️ NOTE: This was a good defensive fix but NOT the root cause

### ✅ 6. Vosk KaldiRecognizer Reset SEGFAULT Fix (Committed) **THE REAL FIX**
   - ✅ Added recognizer.Reset() after recognizer.Result()
   - ✅ Added reset on exception to clear corrupted state
   - ✅ Fixes Vosk assertion failure: queue_.empty()
   - ✅ Root cause: Reusing recognizer without reset corrupts internal state
   - ✅ Committed (commit: 62dc431)
   - **THIS IS THE ACTUAL FIX FOR THE VOSK CRASHES**

## ⚠️ Known Issues

### 1. OpusError Reconnection Timeout
**Status**: Observed in production logs, not yet investigated

**Error**:
```
TimeoutError during channel.connect() in _reconnect_voice_after_opus_errors()
```

**Impact**: When OpusError threshold is exceeded, auto-reconnect times out instead of successfully reconnecting.

**Potential Causes**:
- Discord voice server not responding
- Bot trying to reconnect too quickly after disconnect
- May need longer timeout or delay before reconnect

**Next Steps**:
- Add longer delay before reconnect attempt (currently 1.5s)
- Increase connect timeout
- Add retry logic with exponential backoff
- Consider whether auto-reconnect is needed (OpusError skip might be sufficient)

---

## 📝 Key Improvements

### Benefits:
- ✅ **Version Tracking**: Bot version logged on startup for debugging
- ✅ **Backward Compatibility**: Old configs automatically migrated
- ✅ **Cleaner Codebase**: 4 fewer unused settings
- ✅ **Better Organization**: Related settings grouped together
- ✅ **Clearer UI**: Web dashboard shows logical groupings
- ✅ **Easier Configuration**: Users find related settings in one place
- ✅ **Maintainability**: Clear which settings affect which features

### New Category Structure:

**Audio/Voice Channels**:
- keepalive_interval
- Auto-Join (sub-category): auto_join_enabled
- Auto-Disconnect (sub-category): enable_auto_disconnect, auto_disconnect_timeout

**Audio/Speech Recognition**:
- enable_speech_recognition (master toggle)
- engine (engine selector)
- Vosk (sub-category): vosk_model_path
- Whisper (sub-category): whisper_model, whisper_buffer_duration, whisper_debounce_seconds
- Advanced (sub-category): voice_speech_phrase_time_limit, voice_speech_error_log_threshold, voice_speech_chunk_size

---

## 🔄 Session Recovery

**If session interrupted, resume with:**

```
Current branch: master
Bot Version: 1.0.0
Status: Planning OpusError monkey patch - ready to implement

Problem:
- OpusError: corrupted stream crashes PacketRouter thread
- Speech recognition stops completely until manual restart
- Occurs when Discord audio packets are corrupted/lost

Solution Plan:
1. Monkey patch PacketDecoder._decode_packet() to catch OpusError
2. Skip bad packets (return None) and continue connection
3. Track errors per guild with sliding window
4. Auto-reconnect when threshold exceeded (5 errors in 10 seconds)
5. Rate-limited WARNING logging (every 5th error)

Implementation Details:
- Single file change: bot/cogs/audio/voice_speech.py
- Add 3 config fields (opus_error_threshold, opus_error_window, opus_error_log_interval)
- Add monkey patch function (~line 137-220)
- Add error tracker to __init__ (~line 176)
- Add 2 methods: _handle_opus_error(), _reconnect_voice_after_opus_errors()
- Update cog_unload() for cleanup

User Requirements:
✅ Continue with existing connection (skip bad packets)
✅ Add threshold-based reconnection with ConfigManager
✅ WARNING level logging with rate limiting

Next Steps:
1. Implement the monkey patch and methods
2. Test compilation
3. Test with low threshold to verify reconnection
4. Commit when working
```

**Detailed Implementation Reference:**
See "Implementation Plan" section above for line-by-line code structure and placement.

---

**Document Version**: 2.0
**Last Updated By**: Claude (2025-11-03)
**Next Review**: After OpusError fix is implemented and tested
