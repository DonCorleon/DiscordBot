/**
 * Configuration Editor functionality
 */

let allSettings = {};
let pendingUpdate = null;
let currentMode = 'global'; // 'global' or 'guild'
let selectedGuildId = null;
let guilds = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadGuilds();
    loadConfiguration();
    setupEventListeners();
});

function setupEventListeners() {
    document.getElementById('backup-btn').addEventListener('click', createBackup);
    document.getElementById('restore-btn').addEventListener('click', restoreBackup);
    document.getElementById('refresh-btn').addEventListener('click', loadConfiguration);
}

async function loadGuilds() {
    try {
        const response = await fetch('/api/v1/config/guilds/list');
        const data = await response.json();

        if (data.guilds && data.guilds.length > 0) {
            guilds = data.guilds;
            populateGuildSelector();
            console.log(`Loaded ${guilds.length} guilds`);
        } else {
            console.warn('No guilds available');
            const select = document.getElementById('guild-select');
            select.innerHTML = '<option value="">No guilds available</option>';
        }
    } catch (error) {
        console.error('Error loading guilds:', error);
        const select = document.getElementById('guild-select');
        select.innerHTML = '<option value="">Failed to load guilds</option>';
    }
}

function populateGuildSelector() {
    const select = document.getElementById('guild-select');

    if (guilds.length === 0) {
        select.innerHTML = '<option value="">No guilds available</option>';
        return;
    }

    select.innerHTML = guilds.map(guild =>
        `<option value="${guild.id}">${escapeHtml(guild.name)} (${guild.member_count} members)</option>`
    ).join('');

    // Select first guild by default
    if (guilds.length > 0) {
        selectedGuildId = guilds[0].id;
        select.value = selectedGuildId;
    }
}

function switchToGlobalMode() {
    currentMode = 'global';
    document.getElementById('global-mode-btn').classList.add('active');
    document.getElementById('guild-mode-btn').classList.remove('active');
    document.getElementById('guild-selector-container').style.display = 'none';

    // Hide backup/restore buttons in guild mode (they're for global config only)
    document.getElementById('backup-btn').style.display = 'block';
    document.getElementById('restore-btn').style.display = 'block';

    loadConfiguration();
}

function switchToGuildMode() {
    currentMode = 'guild';
    document.getElementById('global-mode-btn').classList.remove('active');
    document.getElementById('guild-mode-btn').classList.add('active');
    document.getElementById('guild-selector-container').style.display = 'flex';

    // Hide backup/restore buttons in guild mode
    document.getElementById('backup-btn').style.display = 'none';
    document.getElementById('restore-btn').style.display = 'none';

    loadGuildConfig();
}

async function loadConfiguration() {
    if (currentMode === 'guild') {
        return loadGuildConfig();
    }

    try {
        const response = await fetch('/api/v1/config/');
        const data = await response.json();

        allSettings = data.categories;
        displayConfiguration(data.categories);
        updateStats(data);

    } catch (error) {
        console.error('Error loading configuration:', error);
        showNotification('Failed to load configuration', 'error');
    }
}

async function loadGuildConfig() {
    selectedGuildId = document.getElementById('guild-select').value;

    if (!selectedGuildId) {
        showNotification('Please select a guild', 'warning');
        return;
    }

    try {
        const response = await fetch(`/api/v1/config/guild/${selectedGuildId}`);
        const data = await response.json();

        allSettings = data.categories;
        displayGuildConfiguration(data.categories, data.guild_id);
        updateStats(data);

    } catch (error) {
        console.error('Error loading guild configuration:', error);
        showNotification('Failed to load guild configuration', 'error');
    }
}

function displayConfiguration(categories) {
    const container = document.getElementById('config-categories');

    container.innerHTML = Object.keys(categories).map(categoryName => {
        const settings = categories[categoryName];

        return `
            <div class="category-section">
                <div class="category-header">${escapeHtml(categoryName)}</div>
                <div class="settings-grid">
                    ${Object.keys(settings).map(key => {
                        const setting = settings[key];
                        return renderSetting(key, setting);
                    }).join('')}
                </div>
            </div>
        `;
    }).join('');

    // Attach event listeners to controls
    attachControlListeners();
}

function displayGuildConfiguration(categories, guildId) {
    const container = document.getElementById('config-categories');

    container.innerHTML = Object.keys(categories).map(categoryName => {
        const settings = categories[categoryName];

        return `
            <div class="category-section">
                <div class="category-header">${escapeHtml(categoryName)}</div>
                <div class="settings-grid">
                    ${Object.keys(settings).map(key => {
                        const setting = settings[key];
                        return renderGuildSetting(key, setting, guildId);
                    }).join('')}
                </div>
            </div>
        `;
    }).join('');

    // Attach event listeners to controls
    attachControlListeners();
    attachGuildResetListeners();
}

function renderSetting(key, setting) {
    const restartClass = setting.requires_restart ? 'restart-required' : '';
    const restartBadge = setting.requires_restart ? '<span class="restart-badge">RESTART</span>' : '';

    // Build tooltip text
    let tooltip = setting.description || key.replace(/_/g, ' ');
    if (setting.type) tooltip += `\nType: ${setting.type}`;
    if (setting.min !== null) tooltip += `\nMin: ${setting.min}`;
    if (setting.max !== null) tooltip += `\nMax: ${setting.max}`;
    if (setting.choices) tooltip += `\nChoices: ${setting.choices.join(', ')}`;

    const control = renderControl(key, setting);

    return `
        <div class="setting-item ${restartClass}" data-key="${escapeHtml(key)}">
            <div class="setting-info" title="${escapeHtml(tooltip)}">
                <div class="setting-name">
                    ${escapeHtml(key)}
                    ${restartBadge}
                </div>
            </div>
            <div class="setting-control">
                ${control}
            </div>
        </div>
    `;
}

function renderGuildSetting(key, settingData, guildId) {
    const { value, is_override, global_default, type, description, min, max, choices } = settingData;

    const overrideBadge = is_override
        ? '<span class="guild-override-badge">✏️</span>'
        : '<span class="global-default-badge">🌐</span>';

    const resetButton = is_override
        ? `<button class="reset-guild-btn" data-key="${escapeHtml(key)}" data-guild="${guildId}" title="Reset to global default">↺</button>`
        : '';

    // Build tooltip
    let tooltip = description || key.replace(/_/g, ' ');
    tooltip += `\nCurrent: ${value}`;
    if (!is_override) {
        tooltip += '\nUsing global default';
    } else {
        tooltip += `\nGlobal default: ${global_default}`;
        tooltip += '\n✏️ = Guild override';
    }
    if (choices) tooltip += `\nChoices: ${choices.join(', ')}`;
    if (min !== null && min !== undefined) tooltip += `\nMin: ${min}`;
    if (max !== null && max !== undefined) tooltip += `\nMax: ${max}`;

    // Create a full setting object with all metadata for renderControl
    const setting = {
        type: type,
        value: value,
        choices: choices,
        min: min,
        max: max
    };

    const control = renderControl(key, setting);

    return `
        <div class="setting-item" data-key="${escapeHtml(key)}">
            <div class="setting-info" title="${escapeHtml(tooltip)}">
                <div class="setting-name">
                    ${escapeHtml(key)}
                    ${overrideBadge}
                </div>
            </div>
            <div class="setting-control">
                ${control}
                ${resetButton}
            </div>
        </div>
    `;
}

function renderControl(key, setting) {
    const value = setting.value;

    if (setting.type === 'boolean' || setting.type === 'bool') {
        return `<input type="checkbox" data-key="${escapeHtml(key)}" ${value ? 'checked' : ''}>`;
    }

    if (setting.choices) {
        return `
            <select data-key="${escapeHtml(key)}">
                ${setting.choices.map(choice => `
                    <option value="${escapeHtml(choice)}" ${value === choice ? 'selected' : ''}>
                        ${escapeHtml(choice)}
                    </option>
                `).join('')}
            </select>
        `;
    }

    if (setting.type === 'number' || setting.type === 'int' || setting.type === 'float') {
        const step = (setting.type === 'float' || (setting.type === 'number' && !Number.isInteger(value))) ? '0.1' : '1';
        return `
            <input type="number"
                   data-key="${escapeHtml(key)}"
                   value="${value}"
                   step="${step}"
                   ${setting.min !== null && setting.min !== undefined ? `min="${setting.min}"` : ''}
                   ${setting.max !== null && setting.max !== undefined ? `max="${setting.max}"` : ''}>
        `;
    }

    // String or list
    const displayValue = Array.isArray(value) ? value.join(', ') : value;
    return `<input type="text" data-key="${escapeHtml(key)}" value="${escapeHtml(displayValue)}">`;
}

function attachControlListeners() {
    // Checkboxes
    document.querySelectorAll('.setting-control input[type="checkbox"]').forEach(input => {
        input.addEventListener('change', (e) => {
            const key = e.target.dataset.key;
            const value = e.target.checked;
            requestUpdate(key, value);
        });
    });

    // Number inputs
    document.querySelectorAll('.setting-control input[type="number"]').forEach(input => {
        input.addEventListener('change', (e) => {
            const key = e.target.dataset.key;
            let value = parseFloat(e.target.value);
            if (e.target.step === '1') value = parseInt(e.target.value);
            requestUpdate(key, value);
        });
    });

    // Text inputs
    document.querySelectorAll('.setting-control input[type="text"]').forEach(input => {
        input.addEventListener('change', (e) => {
            const key = e.target.dataset.key;
            const value = e.target.value;
            requestUpdate(key, value);
        });
    });

    // Select dropdowns
    document.querySelectorAll('.setting-control select').forEach(select => {
        select.addEventListener('change', (e) => {
            const key = e.target.dataset.key;
            const value = e.target.value;
            requestUpdate(key, value);
        });
    });
}

function requestUpdate(key, value) {
    // Find setting info
    const setting = findSetting(key);
    if (!setting) {
        showNotification('Setting not found', 'error');
        return;
    }

    // Store pending update
    pendingUpdate = { key, value };

    // Show confirmation modal
    document.getElementById('confirm-key').textContent = key;
    document.getElementById('confirm-value').textContent = JSON.stringify(value);

    if (setting.requires_restart) {
        document.getElementById('confirm-message').textContent =
            'This setting requires a bot restart. Are you sure you want to update it?';
    } else {
        document.getElementById('confirm-message').textContent =
            'This setting will be applied immediately. Continue?';
    }

    document.getElementById('confirm-modal').classList.add('show');
}

async function confirmUpdate() {
    if (!pendingUpdate) return;

    // Save pending update before closing modal (which clears it)
    const updateData = { ...pendingUpdate };

    closeConfirmModal();

    try {
        let url, method;

        if (currentMode === 'guild') {
            url = `/api/v1/config/guild/${selectedGuildId}`;
            method = 'PATCH';
        } else {
            url = '/api/v1/config/';
            method = 'PATCH';
        }

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(updateData)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Update failed');
        }

        showNotification(result.message, 'success');

        // If restart required, show restart modal (only for global config)
        if (result.requires_restart && currentMode === 'global') {
            document.getElementById('restart-setting').textContent = updateData.key;
            document.getElementById('restart-modal').classList.add('show');
        }

        // Reload configuration to reflect changes
        await loadConfiguration();

    } catch (error) {
        console.error('Error updating setting:', error);
        showNotification(`Failed to update: ${error.message}`, 'error');

        // Reload to revert UI
        await loadConfiguration();
    }
}

function closeConfirmModal() {
    document.getElementById('confirm-modal').classList.remove('show');
    pendingUpdate = null;

    // Reload to reset controls
    loadConfiguration();
}

function closeRestartModal() {
    document.getElementById('restart-modal').classList.remove('show');
}

async function createBackup() {
    try {
        const response = await fetch('/api/v1/config/backup', {
            method: 'POST'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Backup failed');
        }

        showNotification(result.message, 'success');

    } catch (error) {
        console.error('Error creating backup:', error);
        showNotification(`Failed to create backup: ${error.message}`, 'error');
    }
}

async function restoreBackup() {
    if (!confirm('Are you sure you want to restore from backup? This will revert all recent changes.')) {
        return;
    }

    try {
        const response = await fetch('/api/v1/config/restore', {
            method: 'POST'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Restore failed');
        }

        showNotification(result.message, 'success');

        // Reload configuration
        await loadConfiguration();

    } catch (error) {
        console.error('Error restoring backup:', error);
        showNotification(`Failed to restore backup: ${error.message}`, 'error');
    }
}

function findSetting(key) {
    for (const category in allSettings) {
        if (key in allSettings[category]) {
            return allSettings[category][key];
        }
    }
    return null;
}

function updateStats(data) {
    document.getElementById('total-settings').textContent = data.total_settings || 0;

    // Count modified settings (would need to track this separately)
    document.getElementById('modified-count').textContent = '0';
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => notification.classList.add('show'), 10);

    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

function attachGuildResetListeners() {
    document.querySelectorAll('.reset-guild-btn').forEach(button => {
        button.addEventListener('click', async (e) => {
            const key = e.target.dataset.key;
            const guildId = e.target.dataset.guild;
            await resetGuildSetting(key, guildId);
        });
    });
}

async function resetGuildSetting(key, guildId) {
    if (!confirm(`Are you sure you want to reset "${key}" to the global default for this guild?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/v1/config/guild/${guildId}/${key}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Reset failed');
        }

        showNotification(result.message, 'success');

        // Reload configuration to reflect changes
        await loadGuildConfig();

    } catch (error) {
        console.error('Error resetting guild setting:', error);
        showNotification(`Failed to reset: ${error.message}`, 'error');
    }
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

console.log('⚙️ Configuration editor initialized');
