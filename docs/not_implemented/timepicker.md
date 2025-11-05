# Time Picker Component - Web UI

**Status:** Not Implemented
**Priority:** Medium
**Affects:** Multiple config fields (voice activity tracking, weekly recaps, scheduled tasks)

---

## Overview

Time picker is a reusable UI component for the web config interface that allows users to select time values in a human-friendly format. Should be implemented as a function/component similar to text inputs, checkboxes, and dropdowns.

---

## Use Cases

### 1. **Duration Selection** (Hours + Minutes)
**Example Fields:**
- `voice_time_level_1` through `voice_time_level_8` - Voice activity thresholds
- Future: Session timeout settings, cooldown durations

**User wants to set:** `1 hour 15 minutes`

**Current limitation:** `int` field only allows whole hours (1, 2, 3...)

**Proposed solution:**
```python
voice_time_level_1: float = config_field(
    default=1.25,  # 1 hour 15 minutes
    description="Voice time threshold for level 1",
    ui_component="duration_picker"  # New component type
)
```

**UI Design:**
```
┌─────────────────────────────────────┐
│ Voice Time Level 1                  │
│ ┌───────┐  ┌─────────┐              │
│ │   1   │  │   15    │              │
│ └───────┘  └─────────┘              │
│   Hours      Minutes                │
└─────────────────────────────────────┘
```

---

### 2. **Time of Day Selection** (Hours:Minutes in 24h or 12h format)
**Example Fields:**
- `weekly_recap_hour` + `weekly_recap_minute` (new field) - When to post weekly recaps
- Future: Scheduled backup times, maintenance windows

**User wants to set:** `7:30 PM` (19:30 in 24h)

**Current limitation:**
- `weekly_recap_hour: int` (0-23) - no minutes support
- `weekly_recap_day: int` (0-6) - no day names shown

**Proposed solution:**
```python
weekly_recap_time: str = config_field(
    default="09:00",  # HH:MM format (24-hour)
    description="Time to post weekly recap (24-hour format)",
    ui_component="time_picker",
    validate_pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
)

weekly_recap_day: str = config_field(
    default="Monday",
    description="Day of week for recap",
    ui_component="dropdown",
    choices=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
)

weekly_recap_timezone: str = config_field(
    default="UTC",
    description="Timezone for recap scheduling",
    ui_component="timezone_picker",  # Could use existing timezone library
    choices=pytz.all_timezones  # Or common_timezones for shorter list
)
```

**UI Design (24-hour):**
```
┌─────────────────────────────────────┐
│ Weekly Recap Time                   │
│ ┌───────┐ : ┌───────┐               │
│ │  19   │   │  30   │               │
│ └───────┘   └───────┘               │
│   Hour       Minute                 │
│                                     │
│ Day: [Monday    ▼]                  │
│ Timezone: [America/New_York ▼]     │
└─────────────────────────────────────┘
```

**UI Design (12-hour with AM/PM):**
```
┌─────────────────────────────────────┐
│ Weekly Recap Time                   │
│ ┌───────┐ : ┌───────┐  ┌────────┐  │
│ │   7   │   │  30   │  │  PM  ▼ │  │
│ └───────┘   └───────┘  └────────┘  │
│   Hour       Minute      AM/PM     │
└─────────────────────────────────────┘
```

---

## Technical Implementation

### Component Type: `duration_picker`

**Backend (Python):**
```python
# Store as float (hours with decimal)
voice_time_level_1: float = 1.25  # 1 hour 15 minutes
```

**Frontend API:**
```javascript
// Parse float to hours/minutes for display
function floatToHoursMinutes(value) {
    const hours = Math.floor(value);
    const minutes = Math.round((value - hours) * 60);
    return { hours, minutes };
}

// Convert hours/minutes input back to float
function hoursMinutesToFloat(hours, minutes) {
    return hours + (minutes / 60);
}
```

**UI Component:**
- Two numeric inputs (hours, minutes)
- Optional: Slider for quick selection
- Optional: Preset buttons (15m, 30m, 1h, 2h, etc.)

---

### Component Type: `time_picker`

**Backend (Python):**
```python
# Store as string in HH:MM format (24-hour)
weekly_recap_time: str = "19:30"

# Parse when scheduling tasks
from datetime import datetime, time
recap_time = datetime.strptime(config.weekly_recap_time, "%H:%M").time()
```

**Frontend API:**
```javascript
// Validate HH:MM format
function validateTime(timeStr) {
    const regex = /^([01][0-9]|2[0-3]):[0-5][0-9]$/;
    return regex.test(timeStr);
}

// Convert 12h to 24h
function convertTo24Hour(hours, minutes, ampm) {
    if (ampm === 'PM' && hours !== 12) hours += 12;
    if (ampm === 'AM' && hours === 12) hours = 0;
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
}
```

**UI Component:**
- Two numeric inputs (hours 0-23, minutes 0-59)
- Optional: AM/PM dropdown for 12-hour format
- Optional: Clock icon button to open visual clock picker
- Real-time validation with visual feedback

---

## Timezone Handling

**Critical:** All scheduled times must account for timezone differences.

### Storage Strategy

**Option A - Store UTC, Display Local:**
```python
# Store in database as UTC
weekly_recap_time_utc: str = "14:30"  # UTC

# Display to user in their configured timezone
user_timezone = pytz.timezone(config.weekly_recap_timezone)  # "America/New_York"
utc_time = datetime.strptime(config.weekly_recap_time_utc, "%H:%M").time()
local_time = utc_time.replace(tzinfo=pytz.UTC).astimezone(user_timezone)
# Shows as 09:30 AM to user
```

**Option B - Store Local + Timezone:**
```python
# Store both
weekly_recap_time: str = "09:30"  # Local time
weekly_recap_timezone: str = "America/New_York"

# Convert to UTC when scheduling
from datetime import datetime
import pytz

local_tz = pytz.timezone(config.weekly_recap_timezone)
local_time = datetime.strptime(config.weekly_recap_time, "%H:%M")
local_dt = local_tz.localize(local_time)
utc_dt = local_dt.astimezone(pytz.UTC)
# Schedule at UTC time
```

**Recommendation:** **Option B** - More intuitive for users, explicit about timezone

---

## Implementation Checklist

### Phase 1: Duration Picker
- [ ] Add `ui_component` metadata support to `config_field()`
- [ ] Create `DurationPicker` React component (or equivalent)
- [ ] Backend: Accept float values for duration fields
- [ ] Frontend: Parse float ↔ hours/minutes conversion
- [ ] Test with `voice_time_level_*` fields
- [ ] Update config validation to accept decimals

### Phase 2: Time Picker
- [ ] Create `TimePicker` React component
- [ ] Support 24-hour and 12-hour formats (user preference)
- [ ] Add HH:MM string validation
- [ ] Implement timezone picker (use existing library like `react-timezone-select`)
- [ ] Backend: Parse time strings and handle timezone conversion
- [ ] Test with `weekly_recap_time` + `weekly_recap_day` + `weekly_recap_timezone`

### Phase 3: Integration
- [ ] Update ConfigManager to handle new component types
- [ ] Add frontend rendering logic for `duration_picker` and `time_picker`
- [ ] Update config export/import to handle time formats
- [ ] Document usage in CONFIG_SYSTEM.md
- [ ] Add visual examples to web UI documentation

---

## Example Config Schema Registration

```python
from bot.core.config_base import ConfigBase, config_field

@dataclass
class ActivityConfig(ConfigBase):
    """Activity tracking configuration."""

    # Duration picker example
    voice_time_level_1: float = config_field(
        default=1.0,  # 1 hour
        description="Voice time threshold for level 1",
        category="Statistics/Voice Activity",
        guild_override=True,
        ui_component="duration_picker",
        min_value=0.0,
        max_value=1000.0,
        step=0.25  # 15-minute increments
    )

    # Time picker example
    weekly_recap_time: str = config_field(
        default="09:00",
        description="Time to post weekly recap (24-hour format HH:MM)",
        category="Statistics/Reports",
        guild_override=True,
        ui_component="time_picker",
        validate_pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
    )

    weekly_recap_day: str = config_field(
        default="Monday",
        description="Day of week for recap",
        category="Statistics/Reports",
        guild_override=True,
        choices=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    )

    weekly_recap_timezone: str = config_field(
        default="UTC",
        description="Timezone for recap scheduling",
        category="Statistics/Reports",
        guild_override=True,
        ui_component="timezone_picker",
        choices=["UTC", "America/New_York", "America/Chicago", "America/Los_Angeles",
                 "Europe/London", "Europe/Paris", "Asia/Tokyo", "Australia/Sydney"]
        # Or use pytz.common_timezones for full list
    )
```

---

## Related Files

**Backend:**
- `bot/core/config_base.py` - Add `ui_component` metadata support
- `bot/core/config_system.py` - Handle new component types in validation
- `bot/cogs/activity/tracker.py` - Update fields to use duration_picker
- `bot/cogs/audio/voice_speech.py` - Update recap fields to use time_picker

**Frontend (Web UI):**
- `web/src/components/config/` - Create `DurationPicker.tsx` and `TimePicker.tsx`
- `web/src/components/config/ConfigField.tsx` - Add rendering for new component types
- `web/src/utils/timeUtils.ts` - Time conversion utilities

---

## Migration Notes

When implementing, existing int-based time fields will need migration:

**Before:**
```python
voice_time_level_1: int = 1  # 1 hour (no decimals)
weekly_recap_hour: int = 9    # 9 AM (no minutes)
```

**After:**
```python
voice_time_level_1: float = 1.0  # 1 hour (supports 1.25 = 1h 15m)
weekly_recap_time: str = "09:00"  # 9:00 AM (HH:MM format)
```

**Migration strategy:**
1. Add new fields alongside old ones
2. Copy values: `voice_time_level_1` (int) → `voice_time_level_1` (float)
3. Combine fields: `weekly_recap_hour=9` → `weekly_recap_time="09:00"`
4. Remove old fields after migration period
5. Update all code references to use new fields

---

## Future Enhancements

- Visual clock picker (click to select time on analog/digital clock)
- Recurring schedule builder (multiple days, complex patterns)
- Relative time selection ("2 hours from now", "next Monday at 9 AM")
- Duration presets (quick select common durations)
- Smart timezone detection (use browser timezone as default)
- Cron expression builder for advanced scheduling

---

**Last Updated:** 2025-11-04
**Status:** Design Complete, Awaiting Implementation
