/**
 * Sound Management functionality - Card-based design with modal editor
 */

let sounds = [];
let guilds = [];
let currentSearch = '';
let currentGuild = '';
let currentAudio = null;
let deleteTarget = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadGuilds();
    loadSounds();
    setupEventListeners();
});

function setupEventListeners() {
    // Guild filter
    document.getElementById('guild-filter').addEventListener('change', (e) => {
        currentGuild = e.target.value;
        loadSounds();
    });

    // Search input (with debounce)
    let searchTimeout;
    document.getElementById('sound-search').addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            currentSearch = e.target.value;
            loadSounds();
        }, 300);
    });

    // Upload button
    document.getElementById('upload-btn').addEventListener('click', () => {
        openUploadModal();
    });

    // Close modals on outside click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeAllModals();
            }
        });
    });
}

async function loadGuilds() {
    try {
        const response = await fetch('/api/v1/sounds/guilds');
        const data = await response.json();

        guilds = data.guilds || [];

        // Populate guild filter
        const filterSelect = document.getElementById('guild-filter');
        filterSelect.innerHTML = '<option value="">All Guilds</option>';

        guilds.forEach(guild => {
            const option = document.createElement('option');
            option.value = guild.guild_id;
            option.textContent = `${guild.guild_name} (${guild.sound_count})`;
            filterSelect.appendChild(option);
        });

        // Populate guild selects in modals
        populateGuildSelects();

    } catch (error) {
        console.error('Error loading guilds:', error);
    }
}

function populateGuildSelects() {
    const editSelect = document.getElementById('edit-guild');
    const uploadSelect = document.getElementById('upload-guild');

    [editSelect, uploadSelect].forEach(select => {
        // Keep default "Global" option
        const globalOption = select.querySelector('option[value="default_guild"]');
        select.innerHTML = '';
        select.appendChild(globalOption);

        guilds.forEach(guild => {
            if (guild.guild_id !== 'default_guild') {
                const option = document.createElement('option');
                option.value = guild.guild_id;
                option.textContent = guild.guild_name;
                select.appendChild(option);
            }
        });
    });
}

async function loadSounds() {
    try {
        const params = new URLSearchParams();

        if (currentSearch) {
            params.append('search', currentSearch);
        }

        if (currentGuild) {
            params.append('guild_id', currentGuild);
        }

        const response = await fetch(`/api/v1/sounds/list?${params}`);
        const data = await response.json();

        sounds = data.sounds || [];
        displaySounds(sounds);
        updateStats(data);

    } catch (error) {
        console.error('Error loading sounds:', error);
        showError('Failed to load sounds');
    }
}

function displaySounds(soundList) {
    const grid = document.getElementById('sounds-grid');

    if (!soundList || soundList.length === 0) {
        grid.innerHTML = '<div class="sounds-loading">No sounds found</div>';
        return;
    }

    grid.innerHTML = soundList.map(sound => {
        const triggerTags = sound.triggers.map(t =>
            `<span class="trigger-tag">${escapeHtml(t)}</span>`
        ).join('');

        const disabledClass = sound.is_disabled ? 'disabled' : '';

        return `
            <div class="sound-card ${disabledClass}" onclick="openEditModal('${escapeHtml(sound.id)}')">
                <div class="sound-header">
                    <div>
                        <div class="sound-title">${escapeHtml(sound.title)}</div>
                        <span class="sound-guild">${escapeHtml(sound.guild_name)}</span>
                    </div>
                </div>

                <div class="sound-description">${escapeHtml(sound.description)}</div>

                ${sound.triggers.length > 0 ? `<div class="sound-triggers">${triggerTags}</div>` : ''}

                <div class="sound-meta">
                    <div class="meta-item">
                        <span class="meta-value">${sound.play_count}</span> plays
                    </div>
                    <div class="meta-item">
                        Vol: <span class="meta-value">${sound.volume_adjust.toFixed(1)}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-value">${sound.size_formatted}</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function updateStats(data) {
    document.getElementById('total-sounds').textContent = data.count || 0;
    document.getElementById('total-size').textContent = data.total_size_formatted || '0 B';
}

async function openEditModal(soundId) {
    try {
        // Fetch full sound details
        const response = await fetch(`/api/v1/sounds/${encodeURIComponent(soundId)}`);
        const sound = await response.json();

        // Populate form
        document.getElementById('edit-sound-id').value = sound.id;
        document.getElementById('edit-title').value = sound.title;
        document.getElementById('edit-description').value = sound.description;
        document.getElementById('edit-triggers').value = sound.triggers.join(', ');
        document.getElementById('edit-volume').value = sound.volume_adjust;
        document.getElementById('edit-cooldown').value = sound.cooldown;
        document.getElementById('edit-guild').value = sound.guild_id;
        document.getElementById('edit-disabled').checked = sound.is_disabled;

        // Populate info fields
        document.getElementById('edit-filename').textContent = sound.filename;
        document.getElementById('edit-size').textContent = sound.size_formatted;
        document.getElementById('edit-playcount').textContent = sound.play_count;
        document.getElementById('edit-addedby').textContent = sound.added_by;

        // Show modal
        document.getElementById('edit-modal').classList.add('show');

    } catch (error) {
        console.error('Error loading sound details:', error);
        showNotification('Failed to load sound details', 'error');
    }
}

function closeEditModal() {
    document.getElementById('edit-modal').classList.remove('show');
}

async function saveSound() {
    try {
        const soundId = document.getElementById('edit-sound-id').value;
        const triggers = document.getElementById('edit-triggers').value
            .split(',')
            .map(t => t.trim())
            .filter(t => t);

        const metadata = {
            title: document.getElementById('edit-title').value,
            description: document.getElementById('edit-description').value,
            triggers: triggers,
            volume_adjust: parseFloat(document.getElementById('edit-volume').value),
            cooldown: parseInt(document.getElementById('edit-cooldown').value),
            guild_id: document.getElementById('edit-guild').value,
            is_disabled: document.getElementById('edit-disabled').checked
        };

        const response = await fetch(`/api/v1/sounds/${encodeURIComponent(soundId)}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(metadata)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update sound');
        }

        showNotification('Sound updated successfully', 'success');
        closeEditModal();
        loadSounds();

    } catch (error) {
        console.error('Error saving sound:', error);
        showNotification(`Failed to save: ${error.message}`, 'error');
    }
}

function deleteSoundFromModal() {
    const soundId = document.getElementById('edit-sound-id').value;
    const title = document.getElementById('edit-title').value;

    // Close edit modal and show delete confirmation
    closeEditModal();
    deleteTarget = soundId;
    document.getElementById('delete-sound-title').textContent = title;
    document.getElementById('delete-modal').classList.add('show');
}

function closeDeleteModal() {
    document.getElementById('delete-modal').classList.remove('show');
    deleteTarget = null;
}

async function confirmDelete() {
    if (!deleteTarget) return;

    try {
        const response = await fetch(`/api/v1/sounds/${encodeURIComponent(deleteTarget)}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete sound');
        }

        showNotification('Sound deleted successfully', 'success');
        closeDeleteModal();
        loadSounds();

    } catch (error) {
        console.error('Error deleting sound:', error);
        showNotification(`Failed to delete: ${error.message}`, 'error');
    }
}

function openUploadModal() {
    // Reset form
    document.getElementById('upload-form').reset();
    document.getElementById('upload-progress').style.display = 'none';
    document.getElementById('edit-modal').classList.remove('show');
    document.getElementById('upload-modal').classList.add('show');
}

function closeUploadModal() {
    document.getElementById('upload-modal').classList.remove('show');
}

async function submitUpload() {
    try {
        const fileInput = document.getElementById('upload-file');
        const file = fileInput.files[0];

        if (!file) {
            showNotification('Please select a file', 'error');
            return;
        }

        const title = document.getElementById('upload-title').value;
        if (!title) {
            showNotification('Please enter a title', 'error');
            return;
        }

        // Show progress
        document.getElementById('upload-progress').style.display = 'block';
        document.getElementById('progress-fill').style.width = '0%';
        document.getElementById('upload-status').textContent = 'Uploading...';

        // Build form data
        const formData = new FormData();
        formData.append('file', file);

        // Build query parameters
        const params = new URLSearchParams({
            title: title,
            guild_id: document.getElementById('upload-guild').value,
            description: document.getElementById('upload-description').value,
            triggers: document.getElementById('upload-triggers').value
        });

        const response = await fetch(`/api/v1/sounds/upload?${params}`, {
            method: 'POST',
            body: formData
        });

        // Simulate progress
        document.getElementById('progress-fill').style.width = '100%';

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }

        document.getElementById('upload-status').textContent = 'Upload complete!';

        setTimeout(() => {
            closeUploadModal();
            showNotification('Sound uploaded successfully', 'success');
            loadSounds();
            loadGuilds(); // Refresh guild counts
        }, 1000);

    } catch (error) {
        console.error('Error uploading sound:', error);
        document.getElementById('upload-status').textContent = `Error: ${error.message}`;
        setTimeout(() => {
            document.getElementById('upload-progress').style.display = 'none';
        }, 2000);
        showNotification(`Upload failed: ${error.message}`, 'error');
    }
}

async function playSound(soundId, event) {
    if (event) {
        event.stopPropagation(); // Prevent card click
    }

    try {
        // Stop currently playing audio
        if (currentAudio) {
            currentAudio.pause();
            currentAudio = null;
        }

        // Create and play new audio
        currentAudio = new Audio(`/api/v1/sounds/play/${encodeURIComponent(soundId)}`);
        await currentAudio.play();

        console.log(`Playing sound: ${soundId}`);

    } catch (error) {
        console.error('Error playing sound:', error);
        showNotification('Failed to play sound', 'error');
    }
}

function closeAllModals() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.remove('show');
    });
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;

    // Add to body
    document.body.appendChild(notification);

    // Trigger animation
    setTimeout(() => notification.classList.add('show'), 10);

    // Remove after 3 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

function showError(message) {
    const grid = document.getElementById('sounds-grid');
    grid.innerHTML = `<div class="sounds-loading" style="color: #F04747;">${message}</div>`;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

console.log('🔊 Sound management initialized (card-based design)');
