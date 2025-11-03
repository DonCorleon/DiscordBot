# Whisper Engine Implementation Reference

**Purpose:** Complete reference for implementing WhisperEngine based on user's working example

**Branch:** `feat-pluggable-speech-engines`
**Status:** Ready to implement - use this as reference for WhisperEngine.py

---

## User's Working Implementation

The user provided a complete working Whisper bot with the following key components:

### Key Architecture Components

**1. ResilientWhisperSink (Custom BasicSink)**
- Extends `voice_recv.BasicSink`
- Per-user audio buffering in dictionaries
- Background transcription tasks per user
- Resilient error handling with auto-restart

**2. Audio Processing Pipeline**
```
Discord Voice (96kHz PCM)
  → write() method captures per-user audio
  → Buffer in numpy arrays (rolling 3-second window)
  → Resample 96kHz → 16kHz for Whisper
  → Run Whisper in ThreadPoolExecutor (blocking call)
  → Callback with transcribed text
```

**3. Key Configuration**
```python
BUFFER_DURATION = 3          # Keep 3 seconds of audio
SAMPLE_RATE = 96000          # Discord's sample rate
TARGET_SR = 16000            # Whisper expects 16kHz
DEBOUNCE_SECONDS = 1         # Min time between transcriptions
model = whisper.load_model("tiny.en")
executor = ThreadPoolExecutor(max_workers=4)
```

---

## Critical Implementation Details

### 1. Audio Buffering (Per-User)

```python
class ResilientWhisperSink(voice_recv.BasicSink):
    def __init__(self, text_channel, vc):
        super().__init__(asyncio.Event())
        self.vc = vc
        self.buffers = {}                   # {user_name: [audio_chunks]}
        self.last_transcription = {}        # {user_name: timestamp}
        self.speaking_state = {}            # {user_name: bool}
        self.transcription_tasks = {}       # {user_name: Task}
        self.loop = asyncio.get_running_loop()

    def write(self, source, data):
        """Called for every audio packet from Discord"""
        if data.pcm is None:
            return

        member = self.vc.guild.get_member(getattr(data, "user_id", None))
        user_name = member.name if member else str(getattr(data, "user_id", data.source))

        # Initialize per-user state
        self.buffers.setdefault(user_name, [])
        self.last_transcription.setdefault(user_name, 0)

        # Convert PCM bytes to float32 numpy array
        pcm_float = np.frombuffer(data.pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if pcm_float.size == 0:
            return

        # Add to user's buffer
        self.buffers[user_name].append(pcm_float)

        # Start transcription task if not running
        if user_name not in self.transcription_tasks or self.transcription_tasks[user_name].done():
            self.transcription_tasks[user_name] = self.loop.create_task(
                self._resilient_transcribe(user_name)
            )
```

### 2. Resilient Transcription Loop

```python
async def _resilient_transcribe(self, user_name):
    """Background loop per user - keeps retrying on errors"""
    while True:
        chunks = self.buffers.get(user_name, [])
        if not chunks:
            await asyncio.sleep(1.0)
            continue

        try:
            # 30 second timeout per transcription attempt
            await asyncio.wait_for(self._transcribe_user(user_name), timeout=30)
        except asyncio.TimeoutError:
            logger.warning(f"Whisper transcription timeout for {user_name}, restarting task...")
        except Exception:
            logger.exception(f"Transcription loop crashed for {user_name}, restarting...")

        await asyncio.sleep(0.1)
```

### 3. Transcription with Rolling Buffer

```python
async def _transcribe_user(self, user_name):
    """Process audio buffer for one user"""
    BUFFER_SAMPLES = int(BUFFER_DURATION * SAMPLE_RATE)  # 3 seconds at 96kHz

    chunks = self.buffers.get(user_name, [])
    if not chunks:
        return

    # Concatenate all chunks
    audio_array = np.concatenate(chunks)

    # Keep only last N seconds (rolling buffer)
    if len(audio_array) > BUFFER_SAMPLES:
        audio_array = audio_array[-BUFFER_SAMPLES:]

    if len(audio_array) == 0:
        return

    # Debouncing - don't transcribe too frequently
    now = self.loop.time()
    if now - self.last_transcription[user_name] < DEBOUNCE_SECONDS:
        return
    self.last_transcription[user_name] = now

    # Resample 96kHz → 16kHz for Whisper
    try:
        target_len = int(len(audio_array) * TARGET_SR / SAMPLE_RATE)
        audio_16k = resample(audio_array, target_len)
    except Exception as e:
        logger.warning(f"Resample failed for {user_name}: {e}")
        self.buffers[user_name] = []
        return

    # Run Whisper in thread pool (blocking operation)
    try:
        result = await self.loop.run_in_executor(
            executor,
            lambda: model.transcribe(audio_16k, fp16=False, language="en")
        )
        text = result["text"].strip()
    except Exception as e:
        logger.warning(f"Whisper transcription failed for {user_name}: {e}")
        text = ""

    # Clear buffer after transcription
    self.buffers[user_name] = []

    if not text:
        return

    # Use the transcribed text (soundboard, logging, etc.)
    # This is where you'd call the callback
    logger.info(f"🗣 [Transcribed] {user_name}: {text}")
```

### 4. Health Monitoring

```python
async def heartbeat_monitor(self):
    """Monitor for stalled audio streams"""
    CHECK_INTERVAL = 10
    SILENCE_THRESHOLD = 120
    last_audio_time = {user: self.loop.time() for user in self.buffers.keys()}
    warned_users = set()

    while True:
        current_time = self.loop.time()

        # Update last audio time for active users
        for user in self.buffers.keys():
            if self.buffers.get(user) or self.speaking_state.get(user, False):
                last_audio_time[user] = current_time
                warned_users.discard(user)

        # Check for silent users
        for user, ts in last_audio_time.items():
            if current_time - ts > SILENCE_THRESHOLD and user not in warned_users:
                logger.warning(f"No audio received from {user} in {SILENCE_THRESHOLD}s")
                warned_users.add(user)
                await self.restart_sink()

        await asyncio.sleep(CHECK_INTERVAL)

async def restart_sink(self):
    """Reset buffers without disconnecting"""
    self.buffers = {user: [] for user in self.buffers.keys()}
    self.last_transcription = {user: 0 for user in self.last_transcription.keys()}
    self.speaking_state = {user: False for user in self.speaking_state.keys()}

    # Cancel all transcription tasks
    for user, task in self.transcription_tasks.items():
        if not task.done():
            task.cancel()
    self.transcription_tasks = {}

    logger.info("Sink has been restarted safely.")
```

### 5. Speaking State Tracking

```python
@voice_recv.BasicSink.listener()
def on_voice_member_speaking_start(self, member):
    """Track when users start speaking"""
    if member.name in user_info:
        logger.info(f"🗣️ {member.name} started talking")
        self.speaking_state[member.name] = True

@voice_recv.BasicSink.listener()
def on_voice_member_speaking_stop(self, member):
    """Track when users stop speaking"""
    if member.name in user_info:
        logger.info(f"🔇 {member.name} stopped talking")
        self.speaking_state[member.name] = False
```

---

## Integration with Our Architecture

### How to Adapt for WhisperEngine

**Current stub location:** `bot/core/audio/speech_engines/whisper.py`

**Key changes needed:**

1. **Add dependencies** to WhisperEngine `__init__`:
   ```python
   import whisper
   import numpy as np
   from scipy.signal import resample
   from concurrent.futures import ThreadPoolExecutor
   ```

2. **Initialize Whisper model in constructor:**
   ```python
   def __init__(self, bot, callback, model_size="tiny.en",
                buffer_duration=3.0, debounce_seconds=1.0):
       super().__init__(bot, callback)
       self.model = whisper.load_model(model_size)
       self.executor = ThreadPoolExecutor(max_workers=4)
       self.buffer_duration = buffer_duration
       self.debounce_seconds = debounce_seconds
       # ... rest of config
   ```

3. **Create WhisperSink class** (adapted from ResilientWhisperSink):
   ```python
   class WhisperSink(voice_recv.BasicSink):
       def __init__(self, vc, callback, model, buffer_duration, debounce,
                    executor, ducking_callback=None):
           super().__init__(asyncio.Event())
           self.vc = vc
           self.callback = callback  # (member, text) -> None
           self.model = model
           self.executor = executor
           self.buffer_duration = buffer_duration
           self.debounce = debounce
           self.ducking_callback = ducking_callback

           # Per-user state
           self.buffers = {}
           self.last_transcription = {}
           self.speaking_state = {}
           self.transcription_tasks = {}
           self.loop = asyncio.get_running_loop()

       def write(self, source, data):
           # Implement as in reference above
           pass

       async def _resilient_transcribe(self, user_name):
           # Implement as in reference above
           pass

       async def _transcribe_user(self, user_name):
           # Implement as in reference above
           # Call self.callback(member, text) when done
           pass
   ```

4. **Start listening:**
   ```python
   async def start_listening(self, voice_client):
       self.sink = WhisperSink(
           voice_client,
           self.callback,
           self.model,
           self.buffer_duration,
           self.debounce_seconds,
           self.executor,
           ducking_callback=self.ducking_callback
       )
       voice_client.listen(self.sink)
       self._is_listening = True
       return self.sink
   ```

5. **Stop listening:**
   ```python
   async def stop_listening(self):
       if self.sink:
           # Cancel all transcription tasks
           for task in self.sink.transcription_tasks.values():
               if not task.done():
                   task.cancel()
       self.executor.shutdown(wait=False)
       self._is_listening = False
   ```

---

## Configuration Parameters

**From user's reference:**
- `BUFFER_DURATION = 3` - Keep 3 seconds of audio (prevents missing words)
- `SAMPLE_RATE = 96000` - Discord's native sample rate
- `TARGET_SR = 16000` - Whisper expects 16kHz audio
- `DEBOUNCE_SECONDS = 1` - Minimum time between transcriptions
- `model_size = "tiny.en"` - Fast, English-only model

**Map to SpeechConfig:**
```python
whisper_model: str = "tiny.en"           # Model size
whisper_buffer_duration: float = 3.0     # Seconds of audio to buffer
whisper_debounce_seconds: float = 1.0    # Min seconds between transcriptions
```

---

## Key Differences: Vosk vs Whisper

| Aspect | Vosk (Current) | Whisper (New) |
|--------|----------------|---------------|
| **Latency** | ~100ms | ~1-3 seconds |
| **Accuracy** | Good | Excellent |
| **Audio Processing** | Built into voice_recv | Custom sink + resampling |
| **Buffering** | Handled by library | Manual rolling buffer |
| **Threading** | Synchronous in sink | ThreadPoolExecutor |
| **Error Recovery** | Basic | Resilient with auto-restart |
| **Per-user isolation** | Yes | Yes (explicit in code) |

---

## Testing Plan

### Phase 1: Implement WhisperSink
1. Create WhisperSink class in `whisper.py`
2. Implement `write()`, `_transcribe_user()`, `_resilient_transcribe()`
3. Add health monitoring (optional initially)
4. Test compilation

### Phase 2: Test Integration
1. Set config to use Whisper engine
2. Join voice channel
3. Speak and verify transcription
4. Check latency (should be 1-3 seconds)
5. Verify soundboard triggers work
6. Test with multiple users

### Phase 3: Polish
1. Add heartbeat monitoring
2. Add sink restart logic
3. Test long-running sessions
4. Compare accuracy with Vosk

---

## Dependencies Required

**Already in project:**
- `discord.py`
- `discord-ext-voice-recv`

**New dependencies for Whisper:**
```toml
# Add to pyproject.toml
openai-whisper = "^20231117"
scipy = "^1.11.0"
numpy = "^1.24.0"  # Already installed, just verify
```

**Install:**
```bash
uv add openai-whisper scipy
# or
pip install openai-whisper scipy
```

---

## Important Notes

1. **Thread Safety:** Whisper model transcription is blocking, so MUST use ThreadPoolExecutor
2. **Memory:** Whisper models can use 1-4GB RAM depending on size
3. **CPU:** "tiny.en" is fast, larger models need GPU for real-time
4. **Resampling:** scipy.signal.resample is critical - Whisper expects 16kHz
5. **Rolling Buffer:** Keeps last 3 seconds to avoid missing words between chunks
6. **Debouncing:** Prevents transcribing too frequently (wastes CPU)

---

## Next Steps for Implementation

1. **Update WhisperEngine.__init__** with model loading
2. **Create WhisperSink class** using reference code
3. **Implement core methods** (write, _transcribe_user, _resilient_transcribe)
4. **Add cleanup** in stop_listening (cancel tasks, shutdown executor)
5. **Test** with simple voice channel connection
6. **Add health monitoring** if needed
7. **Update docs** with Whisper usage instructions

---

## File Locations

- **Implementation:** `bot/core/audio/speech_engines/whisper.py`
- **Config:** `bot/core/audio/speech_engines/config.py` (already has settings)
- **Factory:** `bot/core/audio/speech_engines/__init__.py` (already creates WhisperEngine)
- **User's reference:** See this document

---

**Last Updated:** 2025-10-30
**Ready for Implementation:** Yes
**Estimated Lines of Code:** ~250-300 for complete WhisperSink
