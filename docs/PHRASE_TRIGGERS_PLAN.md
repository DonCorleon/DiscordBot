# Phrase Trigger Implementation Plan

## Current State Analysis

### How Triggers Currently Work

**Location:** `bot/cogs/audio/soundboard.py:892-941` (`get_soundfiles_for_text`)

**Current Algorithm:**
1. Split transcribed text into individual words: `text.lower().split()`
2. For each word, check if it matches any trigger in `entry.triggers` list
3. Return matching sounds

**Example:**
```json
{
  "title": "CS:Bomb",
  "triggers": ["bomb", "boom", "bang"],
  "soundfile": "data/soundboard/bomb.mp3"
}
```

If user says: "that bomb was crazy" → matches "bomb"

**Limitations:**
- Only matches single words
- Cannot match "what the fuck" as a phrase
- Cannot distinguish between "what" alone vs "what the fuck"

---

## Proposed Solution

### Goal
Allow triggers to be both **single words** and **multi-word phrases**, with phrases taking priority over individual words.

### Key Design Decisions

#### 1. **Phrase Priority**
- **Longer phrases match first** (greedy matching)
- Example: If triggers include both "what" and "what the fuck":
  - Text: "what the fuck was that" → matches "what the fuck" (not "what")
  - Text: "what was that" → matches "what"

#### 2. **Configuration Format**
No changes needed! Triggers remain a simple list:

```json
{
  "title": "WTF Sound",
  "triggers": [
    "what the fuck",
    "wtf",
    "what the hell"
  ]
}
```

**Backward Compatible:** Existing single-word triggers continue to work unchanged.

#### 3. **Matching Algorithm**

**New Two-Pass Algorithm:**

```
Pass 1: Match phrases (2+ words)
  - Sort triggers by word count (longest first)
  - Search for each phrase in the full text
  - Track matched positions to prevent overlap

Pass 2: Match single words
  - For remaining unmatched words
  - Use current word-by-word matching
  - Skip positions already matched by phrases
```

**Example:**
```
Text: "what the fuck bomb"
Triggers available: ["what the fuck", "bomb", "what"]

Pass 1 (Phrases):
  - "what the fuck" → MATCH at position 0-2

Pass 2 (Words):
  - "bomb" → MATCH at position 3
  - "what" → SKIP (already matched in phrase)

Result: ["what the fuck", "bomb"]
```

---

## Implementation Details

### 1. **Code Changes Required**

#### File: `bot/cogs/audio/soundboard.py`

**Function to Modify:** `get_soundfiles_for_text()` (lines 892-941)

**New Algorithm Pseudocode:**
```python
def get_soundfiles_for_text(self, guild_id, user_id, text):
    text_lower = text.lower()
    words = text_lower.split()
    matched_files = []
    matched_positions = set()  # Track which word positions are matched

    # PASS 1: Match phrases (sorted longest first)
    phrase_triggers = self._get_phrase_triggers(guild_id)
    for phrase, candidates in sorted(phrase_triggers.items(),
                                      key=lambda x: len(x[0].split()),
                                      reverse=True):
        # Search for phrase in text
        positions = self._find_phrase_positions(words, phrase.split())

        for start_pos in positions:
            # Check if any position already matched
            phrase_len = len(phrase.split())
            if any(pos in matched_positions for pos in range(start_pos, start_pos + phrase_len)):
                continue

            # Mark positions as matched
            matched_positions.update(range(start_pos, start_pos + phrase_len))

            # Choose random sound from candidates
            chosen = random.choice(candidates)
            matched_files.append((chosen.soundfile, key, volume, phrase))
            break  # Only match each phrase once

    # PASS 2: Match single words
    for i, word in enumerate(words):
        if i in matched_positions:
            continue  # Skip already matched words

        # Use existing single-word matching logic
        # ... (current code for word matching)

    return matched_files
```

#### Helper Functions to Add:

**1. `_get_phrase_triggers(guild_id)` → dict**
```python
def _get_phrase_triggers(self, guild_id):
    """
    Extract all multi-word triggers and their associated sounds.

    Returns:
        dict: {phrase: [SoundEntry, ...]}
    """
```

**2. `_find_phrase_positions(words, phrase_words)` → list[int]**
```python
def _find_phrase_positions(self, words, phrase_words):
    """
    Find all starting positions where phrase appears in words list.

    Args:
        words: List of words from transcription
        phrase_words: List of words in the trigger phrase

    Returns:
        list[int]: Starting indices where phrase is found

    Example:
        words = ["what", "the", "fuck", "what", "the", "fuck"]
        phrase_words = ["what", "the", "fuck"]
        Returns: [0, 3]
    """
```

**3. `_get_word_triggers(guild_id)` → dict**
```python
def _get_word_triggers(self, guild_id):
    """
    Extract all single-word triggers and their associated sounds.

    Returns:
        dict: {word: [SoundEntry, ...]}
    """
```

---

### 2. **Edge Cases to Handle**

| Case | Behavior |
|------|----------|
| Overlapping phrases | Longer phrase wins (greedy) |
| Phrase appears multiple times | Match only first occurrence per trigger |
| Mixed single + phrase triggers | Phrases matched first, then words |
| Punctuation in speech | Strip punctuation before matching |
| Extra whitespace | Normalize with `.split()` |
| Case sensitivity | All matching is lowercase |
| **Phrase split across windows** | **Concatenate with previous window (see below)** |

**Punctuation Handling:**
```python
# Before split, clean text
import re
text_clean = re.sub(r'[^\w\s]', '', text.lower())
words = text_clean.split()
```

---

### 2.1 **CRITICAL: Handling Phrase Continuation Across Windows**

**Problem:**
The voice recognition system uses a **10-second capture window** (`phrase_time_limit=10` in `voice_speech.py:460`). If a user says a phrase that spans across two windows, it will be split into separate transcriptions.

**Example Scenario:**
```
Window 1 (0-10s):  "hey guys what the"
Window 2 (10-20s): "fuck was that"

Without handling: "what the" and "fuck" never match "what the fuck"
With handling:    Concatenate → "what the fuck was that" → MATCH!
```

**Solution: Per-User Context Buffer**

Maintain a rolling buffer of recent text per user to check for phrase continuations:

```python
# In VoiceSpeechCog or Soundboard cog
self.user_text_history = {}  # {(guild_id, user_id): deque of recent text}
```

**Implementation Details:**

#### Storage Structure
```python
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class TranscriptionWindow:
    text: str
    timestamp: datetime
    words: list[str]  # Pre-split for efficiency

class VoiceSpeechCog:
    def __init__(self, bot):
        # ...
        # Store last N windows per user
        self.user_text_history = {}  # {(guild_id, user_id): deque[TranscriptionWindow]}
        self.history_window_count = 2  # Keep last 2 windows (20 seconds)
        self.history_max_age = timedelta(seconds=30)  # Expire after 30s
```

#### Buffer Management
```python
def _add_to_history(self, guild_id: int, user_id: int, text: str):
    """Add transcription to user's history buffer."""
    key = (guild_id, user_id)

    if key not in self.user_text_history:
        self.user_text_history[key] = deque(maxlen=self.history_window_count)

    window = TranscriptionWindow(
        text=text,
        timestamp=datetime.now(),
        words=text.lower().split()
    )

    self.user_text_history[key].append(window)

    # Clean up old entries
    self._cleanup_old_history(guild_id, user_id)

def _cleanup_old_history(self, guild_id: int, user_id: int):
    """Remove expired history entries."""
    key = (guild_id, user_id)
    if key not in self.user_text_history:
        return

    now = datetime.now()
    history = self.user_text_history[key]

    # Remove entries older than max_age
    while history and (now - history[0].timestamp) > self.history_max_age:
        history.popleft()

    # Clean up empty buffers
    if not history:
        del self.user_text_history[key]
```

#### Modified Trigger Matching
```python
def get_soundfiles_for_text(self, guild_id: int, user_id: int, text: str) -> list:
    """
    Enhanced version that checks current text + previous window for phrases.
    """
    # Build combined text from history
    combined_text = self._get_combined_text(guild_id, user_id, text)

    # Run normal phrase matching on combined text
    matches = self._match_phrases_and_words(combined_text, guild_id, user_id)

    # Add current text to history for next window
    self._add_to_history(guild_id, user_id, text)

    return matches

def _get_combined_text(self, guild_id: int, user_id: int, current_text: str) -> str:
    """Get combined text from history + current window."""
    key = (guild_id, user_id)

    if key not in self.user_text_history:
        return current_text

    # Get previous windows
    history = self.user_text_history[key]

    # Combine: [previous windows] + [current]
    all_texts = [w.text for w in history] + [current_text]

    return " ".join(all_texts)
```

**Example Flow:**

```
User says: "hey guys... [pause] ...what the... [pause] ...fuck"

Window 1: "hey guys"
  - History: []
  - Combined: "hey guys"
  - Matches: None
  - Add to history: ["hey guys"]

Window 2: "what the"
  - History: ["hey guys"]
  - Combined: "hey guys what the"
  - Matches: None (phrase incomplete)
  - Add to history: ["hey guys", "what the"]

Window 3: "fuck was that"
  - History: ["what the", "fuck was that"]  # Note: "hey guys" dropped (max 2 windows)
  - Combined: "what the fuck was that"
  - Matches: ✓ "what the fuck" → plays wtf.mp3
  - Add to history: ["what the", "fuck was that"]
```

**Configuration Options:**

Add to `bot/config.py`:
```python
# Phrase trigger settings
PHRASE_HISTORY_WINDOWS = 2      # Number of previous windows to keep
PHRASE_HISTORY_MAX_AGE = 30     # Maximum age in seconds
PHRASE_MATCHING_ENABLED = True  # Toggle phrase matching
```

**Memory Considerations:**

```
Per user buffer size:
  - 2 windows × ~50 chars/window = 100 chars = ~100 bytes
  - 100 active users = 10 KB
  - Negligible memory impact
```

**Cleanup Strategy:**

```python
# Add periodic cleanup task
@tasks.loop(minutes=5)
async def cleanup_text_history(self):
    """Remove stale user history buffers."""
    now = datetime.now()
    stale_keys = []

    for key, history in self.user_text_history.items():
        if not history or (now - history[-1].timestamp) > self.history_max_age:
            stale_keys.append(key)

    for key in stale_keys:
        del self.user_text_history[key]

    if stale_keys:
        logger.debug(f"Cleaned up {len(stale_keys)} stale user history buffers")
```

**Advantages:**
✅ Catches phrases split across windows
✅ Low memory overhead
✅ Automatic cleanup of old data
✅ Per-user isolation (no cross-contamination)
✅ Configurable window size

**Disadvantages:**
⚠️ Slightly more complex implementation
⚠️ Could match unintended phrases if user pauses mid-sentence
⚠️ Requires testing with real voice patterns

**Alternative: Disable History Matching**

If this adds too much complexity, we can:
1. Document that phrases must be said within 10 seconds
2. Make history matching optional via config flag
3. Users can split long phrases into shorter triggers

---

### 3. **Configuration Examples**

#### Example 1: Phrase with Profanity
```json
{
  "title": "What the Fuck",
  "triggers": ["what the fuck", "wtf"],
  "soundfile": "data/soundboard/wtf.mp3"
}
```

#### Example 2: Overlapping Triggers
```json
{
  "sound1": {
    "triggers": ["oh my god"],
    "soundfile": "data/soundboard/omg.mp3"
  },
  "sound2": {
    "triggers": ["oh my"],
    "soundfile": "data/soundboard/oh.mp3"
  }
}
```
**Result:** Text "oh my god" → matches "oh my god" (longer phrase wins)

#### Example 3: Mixed Single + Phrase
```json
{
  "title": "Bomb Planted",
  "triggers": [
    "bomb has been planted",
    "bomb planted",
    "bomb"
  ],
  "soundfile": "data/soundboard/bomb.mp3"
}
```

---

### 4. **Performance Considerations**

**Current Complexity:** O(n) where n = number of words

**New Complexity:**
- Phrase matching: O(p * n * m) where:
  - p = number of phrase triggers
  - n = number of words in text
  - m = average phrase length
- Word matching: O(w * n) where w = number of word triggers

**Optimization Strategies:**
1. **Pre-process triggers on load:**
   - Separate phrases from words
   - Sort phrases by length once
   - Build lookup dictionaries

2. **Early exit:**
   - Stop phrase search after first match per trigger
   - Skip word matching for positions already matched

3. **Caching:**
   - Cache trigger lists per guild
   - Invalidate on soundboard reload

**Expected Impact:**
- For typical voice recognition (5-15 words): negligible
- For large soundboards (100+ sounds): still < 10ms
- Worth it for better UX

---

### 5. **Testing Plan**

#### Unit Tests Needed

**Test 1: Basic Phrase Matching**
```python
text = "what the fuck was that"
triggers = ["what the fuck"]
expected = ["wtf.mp3"]
```

**Test 2: Phrase Priority Over Words**
```python
text = "what the fuck"
triggers_phrase = ["what the fuck"]  # Sound A
triggers_word = ["what"]             # Sound B
expected = ["Sound A"]  # Not Sound B
```

**Test 3: Multiple Phrases**
```python
text = "oh my god what the fuck"
triggers = ["oh my god", "what the fuck"]
expected = ["omg.mp3", "wtf.mp3"]
```

**Test 4: Overlapping Prevention**
```python
text = "what the fuck the bomb"
triggers = ["what the fuck", "the bomb"]
expected = ["wtf.mp3"]  # "the bomb" overlaps, should not match
```

**Test 5: Mixed Matching**
```python
text = "oh my god bomb"
triggers = ["oh my god", "bomb"]
expected = ["omg.mp3", "bomb.mp3"]
```

**Test 6: No Match**
```python
text = "hello world"
triggers = ["what the fuck"]
expected = []
```

**Test 7: Partial Phrase (No Match)**
```python
text = "what the hell"
triggers = ["what the fuck"]
expected = []  # Must match exact phrase
```

**Test 8: Case Insensitivity**
```python
text = "WHAT THE FUCK"
triggers = ["what the fuck"]
expected = ["wtf.mp3"]
```

**Test 9: Cross-Window Phrase (With History)**
```python
# Simulate sequential windows
window1 = "hey guys what the"
window2 = "fuck was that"
triggers = ["what the fuck"]

# First window
result1 = get_soundfiles_for_text(guild_id, user_id, window1)
expected1 = []  # No match yet

# Second window (should combine with first)
result2 = get_soundfiles_for_text(guild_id, user_id, window2)
expected2 = ["wtf.mp3"]  # Matches across windows
```

**Test 10: Cross-Window Without Match**
```python
window1 = "hello world"
window2 = "goodbye world"
triggers = ["what the fuck"]

result1 = get_soundfiles_for_text(guild_id, user_id, window1)
result2 = get_soundfiles_for_text(guild_id, user_id, window2)

expected1 = []
expected2 = []  # Still no match
```

**Test 11: History Expiration**
```python
# Window 1 at T=0
get_soundfiles_for_text(guild_id, user_id, "what the")

# Wait 35 seconds (past max_age of 30s)
time.sleep(35)

# Window 2 at T=35
result = get_soundfiles_for_text(guild_id, user_id, "fuck")

# History should be expired, no match
expected = []
```

**Test 12: Duplicate Prevention Across Windows**
```python
window1 = "what the fuck"
window2 = "what the fuck"
triggers = ["what the fuck"]

# First window matches
result1 = get_soundfiles_for_text(guild_id, user_id, window1)
expected1 = ["wtf.mp3"]

# Second window - phrase already matched in combined text
# Should still match because it's a new occurrence
result2 = get_soundfiles_for_text(guild_id, user_id, window2)
expected2 = ["wtf.mp3"]
```

#### Integration Testing
1. Record actual voice saying "what the fuck"
2. Verify Vosk transcribes it correctly
3. Verify trigger activates
4. Test with background noise
5. Test with different speakers/accents
6. **Test cross-window scenarios:**
   - Say phrase slowly with pauses: "what... the... fuck"
   - Verify it still triggers when spread across windows
   - Test with unrelated words between: "what... hello... the fuck"
   - Verify false positives don't occur

---

### 6. **Rollout Strategy**

#### Phase 1: Development (Local Testing)
- [ ] Implement new algorithm
- [ ] Add helper functions
- [ ] Unit tests
- [ ] Test with existing single-word triggers (backward compatibility)

#### Phase 2: Configuration
- [ ] Add phrase triggers to soundboard.json
- [ ] Test popular phrases:
  - "what the fuck"
  - "oh my god"
  - "lets go"
  - "no way"
  - "come on"

#### Phase 3: Beta Testing
- [ ] Deploy to test server
- [ ] Monitor logs for phrase matches
- [ ] Verify performance (check latency in logs)
- [ ] Collect user feedback

#### Phase 4: Production
- [ ] Deploy to production
- [ ] Monitor for issues
- [ ] Document phrase trigger feature for users

---

### 7. **User-Facing Changes**

#### Documentation Update
Add to soundboard commands help:

```
Triggers can be single words OR phrases:
  • Single word: "bomb", "hello", "wtf"
  • Phrases: "what the fuck", "oh my god", "lets go"

Longer phrases take priority:
  • If triggers include "what" and "what the fuck"
  • Saying "what the fuck" triggers the phrase
  • Saying "what" alone triggers the word
```

#### Command Updates (Optional)
Update `~soundboard add` to suggest phrase format:

```
~soundboard add
Title: What the Fuck
Trigger words (comma-separated, can include phrases): what the fuck, wtf
Sound file: wtf.mp3
```

---

### 8. **Future Enhancements**

#### Fuzzy Matching (Post-MVP)
- Handle variations: "what the fck", "whatthefuck"
- Levenshtein distance for typos
- Phonetic matching for similar sounds

#### Regex Triggers (Advanced)
```json
{
  "triggers": [
    "regex:what (the|a) (fuck|hell)"
  ]
}
```

#### Wildcard Support
```json
{
  "triggers": [
    "* the fuck",  // Matches "what the fuck", "where the fuck", etc.
  ]
}
```

---

## Implementation Checklist

### Code Changes
- [ ] Add `_get_phrase_triggers()` helper function
- [ ] Add `_find_phrase_positions()` helper function
- [ ] Add `_get_word_triggers()` helper function
- [ ] Refactor `get_soundfiles_for_text()` to use two-pass algorithm
- [ ] Add punctuation stripping
- [ ] Add position tracking to prevent overlaps
- [ ] **Add `TranscriptionWindow` dataclass for history tracking**
- [ ] **Add `user_text_history` dict to VoiceSpeechCog or Soundboard**
- [ ] **Implement `_add_to_history()` method**
- [ ] **Implement `_cleanup_old_history()` method**
- [ ] **Implement `_get_combined_text()` method**
- [ ] **Add periodic cleanup task for stale history**
- [ ] **Add config options: PHRASE_HISTORY_WINDOWS, PHRASE_HISTORY_MAX_AGE**

### Testing
- [ ] Write unit tests for phrase matching
- [ ] Write unit tests for priority/overlap cases
- [ ] **Write unit tests for cross-window matching**
- [ ] **Write unit tests for history expiration**
- [ ] Write integration tests with voice input
- [ ] Test backward compatibility with existing triggers
- [ ] Performance testing with large soundboards
- [ ] **Test cross-window scenarios with real voice (slow speech)**

### Documentation
- [ ] Update PHRASE_TRIGGERS_PLAN.md (this file)
- [ ] Update user-facing help text
- [ ] Add example phrases to soundboard.json
- [ ] Document in README or CLAUDE.md

### Deployment
- [ ] Test on local machine
- [ ] Deploy to test server
- [ ] Monitor logs for issues
- [ ] Deploy to production
- [ ] Update CURRENT_WORK.md

---

## Estimated Effort

| Task | Effort | Notes |
|------|--------|-------|
| Code implementation (phrases) | 2-3 hours | Refactor + helpers |
| **Code implementation (history)** | **1-2 hours** | **Context buffer + cleanup** |
| Unit testing | 1-2 hours | 12+ test cases (added cross-window) |
| Integration testing | 1-2 hours | Voice tests + cross-window scenarios |
| Configuration | 30 min | Add phrase triggers + config |
| Documentation | 30 min | Update help/docs |
| **Total** | **6-10 hours** | Can be done incrementally |

**Note:** History tracking adds ~1-2 hours but significantly improves UX for natural speech patterns.

---

## Example Implementation Preview

### Before (Current):
```python
def get_soundfiles_for_text(self, guild_id, user_id, text):
    words = text.lower().split()
    matched_files = []

    for word in words:
        # Check each word against triggers
        for entry in self.soundboard.sounds.values():
            if word in [t.lower() for t in entry.triggers]:
                matched_files.append(...)

    return matched_files
```

### After (With Phrases):
```python
def get_soundfiles_for_text(self, guild_id, user_id, text):
    text_clean = re.sub(r'[^\w\s]', '', text.lower())
    words = text_clean.split()
    matched_files = []
    matched_positions = set()

    # PASS 1: Phrases (longest first)
    phrase_map = self._get_phrase_triggers(guild_id)
    for phrase, candidates in sorted(phrase_map.items(),
                                      key=lambda x: -len(x[0].split())):
        positions = self._find_phrase_positions(words, phrase.split())
        for pos in positions:
            if self._is_position_free(pos, len(phrase.split()), matched_positions):
                # Add match and mark positions
                matched_files.append(...)
                matched_positions.update(...)
                break

    # PASS 2: Single words
    for i, word in enumerate(words):
        if i not in matched_positions:
            # Use existing word matching logic
            ...

    return matched_files
```

---

## Questions for Consideration

1. **Should we support partial phrases?**
   - Example: "what the" matches "what the fuck"?
   - **Recommendation:** No, require exact match for clarity

2. **Should phrases be case-sensitive?**
   - **Recommendation:** No, all lowercase like current system

3. **Should we limit phrase length?**
   - **Recommendation:** Yes, max 6 words to prevent abuse

4. **Should we support multiple languages?**
   - **Recommendation:** Later enhancement, current system is English-only

5. **How to handle duplicates?**
   - Example: Text has "what the fuck" twice
   - **Recommendation:** Match only first occurrence (current behavior)

6. **Should history matching be enabled by default?**
   - **Recommendation:** Yes, but make it configurable via `PHRASE_MATCHING_ENABLED` flag
   - Users can disable if they experience false positives

7. **How many previous windows should we keep?**
   - **Recommendation:** 2 windows (20 seconds total)
   - Most natural phrases are said within this timeframe
   - Balance between catching phrases and preventing false positives

8. **Should we match phrases with words in between?**
   - Example: "what hello the fuck" matches "what the fuck"?
   - **Recommendation:** No, require consecutive words
   - Prevents too many false positives

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Performance degradation | Medium | Low | Pre-process triggers, cache lookups |
| Breaking existing triggers | High | Low | Maintain backward compatibility |
| Complex edge cases | Low | Medium | Comprehensive unit tests |
| False positives | Medium | Low | Require exact phrase match |
| Vosk transcription errors | Medium | Medium | User can adjust triggers to match actual transcription |

---

## Conclusion

This plan provides a **backward-compatible**, **performant**, and **user-friendly** way to add phrase trigger support to the Discord bot.

**Key Benefits:**
✅ No breaking changes to existing triggers
✅ Intuitive configuration (just add phrases to triggers list)
✅ Greedy matching prevents conflicts
✅ Minimal performance impact
✅ Clear implementation path

**Ready to implement!**
