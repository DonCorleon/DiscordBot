/**
 * Dashboard logic and data handling
 */

// Handle initial data load
wsClient.on('init', (data) => {
    console.log('Received initial data:', data);
    if (data.data) {
        updateDashboard(data.data);
    }
});

// Handle real-time updates
wsClient.on('update', (data) => {
    if (data.data) {
        updateDashboard(data.data);
    }
});

// Handle real-time command events
wsClient.on('command', (data) => {
    addToActivityFeed('command', data.data, data.timestamp);
    addToRecentCommands(data.data, data.timestamp);
});

// Handle real-time message events (if implemented)
wsClient.on('message', (data) => {
    addToActivityFeed('message', data.data, data.timestamp);
});

function updateDashboard(data) {
    // Update bot status
    updateBotStatus(data);

    // Update system resources
    updateSystemResources(data);

    // Update voice channels
    updateVoiceChannels(data);

    // Update charts
    if (window.updateCommandsChart && data.commands) {
        updateCommandsChart(data.commands);
    }
}

function updateBotStatus(data) {
    // Get bot info from summary
    const botInfo = data.summary?.bot_info;

    if (!botInfo) {
        console.log('No bot info available');
        return;
    }

    console.log('Bot info:', botInfo);

    // Update guild count
    const guildEl = document.getElementById('guild-count');
    if (guildEl && botInfo.guilds !== undefined) {
        guildEl.textContent = botInfo.guilds;
    }

    // Update user count
    const userEl = document.getElementById('user-count');
    if (userEl && botInfo.users !== undefined) {
        userEl.textContent = botInfo.users.toLocaleString();
    }

    // Update uptime
    const uptimeEl = document.getElementById('uptime');
    if (uptimeEl) {
        if (botInfo.uptime) {
            uptimeEl.textContent = botInfo.uptime;
        } else {
            uptimeEl.textContent = 'N/A';
        }
    }

    // Update latency
    const latencyEl = document.getElementById('latency');
    if (latencyEl) {
        if (botInfo.latency_ms !== null && botInfo.latency_ms !== undefined) {
            latencyEl.textContent = `${botInfo.latency_ms} ms`;
        } else {
            latencyEl.textContent = 'N/A';
        }
    }
}

function updateSystemResources(data) {
    // Get health data from either health.json or summary.json
    let healthData = null;

    if (data.health?.current) {
        healthData = data.health.current;
    } else if (data.summary?.health) {
        healthData = data.summary.health;
    }

    if (!healthData) return;

    console.log('Health data:', healthData);

    // Update CPU
    const cpuEl = document.getElementById('cpu-usage');
    if (cpuEl && healthData.cpu_percent !== undefined) {
        cpuEl.textContent = `${healthData.cpu_percent.toFixed(1)}%`;
    }

    // Update Memory
    const memEl = document.getElementById('memory-usage');
    if (memEl && healthData.memory_mb !== undefined) {
        const memPercent = healthData.memory_percent || 0;
        memEl.textContent = `${healthData.memory_mb.toFixed(1)} MB`;
    }

    // Update voice connections
    const connEl = document.getElementById('voice-connections');
    if (connEl && healthData.active_connections !== undefined) {
        connEl.textContent = healthData.active_connections;
    }
}

function updateVoiceChannels(data) {
    const container = document.getElementById('voice-channels');
    if (!container) return;

    // connections.json has a 'connections' array
    const connections = data.connections?.connections;

    if (!connections || connections.length === 0) {
        container.innerHTML = '<div class="voice-empty">No active connections</div>';
        return;
    }

    console.log('Voice connections:', connections);

    container.innerHTML = connections.map(conn => `
        <div class="voice-item">
            <div class="guild-name">${escapeHtml(conn.guild_name)}</div>
            <div class="channel-name">📢 ${escapeHtml(conn.channel_name)}</div>
            <div class="members">👥 ${conn.members_count} member${conn.members_count !== 1 ? 's' : ''}</div>
            <div class="status">
                ${conn.is_listening ? '<span class="voice-badge listening">🎧 Listening</span>' : ''}
                ${conn.is_playing ? '<span class="voice-badge playing">▶️ Playing</span>' : ''}
                ${conn.queue_size > 0 ? `<span class="voice-badge">🎵 Queue: ${conn.queue_size}</span>` : ''}
            </div>
        </div>
    `).join('');
}

function addToActivityFeed(type, data, timestamp) {
    const feed = document.getElementById('activity-feed');
    if (!feed) return;

    // Remove empty message if it exists
    const empty = feed.querySelector('.feed-empty');
    if (empty) empty.remove();

    const item = document.createElement('div');
    item.className = `feed-item feed-${type}`;

    const time = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();

    if (type === 'message') {
        item.innerHTML = `
            <span class="time">${time}</span>
            <span class="user">${escapeHtml(data.author)}</span>: ${escapeHtml(data.content)}
        `;
    } else if (type === 'command') {
        const statusIcon = data.success ? '✅' : '❌';
        item.innerHTML = `
            <span class="time">${time}</span>
            <span class="command">~${escapeHtml(data.name)}</span>
            <span style="margin-left: 0.5rem;">${statusIcon}</span>
        `;
    }

    feed.insertBefore(item, feed.firstChild);

    // Keep only last 50 items
    while (feed.children.length > 50) {
        feed.removeChild(feed.lastChild);
    }
}

function addToRecentCommands(data, timestamp) {
    const container = document.getElementById('recent-commands');
    if (!container) return;

    // Remove empty message if it exists
    const empty = container.querySelector('.commands-empty');
    if (empty) empty.remove();

    const item = document.createElement('div');
    item.className = 'command-item';

    const time = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();

    item.innerHTML = `
        <div>
            <div class="cmd-name">~${escapeHtml(data.name)}</div>
            <div class="cmd-time">${time}</div>
        </div>
        <div class="cmd-status">${data.success ? '✅' : '❌'}</div>
    `;

    container.insertBefore(item, container.firstChild);

    // Keep only last 10 commands
    while (container.children.length > 10) {
        container.removeChild(container.lastChild);
    }
}

function formatUptime(seconds) {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (days > 0) {
        return `${days}d ${hours}h ${minutes}m`;
    } else if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else {
        return `${minutes}m`;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Log when dashboard is ready
console.log('📊 Dashboard initialized');
