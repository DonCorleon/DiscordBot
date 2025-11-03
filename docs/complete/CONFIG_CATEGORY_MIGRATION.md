# Configuration Category Migration Record

**Date:** 2025-11-03
**Purpose:** Record of all config category changes for reversion if needed

---

## Migration Summary

This document records the migration of configuration categories from the old structure to a new, more logical organization. Each section shows the original category path and the new category path for every configuration field.

---

## System Config (bot/core/system_config.py)

### Bot Owner → Bot Configuration/Core
- `token`: "Bot Owner" → "Bot Configuration/Core"
- `command_prefix`: "Bot Owner" → "Bot Configuration/Core"
- `bot_owner_id`: "Bot Owner" → "Bot Configuration/Core"

### Admin/System → Bot Configuration/Logging
- `log_level`: "Admin/System" → "Bot Configuration/Logging"
- `log_dir`: "Admin/System" → "Data Storage"
- `log_rotation_interval`: "Admin/System" → "Bot Configuration/Logging"
- `log_backup_count`: "Admin/System" → "Bot Configuration/Logging"
- `admin_data_dir`: "Admin/System" → "Data Storage"
- `update_git_output_truncate`: "Admin/System" → "Bot Configuration/Features"
- `update_shutdown_delay`: "Admin/System" → "Bot Configuration/Features"

### Admin/Monitoring → Bot Configuration/Monitoring
- `max_history`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `health_collection_interval`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `data_export_interval`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `logs_max_lines`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `monitor_health_interval`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `high_memory_threshold`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `high_cpu_threshold`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `large_queue_warning_size`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `health_color_warning_memory`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `health_color_warning_cpu`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `health_color_caution_memory`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `health_color_caution_cpu`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `logs_chunk_char_limit`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `log_message_truncate_length`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `ping_excellent_threshold`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `ping_good_threshold`: "Admin/Monitoring" → "Bot Configuration/Monitoring"
- `ping_fair_threshold`: "Admin/Monitoring" → "Bot Configuration/Monitoring"

### Admin/Features → Bot Configuration/Features
- `enable_auto_disconnect`: "Admin/Features" → "Bot Configuration/Features"
- `enable_speech_recognition`: "Admin/Features" → "Bot Configuration/Features"

### Admin/Web → Bot Configuration/Web Dashboard
- `enable_web_dashboard`: "Admin/Web" → "Bot Configuration/Web Dashboard"
- `web_host`: "Admin/Web" → "Bot Configuration/Web Dashboard"
- `web_port`: "Admin/Web" → "Bot Configuration/Web Dashboard"
- `web_reload`: "Admin/Web" → "Bot Configuration/Web Dashboard"

### Admin/Voice → Audio/Playback
- `keepalive_interval`: "Admin/Voice" → "Audio/Playback"

### Admin/Audio → Audio/Engine
- `audio_sample_rate`: "Admin/Audio" → "Audio/Engine"
- `audio_channels`: "Admin/Audio" → "Audio/Engine"
- `audio_chunk_size`: "Admin/Audio" → "Audio/Engine"
- `audio_duck_transition_ms`: "Admin/Audio" → "Audio/Engine"

---

## Soundboard Config (bot/cogs/audio/soundboard.py)

### Playback → Audio/Playback
- `default_volume`: "Playback" → "Audio/Playback"
- `ducking_enabled`: "Playback" → "Audio/Playback"
- `ducking_level`: "Playback" → "Audio/Playback"
- `ducking_transition_ms`: "Playback" → "Audio/Playback"
- `sound_playback_timeout`: "Playback" → "Audio/Playback"
- `sound_queue_warning_size`: "Playback" → "Audio/Playback"

### Admin → Data Storage
- `soundboard_dir`: "Admin" → "Data Storage"

### DiscordUI/Uploading → User Interface/Sound Management
- `sound_upload_modal_timeout`: "DiscordUI/Uploading" → "User Interface/Sound Management"
- `sound_edit_modal_timeout`: "DiscordUI/Uploading" → "User Interface/Sound Management"
- `sound_title_max_length`: "DiscordUI/Uploading" → "User Interface/Sound Management"
- `sound_description_max_length`: "DiscordUI/Uploading" → "User Interface/Sound Management"
- `sound_description_edit_max_length`: "DiscordUI/Uploading" → "User Interface/Sound Management"
- `sound_triggers_max_length`: "DiscordUI/Uploading" → "User Interface/Sound Management"
- `sound_flags_max_length`: "DiscordUI/Uploading" → "User Interface/Sound Management"

### DiscordUI/Volume → User Interface/Sound Management
- `sound_volume_min`: "DiscordUI/Volume" → "User Interface/Sound Management"
- `sound_volume_max`: "DiscordUI/Volume" → "User Interface/Sound Management"
- `sound_volume_input_max_length`: "DiscordUI/Volume" → "User Interface/Sound Management"

### DiscordUI/Commands → User Interface/Commands
- `sound_browser_timeout`: "DiscordUI/Commands" → "User Interface/Commands"
- `soundboard_pagination_size`: "DiscordUI/Commands" → "User Interface/Commands"
- `sound_select_truncate_triggers`: "DiscordUI/Commands" → "User Interface/Commands"

---

## Voice Config (bot/cogs/audio/voice_speech.py)

### Playback → Audio/Playback
- `auto_join_enabled`: "Playback" → "Audio/Playback"
- `auto_disconnect_timeout` (formerly `auto_join_timeout`): "Playback" → "Audio/Playback"
- `sound_playback_timeout`: "Playback" → "Audio/Playback"
- `sound_queue_warning_size`: "Playback" → "Audio/Playback"
- `keepalive_interval`: "Playback" → "Audio/Playback"

### Admin/SpeechRecognition → Audio/Speech Recognition/Advanced
- `voice_speech_phrase_time_limit`: "Admin/SpeechRecognition" → "Audio/Speech Recognition/Advanced"
- `voice_speech_error_log_threshold`: "Admin/SpeechRecognition" → "Audio/Speech Recognition/Advanced"
- `voice_speech_chunk_size`: "Admin/SpeechRecognition" → "Audio/Speech Recognition/Advanced"

### Transcription → Audio/Speech Recognition
- `transcript_enabled`: "Transcription" → "Audio/Speech Recognition"
- `transcript_flush_interval`: "Transcription" → "Audio/Speech Recognition"
- `transcript_dir`: "Transcription" → "Data Storage"

---

## Speech Config (bot/core/audio/speech_engines/config.py)

### Speech Recognition → Audio/Speech Recognition
- `engine`: "Speech Recognition" → "Audio/Speech Recognition"

### Speech Recognition/Vosk → Audio/Speech Recognition
- `vosk_model_path`: "Speech Recognition/Vosk" → "Audio/Speech Recognition"

### Speech Recognition/Whisper → Audio/Speech Recognition
- `whisper_model`: "Speech Recognition/Whisper" → "Audio/Speech Recognition"
- `whisper_buffer_duration`: "Speech Recognition/Whisper" → "Audio/Speech Recognition"
- `whisper_debounce_seconds`: "Speech Recognition/Whisper" → "Audio/Speech Recognition"

---

## TTS Config (bot/cogs/audio/tts.py)

### TextToSpeech/PyTTS → Audio/Text-to-Speech
- `tts_default_volume`: "TextToSpeech/PyTTS" → "Audio/Text-to-Speech"
- `tts_default_rate`: "TextToSpeech/PyTTS" → "Audio/Text-to-Speech"
- `tts_max_text_length`: "TextToSpeech/PyTTS" → "Audio/Text-to-Speech"

---

## EdgeTTS Config (bot/cogs/audio/edge_tts.py)

### TextToSpeech/Edge → Audio/Text-to-Speech
- `edge_tts_default_volume`: "TextToSpeech/Edge" → "Audio/Text-to-Speech"
- `edge_tts_default_voice`: "TextToSpeech/Edge" → "Audio/Text-to-Speech"

---

## Activity Config (bot/cogs/activity/tracker.py)

### Stats/Voice Tracking → Statistics/Voice Activity
- `voice_tracking_enabled`: "Stats/Voice Tracking" → "Statistics/Voice Activity"
- `voice_points_per_minute`: "Stats/Voice Tracking" → "Statistics/Voice Activity"
- `voice_time_display_mode`: "Stats/Voice Tracking" → "Statistics/Voice Activity"
- `voice_tracking_type`: "Stats/Voice Tracking" → "Statistics/Voice Activity"

### Stats/Voice Time Levels → Statistics/Voice Activity
- `voice_time_level_1`: "Stats/Voice Time Levels" → "Statistics/Voice Activity"
- `voice_time_level_2`: "Stats/Voice Time Levels" → "Statistics/Voice Activity"
- `voice_time_level_3`: "Stats/Voice Time Levels" → "Statistics/Voice Activity"
- `voice_time_level_4`: "Stats/Voice Time Levels" → "Statistics/Voice Activity"
- `voice_time_level_5`: "Stats/Voice Time Levels" → "Statistics/Voice Activity"
- `voice_time_level_6`: "Stats/Voice Time Levels" → "Statistics/Voice Activity"
- `voice_time_level_7`: "Stats/Voice Time Levels" → "Statistics/Voice Activity"
- `voice_time_level_8`: "Stats/Voice Time Levels" → "Statistics/Voice Activity"

### Stats/Weekly Recap → Statistics/Reports
- `enable_weekly_recap`: "Stats/Weekly Recap" → "Statistics/Reports"
- `weekly_recap_channel_id`: "Stats/Weekly Recap" → "Statistics/Reports"
- `weekly_recap_day`: "Stats/Weekly Recap" → "Statistics/Reports"
- `weekly_recap_hour`: "Stats/Weekly Recap" → "Statistics/Reports"

### Stats/Activity Points → Gamification/Points System
- `activity_base_message_points_min`: "Stats/Activity Points" → "Gamification/Points System"
- `activity_base_message_points_max`: "Stats/Activity Points" → "Gamification/Points System"
- `activity_link_bonus_points`: "Stats/Activity Points" → "Gamification/Points System"
- `activity_attachment_bonus_points`: "Stats/Activity Points" → "Gamification/Points System"
- `activity_reaction_points`: "Stats/Activity Points" → "Gamification/Points System"
- `activity_reply_points`: "Stats/Activity Points" → "Gamification/Points System"

### Stats/Display → Statistics/Display Options
- `leaderboard_default_limit`: "Stats/Display" → "Statistics/Display Options"
- `user_stats_channel_breakdown_limit`: "Stats/Display" → "Statistics/Display Options"
- `user_stats_triggers_limit`: "Stats/Display" → "Statistics/Display Options"
- `leaderboard_bar_chart_length`: "Stats/Display" → "Statistics/Display Options"
- `voice_activity_bar_chart_length`: "Stats/Display" → "Statistics/Display Options"

### Stats/Activity Tiers → Gamification/Message Tiers
- `activity_tier_diamond`: "Stats/Activity Tiers" → "Gamification/Message Tiers"
- `activity_tier_gold`: "Stats/Activity Tiers" → "Gamification/Message Tiers"
- `activity_tier_silver`: "Stats/Activity Tiers" → "Gamification/Message Tiers"
- `activity_tier_bronze`: "Stats/Activity Tiers" → "Gamification/Message Tiers"
- `activity_tier_contributor`: "Stats/Activity Tiers" → "Gamification/Message Tiers"

### Stats/Voice Tiers → Gamification/Voice Tiers
- `voice_tier_lurker`: "Stats/Voice Tiers" → "Gamification/Voice Tiers"
- `voice_tier_listener`: "Stats/Voice Tiers" → "Gamification/Voice Tiers"
- `voice_tier_regular`: "Stats/Voice Tiers" → "Gamification/Voice Tiers"
- `voice_tier_active`: "Stats/Voice Tiers" → "Gamification/Voice Tiers"
- `voice_tier_champion`: "Stats/Voice Tiers" → "Gamification/Voice Tiers"

### Stats/Milestones → Gamification/Milestones
- `mystats_milestone_1`: "Stats/Milestones" → "Gamification/Milestones"
- `mystats_milestone_2`: "Stats/Milestones" → "Gamification/Milestones"
- `mystats_milestone_3`: "Stats/Milestones" → "Gamification/Milestones"
- `mystats_milestone_4`: "Stats/Milestones" → "Gamification/Milestones"
- `mystats_milestone_5`: "Stats/Milestones" → "Gamification/Milestones"
- `mystats_milestone_6`: "Stats/Milestones" → "Gamification/Milestones"
- `mystats_milestone_7`: "Stats/Milestones" → "Gamification/Milestones"
- `mystats_milestone_8`: "Stats/Milestones" → "Gamification/Milestones"
- `mystats_milestone_9`: "Stats/Milestones" → "Gamification/Milestones"

---

## Reversion Instructions

To revert these changes:

1. Use find/replace in each file to change categories back to original values
2. Use the mappings above to identify which fields need changes
3. Restart the bot to reload configuration schemas

### Example Reversion Commands:

For system_config.py:
```python
# Change:
category="Bot Configuration/Core"
# Back to:
category="Bot Owner"
```

For soundboard.py:
```python
# Change:
category="Audio/Playback"
# Back to:
category="Playback"
```

---

## Files Modified

1. `bot/core/system_config.py` - System configuration
2. `bot/cogs/audio/soundboard.py` - Soundboard configuration
3. `bot/cogs/audio/voice_speech.py` - Voice configuration
4. `bot/core/audio/speech_engines/config.py` - Speech engine configuration
5. `bot/cogs/audio/tts.py` - TTS configuration
6. `bot/cogs/audio/edge_tts.py` - Edge TTS configuration
7. `bot/cogs/activity/tracker.py` - Activity tracking configuration

---

## Testing Checklist

After migration:
- [ ] Bot starts without errors
- [ ] Web UI config page loads correctly
- [ ] All categories appear in correct hierarchy
- [ ] Settings can be changed and saved
- [ ] Settings persist after bot restart
- [ ] Guild-specific overrides still work
- [ ] Admin-only settings are still restricted

---

**End of Migration Record**
