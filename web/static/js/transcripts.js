/**
 * Transcripts Viewer functionality
 */

let currentGuild = '';
let currentChannel = '';
let currentSearch = '';
let liveMode = false;
let allGuilds = [];
let allChannels = [];
let transcripts = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadGuilds();
    loadTranscripts();
    setupEventListeners();
    setupWebSocket();
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
        currentChannel = e.target.value;
        loadTranscripts();
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
}

function setupWebSocket() {
    // Listen for real-time transcription events via WebSocket
    if (window.wsClient) {
        wsClient.on('transcription', (data) => {
            console.log('Received real-time transcription:', data);
            // Add to transcripts list
            addTranscriptionToView(data.data);
            updateStats();
        });
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

    container.innerHTML = transcriptList.map(t => {
        const timestamp = new Date(t.timestamp).toLocaleString();
        const triggers = t.triggers && t.triggers.length > 0
            ? `<div class="transcript-triggers">Triggers: ${t.triggers.map(tr => `<span class="trigger-badge">${escapeHtml(tr.word)} → ${escapeHtml(tr.sound)}</span>`).join(' ')}</div>`
            : '';

        return `
            <div class="transcript-entry">
                <div class="transcript-header">
                    <span class="transcript-timestamp">${timestamp}</span>
                    <span class="transcript-guild">${escapeHtml(t.guild || 'Unknown')}</span>
                    <span class="transcript-channel">#${escapeHtml(t.channel || 'Unknown')}</span>
                    <span class="transcript-user">${escapeHtml(t.user || 'Unknown')}</span>
                </div>
                <div class="transcript-text">${escapeHtml(t.text)}</div>
                ${triggers}
            </div>
        `;
    }).join('');
}

function addTranscriptionToView(transcription) {
    // Only add if it matches current filters
    // IDs are now strings from backend for JavaScript compatibility
    if (currentGuild && transcription.guild_id !== currentGuild) return;
    if (currentChannel && transcription.channel_id !== currentChannel) return;
    if (currentSearch) {
        const searchLower = currentSearch.toLowerCase();
        if (!transcription.text.toLowerCase().includes(searchLower) &&
            !transcription.user.toLowerCase().includes(searchLower)) {
            return;
        }
    }

    // Add to beginning of transcripts array
    transcripts.unshift(transcription);

    // Keep only last 100
    if (transcripts.length > 100) {
        transcripts = transcripts.slice(0, 100);
    }

    // Re-display
    displayTranscripts(transcripts);
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
