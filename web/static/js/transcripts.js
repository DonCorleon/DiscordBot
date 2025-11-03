/**
 * Transcripts Viewer functionality
 */

let currentGuild = '';
let currentChannel = '';
let currentSearch = '';
let viewMode = 'live'; // 'live' or 'history'
let autoScroll = true;
let allGuilds = [];
let allChannels = [];
let transcripts = [];
let historicalSessions = [];
let currentSession = null;

/**
 * Convert UTC timestamp to local time string
 * Timestamps from the bot are in UTC (without 'Z' suffix)
 */
function formatTimestamp(utcTimestamp) {
    // Add 'Z' to indicate UTC if not present
    const isoString = utcTimestamp.endsWith('Z') ? utcTimestamp : utcTimestamp + 'Z';
    const date = new Date(isoString);
    return date.toLocaleString();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadGuilds();
    loadChannels(); // Load all channels on initial load
    loadTranscripts();
    setupEventListeners();

    // Setup WebSocket handlers after wsClient is ready
    // Use a slight delay to ensure websocket.js has loaded and created wsClient
    setTimeout(() => {
        if (window.wsClient) {
            setupWebSocket();
        } else {
            console.error('⚠️ wsClient still not available after delay');
        }
    }, 500);
});

function setupEventListeners() {
    // Guild selection
    document.getElementById('guild-select').addEventListener('change', (e) => {
        currentGuild = e.target.value;
        loadChannels();
        // Filter existing transcripts instead of reloading
        if (viewMode === 'live') {
            filterAndDisplayTranscripts();
        } else {
            loadTranscripts();
        }
    });

    // Channel selection
    document.getElementById('channel-select').addEventListener('change', (e) => {
        const selectedOption = e.target.options[e.target.selectedIndex];

        // If no guild is selected and a channel is chosen, auto-select the guild
        if (!currentGuild && e.target.value && selectedOption.dataset.guildId) {
            const guildId = selectedOption.dataset.guildId;
            currentGuild = guildId;
            document.getElementById('guild-select').value = guildId;
            currentChannel = e.target.value;
            // Reload channels for the selected guild
            loadChannels();
            if (viewMode === 'live') {
                filterAndDisplayTranscripts();
            } else {
                loadTranscripts();
            }
        } else {
            currentChannel = e.target.value;
            // Filter existing transcripts instead of reloading
            if (viewMode === 'live') {
                filterAndDisplayTranscripts();
            } else {
                loadTranscripts();
            }
        }
    });

    // Search input (with debounce)
    let searchTimeout;
    document.getElementById('transcript-search').addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            currentSearch = e.target.value;
            // Filter existing transcripts instead of reloading
            if (viewMode === 'live') {
                filterAndDisplayTranscripts();
            } else {
                loadTranscripts();
            }
        }, 300);
    });

    // Clear filters button
    document.getElementById('clear-filters-btn').addEventListener('click', () => {
        currentGuild = '';
        currentChannel = '';
        currentSearch = '';
        document.getElementById('guild-select').value = '';
        document.getElementById('channel-select').value = '';
        document.getElementById('transcript-search').value = '';
        loadChannels();
        loadTranscripts();
    });

    // Live mode toggle
    document.getElementById('live-btn').addEventListener('click', () => {
        switchToLiveMode();
    });

    // History mode toggle
    document.getElementById('history-btn').addEventListener('click', () => {
        switchToHistoryMode();
    });

    // Auto-scroll checkbox
    document.getElementById('auto-scroll-checkbox').addEventListener('change', (e) => {
        autoScroll = e.target.checked;
    });
}

function setupWebSocket() {
    // Listen for real-time transcription events via WebSocket
    if (window.wsClient) {
        console.log('Setting up transcription WebSocket listener');
        wsClient.on('transcription', (data) => {
            console.log('🎤 Received real-time transcription:', data);
            console.log('Transcription data:', data.data);
            // Add to transcripts list
            addTranscriptionToView(data.data);
            updateStats();
        });
    } else {
        console.error('⚠️ wsClient not available!');
    }
}

async function loadGuilds() {
    try {
        const endpoint = viewMode === 'live'
            ? '/api/v1/transcripts/guilds'
            : '/api/v1/transcripts/history/guilds';

        const response = await fetch(endpoint);
        const data = await response.json();

        allGuilds = data.guilds || [];

        const select = document.getElementById('guild-select');
        select.innerHTML = '<option value="">All Guilds</option>';

        allGuilds.forEach(guild => {
            const option = document.createElement('option');
            option.value = guild.guild_id;
            option.textContent = guild.guild_name;
            select.appendChild(option);
        });

    } catch (error) {
        console.error('Error loading guilds:', error);
    }
}

async function loadChannels() {
    const select = document.getElementById('channel-select');
    select.innerHTML = '<option value="">All Channels</option>';

    if (!currentGuild) {
        // When no guild is selected, show all channels across all guilds in "Guild:Channel" format
        try {
            const endpoint = viewMode === 'live'
                ? '/api/v1/transcripts/all-channels'
                : '/api/v1/transcripts/history/channels';

            const response = await fetch(endpoint);
            const data = await response.json();

            allChannels = data.channels || [];

            allChannels.forEach(channel => {
                const option = document.createElement('option');
                option.value = channel.channel_id;
                option.dataset.guildId = channel.guild_id; // Store guild_id for later use
                option.textContent = `${channel.guild_name}:${channel.channel_name}`;
                select.appendChild(option);
            });

        } catch (error) {
            console.error('Error loading all channels:', error);
        }
        return;
    }

    try {
        const endpoint = viewMode === 'live'
            ? `/api/v1/transcripts/channels?guild_id=${currentGuild}`
            : `/api/v1/transcripts/history/channels?guild_id=${currentGuild}`;

        const response = await fetch(endpoint);
        const data = await response.json();

        allChannels = data.channels || [];

        allChannels.forEach(channel => {
            const option = document.createElement('option');
            option.value = channel.channel_id;
            option.textContent = channel.channel_name;
            select.appendChild(option);
        });

    } catch (error) {
        console.error('Error loading channels:', error);
    }
}

async function loadTranscripts() {
    if (viewMode === 'live') {
        await loadLiveTranscripts();
    } else {
        await loadHistoricalSessions();
    }
}

async function loadLiveTranscripts() {
    try {
        const params = new URLSearchParams({
            limit: '100'
        });

        if (currentGuild) {
            // Keep as string - Discord IDs are too large for JS numbers
            params.append('guild_id', currentGuild);
        }

        if (currentChannel) {
            // Keep as string - Discord IDs are too large for JS numbers
            params.append('channel_id', currentChannel);
        }

        if (currentSearch) {
            params.append('search', currentSearch);
        }

        const response = await fetch(`/api/v1/transcripts/list?${params}`);
        const data = await response.json();

        transcripts = data.transcriptions || [];
        displayTranscripts(transcripts);
        updateStats(data);

    } catch (error) {
        console.error('Error loading transcripts:', error);
        showError('Failed to load transcripts');
    }
}

async function loadHistoricalSessions() {
    try {
        const params = new URLSearchParams();

        if (currentGuild) {
            params.append('guild_id', currentGuild);
        }

        if (currentChannel) {
            params.append('channel_id', currentChannel);
        }

        const response = await fetch(`/api/v1/transcripts/history/sessions?${params}`);
        const data = await response.json();

        historicalSessions = data.sessions || [];
        displayHistoricalSessions(historicalSessions);
        updateHistoryStats(data);

    } catch (error) {
        console.error('Error loading historical sessions:', error);
        showError('Failed to load historical sessions');
    }
}

function filterAndDisplayTranscripts() {
    // Filter the existing transcripts array based on current filters
    const filtered = transcripts.filter(t => {
        // Guild filter
        if (currentGuild && t.guild_id !== currentGuild) {
            return false;
        }
        // Channel filter
        if (currentChannel && t.channel_id !== currentChannel) {
            return false;
        }
        // Search filter
        if (currentSearch) {
            const searchLower = currentSearch.toLowerCase();
            if (!t.text.toLowerCase().includes(searchLower) &&
                !t.user.toLowerCase().includes(searchLower)) {
                return false;
            }
        }
        return true;
    });

    displayTranscripts(filtered);

    // Update stats with filtered count
    document.getElementById('total-transcripts').textContent = transcripts.length.toLocaleString();
    document.getElementById('filtered-transcripts').textContent = filtered.length.toLocaleString();
    document.getElementById('last-updated').textContent = new Date().toLocaleTimeString();
}

function displayTranscripts(transcriptList) {
    const container = document.getElementById('transcripts-content');

    if (!transcriptList || transcriptList.length === 0) {
        container.innerHTML = '<div class="transcripts-empty">No transcriptions match the current filters</div>';
        return;
    }

    // Reverse to show oldest first (newest at bottom)
    const reversed = [...transcriptList].reverse();

    container.innerHTML = reversed.map(t => {
        const timestamp = formatTimestamp(t.timestamp);
        const triggers = t.triggers && t.triggers.length > 0
            ? ` | 🔊 ${t.triggers.map(tr => `${escapeHtml(tr.word)}→${escapeHtml(tr.sound)}`).join(', ')}`
            : '';

        // Only show guild if no specific guild is selected
        const showGuild = !currentGuild;
        const guildHtml = showGuild ? `<span class="transcript-guild">${escapeHtml(t.guild || 'Unknown')}</span>` : '';

        // Only show channel if no specific channel is selected
        const showChannel = !currentChannel;
        const channelHtml = showChannel ? `<span class="transcript-channel">#${escapeHtml(t.channel || 'Unknown')}</span>` : '';

        // Add avatar if available
        const avatarHtml = t.user_avatar_url
            ? `<img src="${escapeHtml(t.user_avatar_url)}" class="transcript-avatar" alt="${escapeHtml(t.user)}" onerror="this.style.display='none'">`
            : '';

        return `
            <div class="transcript-entry">
                <span class="transcript-timestamp">${timestamp}</span>
                ${guildHtml}
                ${channelHtml}
                <span class="transcript-user">${escapeHtml(t.user || 'Unknown')}</span>
                ${avatarHtml}
                <span class="transcript-text">${escapeHtml(t.text)}</span>${triggers}
            </div>
        `;
    }).join('');

    // Auto-scroll to bottom if enabled
    if (autoScroll) {
        container.scrollTop = container.scrollHeight;
    }
}

function addTranscriptionToView(transcription) {
    console.log('addTranscriptionToView called with:', transcription);
    console.log('Current view mode:', viewMode);
    console.log('Current filters - Guild:', currentGuild, 'Channel:', currentChannel, 'Search:', currentSearch);

    // IMPORTANT: Only add to view if we're in live mode
    // Historical transcripts should not be added via WebSocket
    if (viewMode !== 'live') {
        console.log('❌ Not in live mode, ignoring real-time transcription');
        return;
    }

    // Only add if it matches current filters
    // IDs are now strings from backend for JavaScript compatibility
    if (currentGuild && transcription.guild_id !== currentGuild) {
        console.log('❌ Filtered out by guild filter:', transcription.guild_id, '!==', currentGuild);
        return;
    }
    if (currentChannel && transcription.channel_id !== currentChannel) {
        console.log('❌ Filtered out by channel filter:', transcription.channel_id, '!==', currentChannel);
        return;
    }
    if (currentSearch) {
        const searchLower = currentSearch.toLowerCase();
        if (!transcription.text.toLowerCase().includes(searchLower) &&
            !transcription.user.toLowerCase().includes(searchLower)) {
            console.log('❌ Filtered out by search filter');
            return;
        }
    }

    console.log('✅ Transcription passed filters, adding to view');

    // Add to beginning of transcripts array (newest first in array)
    transcripts.unshift(transcription);

    // Keep only last 100
    if (transcripts.length > 100) {
        transcripts.pop(); // Remove oldest
    }

    console.log('Transcripts array now has', transcripts.length, 'items');

    // Append to end of display (newest at bottom) without flicker
    const container = document.getElementById('transcripts-content');

    // Clear empty message if present
    if (container.querySelector('.transcripts-empty')) {
        container.innerHTML = '';
    }

    const timestamp = formatTimestamp(transcription.timestamp);
    const triggers = transcription.triggers && transcription.triggers.length > 0
        ? ` | 🔊 ${transcription.triggers.map(tr => `${escapeHtml(tr.word)}→${escapeHtml(tr.sound)}`).join(', ')}`
        : '';

    // Only show guild if no specific guild is selected
    const showGuild = !currentGuild;
    const guildHtml = showGuild ? `<span class="transcript-guild">${escapeHtml(transcription.guild || 'Unknown')}</span>` : '';

    // Only show channel if no specific channel is selected
    const showChannel = !currentChannel;
    const channelHtml = showChannel ? `<span class="transcript-channel">#${escapeHtml(transcription.channel || 'Unknown')}</span>` : '';

    // Add avatar if available
    const avatarHtml = transcription.user_avatar_url
        ? `<img src="${escapeHtml(transcription.user_avatar_url)}" class="transcript-avatar" alt="${escapeHtml(transcription.user)}" onerror="this.style.display='none'">`
        : '';

    const entry = document.createElement('div');
    entry.className = 'transcript-entry';
    entry.innerHTML = `
        <span class="transcript-timestamp">${timestamp}</span>
        ${guildHtml}
        ${channelHtml}
        <span class="transcript-user">${escapeHtml(transcription.user || 'Unknown')}</span>
        ${avatarHtml}
        <span class="transcript-text">${escapeHtml(transcription.text)}</span>${triggers}
    `;

    // Append to end (newest at bottom)
    container.appendChild(entry);

    // Remove oldest entry if too many displayed
    const entries = container.querySelectorAll('.transcript-entry');
    if (entries.length > 100) {
        entries[0].remove();
    }

    // Auto-scroll to bottom if enabled
    if (autoScroll) {
        container.scrollTop = container.scrollHeight;
    }
}

function updateStats(data) {
    // Update total count
    if (data) {
        document.getElementById('total-transcripts').textContent = (data.total || 0).toLocaleString();
        document.getElementById('filtered-transcripts').textContent = (data.count || 0).toLocaleString();
    }

    // Update last updated time
    document.getElementById('last-updated').textContent = new Date().toLocaleTimeString();
}

function switchToLiveMode() {
    viewMode = 'live';
    currentSession = null;

    // Update button states
    document.getElementById('live-btn').classList.add('active');
    document.getElementById('history-btn').classList.remove('active');

    // Remove history mode class to show live-only elements
    document.body.classList.remove('history-mode');

    // Reload guilds, channels, and data
    loadGuilds();
    loadChannels();
    loadTranscripts();
}

function switchToHistoryMode() {
    viewMode = 'history';

    // Update button states
    document.getElementById('live-btn').classList.remove('active');
    document.getElementById('history-btn').classList.add('active');

    // Add history mode class to hide live-only elements
    document.body.classList.add('history-mode');

    // Reload guilds, channels, and data
    loadGuilds();
    loadChannels();
    loadTranscripts();
}

function displayHistoricalSessions(sessions) {
    const container = document.getElementById('transcripts-content');

    if (!sessions || sessions.length === 0) {
        container.innerHTML = '<div class="transcripts-empty">No historical sessions match the current filters</div>';
        return;
    }

    container.innerHTML = sessions.map(session => {
        const startTime = formatTimestamp(session.start_time);
        const endTime = session.end_time ? formatTimestamp(session.end_time) : 'In Progress';
        const duration = session.duration_seconds
            ? formatDuration(session.duration_seconds)
            : 'N/A';

        return `
            <div class="session-entry" data-session-id="${session.session_id}" onclick="loadSessionTranscript('${session.session_id}')">
                <div class="session-header">
                    <span class="session-time">${startTime}</span>
                    <span class="session-duration">Duration: ${duration}</span>
                </div>
                <div class="session-info">
                    <span class="session-guild">${escapeHtml(session.guild_name)}</span>
                    <span class="session-channel">#${escapeHtml(session.channel_name)}</span>
                    <span class="session-stats">${session.total_messages} messages • ${session.unique_speakers} speakers</span>
                </div>
            </div>
        `;
    }).join('');
}

async function loadSessionTranscript(sessionId) {
    try {
        const response = await fetch(`/api/v1/transcripts/history/session/${sessionId}`);
        const data = await response.json();

        if (!data.success || !data.session) {
            showError('Failed to load session transcript');
            return;
        }

        currentSession = data.session;
        displaySessionTranscript(currentSession);

    } catch (error) {
        console.error('Error loading session transcript:', error);
        showError('Failed to load session transcript');
    }
}

function displaySessionTranscript(session) {
    const container = document.getElementById('transcripts-content');

    if (!session.transcript || session.transcript.length === 0) {
        container.innerHTML = `
            <div class="session-back-btn" onclick="loadHistoricalSessions()">← Back to Sessions</div>
            <div class="transcripts-empty">No transcript entries in this session</div>
        `;
        return;
    }

    // Build transcript HTML
    const transcriptHtml = session.transcript.map(entry => {
        const timestamp = formatTimestamp(entry.timestamp);
        const confidenceBadge = entry.confidence < 0.8
            ? ` <span class="confidence-low">(${Math.round(entry.confidence * 100)}%)</span>`
            : '';

        return `
            <div class="transcript-entry">
                <span class="transcript-timestamp">${timestamp}</span>
                <span class="transcript-user">${escapeHtml(entry.username)}</span>
                <span class="transcript-text">${escapeHtml(entry.text)}</span>${confidenceBadge}
            </div>
        `;
    }).join('');

    // Session header info
    const startTime = formatTimestamp(session.start_time);
    const endTime = session.end_time ? formatTimestamp(session.end_time) : 'In Progress';
    const duration = session.stats?.duration_seconds
        ? formatDuration(session.stats.duration_seconds)
        : 'N/A';

    container.innerHTML = `
        <div class="session-back-btn" onclick="loadHistoricalSessions()">← Back to Sessions</div>
        <div class="session-details">
            <h3>${escapeHtml(session.guild_name)} - #${escapeHtml(session.channel_name)}</h3>
            <div class="session-meta">
                <span>Started: ${startTime}</span>
                <span>Ended: ${endTime}</span>
                <span>Duration: ${duration}</span>
                <span>${session.stats?.total_messages || 0} messages</span>
                <span>${session.stats?.unique_speakers || 0} speakers</span>
            </div>
        </div>
        <div class="transcript-content">
            ${transcriptHtml}
        </div>
    `;

    // Scroll to top
    container.scrollTop = 0;
}

function formatDuration(seconds) {
    if (!seconds || seconds < 0) return 'N/A';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

function updateHistoryStats(data) {
    document.getElementById('total-transcripts').textContent = (data.count || 0).toLocaleString();
    document.getElementById('filtered-transcripts').textContent = (data.count || 0).toLocaleString();
    document.getElementById('last-updated').textContent = new Date().toLocaleTimeString();
}

function showError(message) {
    const container = document.getElementById('transcripts-content');
    container.innerHTML = `<div class="transcripts-empty" style="color: #f04747;">${message}</div>`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

console.log('📝 Transcripts viewer initialized');
