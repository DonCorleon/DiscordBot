# Current Work: Speech Engine Unification

**Branch:** `master`
**Last Updated:** 2025-11-04
**Status:** ✅ Speech engines unified with Vosk's buffering pattern

---

## 📍 Current Focus

**Status**: Speech engine refactoring completed

**Goal**: Unified buffering implementation across all speech engines (Vosk, Whisper, faster-whisper) using Vosk's proven periodic processing pattern.

**Latest**: All three speech engines now use identical buffering logic with unified configuration settings.

---

## 🎯 Completed Work (Current Session)

### ✅ 1. Speech Engine Buffering Unification (Commits: fe48d14, 0018fd0)

**Problem**:
- Each speech engine had different buffering implementations
- Whisper and faster-whisper used per-user resilient loops (complex, error-prone)
- Different config field names across engines caused confusion
- faster-whisper was very laggy due to missing config fields

**Solution**:
Applied Vosk's proven buffering pattern to all engines while maintaining proper inheritance:
- **VoskSink**: Uses `voice_recv.AudioSink` - left completely untouched ✅
- **WhisperSink**: Uses `voice_recv.BasicSink` - refactored to use Vosk pattern
- **FasterWhisperSink**: Uses `voice_recv.BasicSink` - refactored to use Vosk pattern

**Key Changes**:
1. **Periodic Processing Pattern**:
   - Single background task per sink checks all users periodically
   - Processes audio chunks at regular intervals (default 4.0s)
   - Chunk overlap prevents missing words (default 0.5s)
   - Thread-safe buffer access with `threading.Lock`

2. **Correct Audio Handling**:
   - Fixed SAMPLE_RATE: 96000 → 48000 (Discord's actual rate)
   - Store raw PCM bytes (not pre-converted floats)
   - Use `member.id` for buffer keys (not `member.name`)
   - Process remaining audio when user stops speaking

3. **Unified Configuration** (commit 0018fd0):
   - Renamed: `vosk_chunk_duration` → `speech_chunk_duration`
   - Renamed: `vosk_chunk_overlap` → `speech_chunk_overlap`
   - Renamed: `vosk_processing_interval` → `speech_processing_interval`
   - Category: "Audio/Speech Recognition" (shared by all engines)
   - All engines now read same config fields

**Files Modified**:
- `bot/core/audio/speech_engines/whisper.py` - Applied Vosk pattern
- `bot/core/audio/speech_engines/faster_whisper.py` - Applied Vosk pattern
- `bot/core/audio/speech_engines/config.py` - Renamed fields to speech_*
- `bot/core/audio/speech_engines/vosk.py` - Updated to use speech_* fields

**Benefits**:
- ✅ Consistent buffering behavior across all engines
- ✅ Same proven low-latency pattern that works in Vosk
- ✅ Proper chunk overlap prevents missing words
- ✅ Thread-safe operations
- ✅ Single source of truth for configuration
- ✅ Fixed faster-whisper lag issues

---

## 🔄 Recent Commits

```
0018fd0 refactor: rename vosk_* config fields to speech_* for all engines
fe48d14 refactor: apply Vosk's buffering pattern to Whisper and FasterWhisper
d722528 Revert "refactor: unify speech engine buffering using BaseSpeechSink"
946d0fc refactor: unify speech engine buffering using BaseSpeechSink (REVERTED - broke VoskSink)
```

**Note on Reverted Commit**:
The first attempt (946d0fc) tried to create a shared `BaseSpeechSink` class but incorrectly:
- Forced VoskSink to use `BasicSink` instead of `AudioSink` (breaking change)
- Used wrong `super().__init__()` signature
- Broke PCM data reception completely
- Lesson: Never assume - verify inheritance requirements

---

## 📋 Speech Engine Architecture

### Buffering Pattern (Vosk's approach, now used by all):

```python
# 1. write() - Fast synchronous method (called for every packet)
def write(self, source, data):
    with self.buffer_lock:  # Thread-safe
        if member.id not in self.buffers:
            self.buffers[member.id] = deque()
            self.last_chunk_time[member.id] = time.time()
        self.buffers[member.id].append(data.pcm)  # Raw PCM bytes

# 2. Background task - Periodic processing
async def _process_buffers_loop(self):
    while not self._stop_processing:
        await asyncio.sleep(self.processing_interval)  # 0.1s

        with self.buffer_lock:
            for user_id, buffer in self.buffers.items():
                if time.time() - self.last_chunk_time[user_id] >= self.chunk_duration:
                    pcm_data = b''.join(buffer)
                    # Keep overlap for next chunk
                    overlap_bytes = int(SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH * self.chunk_overlap)
                    self.buffers[user_id] = deque([pcm_data[-overlap_bytes:]])
                    # Process in thread pool
                    self.vc.loop.run_in_executor(self.executor, self.transcribe_user, pcm_data, member)

# 3. on_voice_member_speaking_stop - Process remaining audio
def on_voice_member_speaking_stop(self, member):
    with self.buffer_lock:
        if member.id in self.buffers and self.buffers[member.id]:
            pcm_data = b''.join(self.buffers[member.id])
            self.buffers[member.id].clear()
            self.vc.loop.run_in_executor(self.executor, self.transcribe_user, pcm_data, member)
```

### Configuration (Unified):

```python
# bot/core/audio/speech_engines/config.py
speech_chunk_duration: float = 4.0       # Process audio every N seconds
speech_chunk_overlap: float = 0.5        # Overlap to prevent missing words
speech_processing_interval: float = 0.1  # Buffer check frequency
```

### Engine-Specific Transcription:

Each engine implements `transcribe_user(pcm_data: bytes, member: discord.Member)`:

**Vosk**:
- Convert stereo → mono int16
- Feed to KaldiRecognizer
- Call Result() then Reset()

**Whisper/FasterWhisper**:
- Convert stereo → mono float32
- Resample 48kHz → 16kHz
- Run model.transcribe()

---

## ✅ Previously Completed

### 7. Unified TTS Engine System
   - ✅ Created TTS engine abstraction layer
   - ✅ Three engines: Pyttsx3, Edge, Piper
   - ✅ Per-guild engine caching
   - ✅ Auto-switch on config changes
   - ✅ Committed (f0a3237)

### 6. Vosk KaldiRecognizer Reset Fix
   - ✅ Added Reset() after Result()
   - ✅ Fixes assertion failure crashes
   - ✅ Committed (62dc431)

### 5. Vosk Executor Shutdown Fix
   - ✅ Changed wait=False to wait=True
   - ✅ Prevents segfaults in native code
   - ✅ Committed (ebca5d4)

### 4. pyttsx3 SEGFAULT Fix
   - ✅ Removed engine.stop() calls
   - ✅ Committed (3c345cb)

### 3. Keepalive struct.error Fix
   - ✅ Check for valid ssrc before sending
   - ✅ Committed (03e6cc1)

### 2. TTS Dynamic Voice System
   - ✅ Cross-platform voice discovery
   - ✅ tts_default_voice config field
   - ✅ Fixed tuple choice validation
   - ✅ Committed

### 1. OpusError Monkey Patch
   - ✅ Catch and skip corrupted packets
   - ✅ Threshold-based reconnection
   - ✅ Committed

---

## 🔄 Session Recovery

**If session interrupted, resume with:**

```
Current branch: master
Status: Speech engine unification complete
Last Commit: 0018fd0

Recent Work:
- Unified all speech engines to use Vosk's buffering pattern
- Renamed config fields: vosk_* → speech_*
- Fixed faster-whisper lag issues
- All engines now share same timing configuration

Key Files:
- bot/core/audio/speech_engines/vosk.py (unchanged, uses AudioSink)
- bot/core/audio/speech_engines/whisper.py (refactored to Vosk pattern)
- bot/core/audio/speech_engines/faster_whisper.py (refactored to Vosk pattern)
- bot/core/audio/speech_engines/config.py (unified speech_* fields)

Important Lessons:
- VoskSink uses AudioSink, others use BasicSink - DO NOT change base classes
- Always verify inheritance requirements before refactoring
- Apply patterns, not forced abstractions
```

---

## 📝 Key Architecture Notes

### Speech Engine Design Principles:

1. **Inheritance Matters**:
   - VoskSink MUST use `voice_recv.AudioSink`
   - WhisperSink/FasterWhisperSink MUST use `voice_recv.BasicSink`
   - These are different classes with different behaviors - NOT interchangeable

2. **Buffering Pattern**:
   - Use Vosk's proven periodic processing approach
   - Single background task per sink (not per-user)
   - Thread-safe buffer operations with `threading.Lock`
   - Process remaining audio on speaking stop

3. **Configuration**:
   - Shared timing settings: `speech_*` prefix
   - Engine-specific settings: `<engine>_*` prefix
   - All in category "Audio/Speech Recognition"

4. **Audio Format**:
   - Discord sends: 48kHz stereo int16 PCM
   - Vosk expects: 48kHz mono int16
   - Whisper expects: 16kHz mono float32
   - Always store raw PCM, convert in transcription

---

**Document Version**: 3.0
**Last Updated By**: Claude (2025-11-04)
**Next Review**: After production testing of unified speech engines
