/**
 * Transcripts Viewer functionality
 */

let currentGuild = '';
let currentChannel = '';
let currentSearch = '';
let liveMode = false;
let autoScroll = true;
let allGuilds = [];
let allChannels = [];
let transcripts = [];

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
        loadTranscripts();
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
            loadTranscripts();
        } else {
            currentChannel = e.target.value;
            loadTranscripts();
        }
    });

    // Search input (with debounce)
    let searchTimeout;
    document.getElementById('transcript-search').addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            currentSearch = e.target.value;
            loadTranscripts();
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
        toggleLiveMode();
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
        const response = await fetch('/api/v1/transcripts/guilds');
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
            const response = await fetch('/api/v1/transcripts/all-channels');
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
        const response = await fetch(`/api/v1/transcripts/channels?guild_id=${currentGuild}`);
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

function displayTranscripts(transcriptList) {
    const container = document.getElementById('transcripts-content');

    if (!transcriptList || transcriptList.length === 0) {
        container.innerHTML = '<div class="transcripts-empty">No transcriptions match the current filters</div>';
        return;
    }

    // Reverse to show oldest first (newest at bottom)
    const reversed = [...transcriptList].reverse();

    container.innerHTML = reversed.map(t => {
        const timestamp = new Date(t.timestamp).toLocaleString();
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
    console.log('Current filters - Guild:', currentGuild, 'Channel:', currentChannel, 'Search:', currentSearch);

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

    const timestamp = new Date(transcription.timestamp).toLocaleString();
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

function toggleLiveMode() {
    liveMode = !liveMode;
    const btn = document.getElementById('live-btn');

    if (liveMode) {
        btn.classList.add('active');
        btn.textContent = '⏸️ Pause';
    } else {
        btn.classList.remove('active');
        btn.textContent = '▶️ Live';
    }
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
