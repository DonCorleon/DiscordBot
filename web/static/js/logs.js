/**
 * Logs Viewer functionality
 */

let currentFile = null;
let currentLevel = 'ALL';
let currentSearch = '';
let liveMode = false;
let autoScroll = true;
let liveInterval = null;
let allLogFiles = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadLogFiles();
    setupEventListeners();
});

function setupEventListeners() {
    // File selection
    document.getElementById('log-file-select').addEventListener('change', (e) => {
        currentFile = e.target.value;
        if (currentFile) {
            loadLogs();
        }
    });

    // Level filter
    document.getElementById('log-level-select').addEventListener('change', (e) => {
        currentLevel = e.target.value;
        if (currentFile) {
            loadLogs();
        }
    });

    // Search input (with debounce)
    let searchTimeout;
    document.getElementById('log-search').addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            currentSearch = e.target.value;
            if (currentFile) {
                loadLogs();
            }
        }, 500);
    });

    // Refresh button
    document.getElementById('refresh-btn').addEventListener('click', () => {
        if (currentFile) {
            loadLogs();
        }
    });

    // Download button
    document.getElementById('download-btn').addEventListener('click', () => {
        if (currentFile) {
            downloadLog();
        }
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

async function loadLogFiles() {
    try {
        const response = await fetch('/api/v1/logs/files');
        const data = await response.json();

        allLogFiles = data.files;

        const select = document.getElementById('log-file-select');
        select.innerHTML = '';

        if (data.files.length === 0) {
            select.innerHTML = '<option value="">No log files found</option>';
            return;
        }

        data.files.forEach(file => {
            const option = document.createElement('option');
            option.value = file.name;
            option.textContent = `${file.name} (${formatFileSize(file.size)})`;
            select.appendChild(option);
        });

        // Auto-select first (most recent) file
        if (data.files.length > 0) {
            currentFile = data.files[0].name;
            select.value = currentFile;
            loadLogs();
        }

    } catch (error) {
        console.error('Error loading log files:', error);
        showError('Failed to load log files');
    }
}

async function loadLogs() {
    try {
        const params = new URLSearchParams({
            file: currentFile,
            tail: 'true',
            lines: '500'
        });

        if (currentLevel !== 'ALL') {
            params.append('level', currentLevel);
        }

        if (currentSearch) {
            params.append('search', currentSearch);
        }

        const response = await fetch(`/api/v1/logs/read?${params}`);
        const data = await response.json();

        displayLogs(data.logs);
        updateStats(data);

    } catch (error) {
        console.error('Error loading logs:', error);
        showError('Failed to load logs');
    }
}

function displayLogs(logs) {
    const container = document.getElementById('logs-content');

    if (!logs || logs.length === 0) {
        container.innerHTML = '<div class="logs-empty">No logs match the current filters</div>';
        return;
    }

    container.innerHTML = logs.map(log => {
        const level = log.level || 'UNKNOWN';
        const fullMessage = log.message || '';
        // Use the raw log line if available, otherwise construct it
        const fullText = log.raw || `${log.timestamp ? '[' + log.timestamp + '] ' : ''}[${level}] ${log.logger ? log.logger + ': ' : ''}${fullMessage}`;

        // Escape for attribute - replace double quotes with single quotes to avoid breaking the title attribute
        const titleText = fullText.replace(/"/g, "'");

        return `
            <div class="log-entry ${level}" title="${escapeHtml(titleText)}">
                ${log.timestamp ? `<span class="log-timestamp">[${log.timestamp}]</span>` : ''}
                <span class="log-level">[${level}]</span>
                ${log.logger ? `<span class="log-logger">${escapeHtml(log.logger)}:</span>` : ''}
                <span class="log-message">${escapeHtml(log.message)}</span>
            </div>
        `;
    }).join('');

    // Auto-scroll to bottom if enabled
    if (autoScroll) {
        container.scrollTop = container.scrollHeight;
    }
}

function updateStats(data) {
    // Update total lines
    document.getElementById('total-lines').textContent = data.count.toLocaleString();

    // Update file info
    const fileInfo = allLogFiles.find(f => f.name === currentFile);
    if (fileInfo) {
        document.getElementById('file-size').textContent = formatFileSize(fileInfo.size);
        document.getElementById('last-modified').textContent = formatDate(new Date(fileInfo.modified * 1000));
    }
}

function toggleLiveMode() {
    liveMode = !liveMode;
    const btn = document.getElementById('live-btn');

    if (liveMode) {
        btn.classList.add('active');
        btn.textContent = '⏸️ Pause';
        startLiveMode();
    } else {
        btn.classList.remove('active');
        btn.textContent = '▶️ Live';
        stopLiveMode();
    }
}

function startLiveMode() {
    // Refresh logs every 2 seconds
    liveInterval = setInterval(() => {
        if (currentFile) {
            loadLogs();
        }
    }, 2000);
}

function stopLiveMode() {
    if (liveInterval) {
        clearInterval(liveInterval);
        liveInterval = null;
    }
}

function downloadLog() {
    window.open(`/api/v1/logs/download/${currentFile}`, '_blank');
}

function showError(message) {
    const container = document.getElementById('logs-content');
    container.innerHTML = `<div class="logs-empty" style="color: #f04747;">${message}</div>`;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

function formatDate(date) {
    return date.toLocaleString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopLiveMode();
});

console.log('📄 Logs viewer initialized');
