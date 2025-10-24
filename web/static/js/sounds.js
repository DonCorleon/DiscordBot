/**
 * Sound Management functionality
 */

let sounds = [];
let currentSearch = '';
let deleteTarget = null;
let currentAudio = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadSounds();
    setupEventListeners();
});

function setupEventListeners() {
    // Search input (with debounce)
    let searchTimeout;
    document.getElementById('sound-search').addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            currentSearch = e.target.value;
            loadSounds();
        }, 300);
    });

    // File upload
    document.getElementById('file-upload').addEventListener('change', handleFileSelect);

    // Drag and drop
    const dropZone = document.getElementById('drag-drop-zone');
    dropZone.addEventListener('dragover', handleDragOver);
    dropZone.addEventListener('dragleave', handleDragLeave);
    dropZone.addEventListener('drop', handleDrop);

    // Delete modal buttons
    document.getElementById('confirm-delete-btn').addEventListener('click', confirmDelete);
    document.getElementById('cancel-delete-btn').addEventListener('click', closeDeleteModal);

    // Close modal on outside click
    document.getElementById('delete-modal').addEventListener('click', (e) => {
        if (e.target.id === 'delete-modal') {
            closeDeleteModal();
        }
    });
}

async function loadSounds() {
    try {
        const params = new URLSearchParams();

        if (currentSearch) {
            params.append('search', currentSearch);
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
    const tbody = document.getElementById('sounds-tbody');

    if (!soundList || soundList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="sounds-loading">No sounds found</td></tr>';
        return;
    }

    tbody.innerHTML = soundList.map(sound => {
        return `
            <tr data-filename="${escapeHtml(sound.filename)}">
                <td class="sound-filename">${escapeHtml(sound.filename)}</td>
                <td>${sound.size_formatted}</td>
                <td>${sound.play_count}</td>
                <td>
                    <div class="volume-control">
                        <input
                            type="number"
                            class="volume-input"
                            value="${sound.volume}"
                            min="0"
                            max="2"
                            step="0.1"
                            data-filename="${escapeHtml(sound.filename)}"
                        >
                    </div>
                </td>
                <td>
                    <div class="action-buttons">
                        <button class="btn-play" onclick="playSound('${escapeHtml(sound.filename)}')">
                            ▶️ Play
                        </button>
                        <button class="btn-delete" onclick="showDeleteModal('${escapeHtml(sound.filename)}')">
                            🗑️ Delete
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    // Add volume change listeners
    document.querySelectorAll('.volume-input').forEach(input => {
        let debounceTimer;
        input.addEventListener('change', (e) => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                updateVolume(e.target.dataset.filename, parseFloat(e.target.value));
            }, 500);
        });
    });
}

function updateStats(data) {
    document.getElementById('total-sounds').textContent = data.count || 0;
    document.getElementById('total-size').textContent = data.total_size_formatted || '0 B';
}

async function playSound(filename) {
    try {
        // Stop currently playing audio
        if (currentAudio) {
            currentAudio.pause();
            currentAudio = null;
        }

        // Create and play new audio
        currentAudio = new Audio(`/api/v1/sounds/play/${encodeURIComponent(filename)}`);
        await currentAudio.play();

        console.log(`Playing sound: ${filename}`);

    } catch (error) {
        console.error('Error playing sound:', error);
        showNotification('Failed to play sound', 'error');
    }
}

async function updateVolume(filename, volume) {
    try {
        const response = await fetch(`/api/v1/sounds/${encodeURIComponent(filename)}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ volume })
        });

        if (!response.ok) {
            throw new Error('Failed to update volume');
        }

        console.log(`Updated volume for ${filename}: ${volume}`);
        showNotification(`Volume updated for ${filename}`, 'success');

    } catch (error) {
        console.error('Error updating volume:', error);
        showNotification('Failed to update volume', 'error');
        loadSounds(); // Reload to reset volume input
    }
}

function handleFileSelect(event) {
    const files = event.target.files;
    if (files.length > 0) {
        uploadFile(files[0]);
    }
}

function handleDragOver(event) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.add('drag-over');
}

function handleDragLeave(event) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.remove('drag-over');
}

function handleDrop(event) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.remove('drag-over');

    const files = event.dataTransfer.files;
    if (files.length > 0) {
        uploadFile(files[0]);
    }
}

async function uploadFile(file) {
    // Validate file type
    const allowedExtensions = ['.mp3', '.wav', '.ogg', '.m4a', '.flac'];
    const fileExt = '.' + file.name.split('.').pop().toLowerCase();

    if (!allowedExtensions.includes(fileExt)) {
        showNotification(`Invalid file type. Allowed: ${allowedExtensions.join(', ')}`, 'error');
        return;
    }

    // Show upload modal
    const uploadModal = document.getElementById('upload-modal');
    const progressFill = document.getElementById('progress-fill');
    const uploadStatus = document.getElementById('upload-status');

    uploadModal.classList.add('show');
    uploadStatus.textContent = `Uploading ${file.name}...`;
    progressFill.style.width = '0%';

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/api/v1/sounds/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Upload failed');
        }

        // Simulate progress (since we can't track real upload progress easily)
        progressFill.style.width = '100%';
        uploadStatus.textContent = 'Upload complete!';

        setTimeout(() => {
            uploadModal.classList.remove('show');
            showNotification(`Successfully uploaded ${file.name}`, 'success');
            loadSounds(); // Reload sounds list
        }, 1000);

    } catch (error) {
        console.error('Error uploading file:', error);
        uploadStatus.textContent = `Error: ${error.message}`;

        setTimeout(() => {
            uploadModal.classList.remove('show');
            showNotification(`Failed to upload: ${error.message}`, 'error');
        }, 2000);
    }

    // Reset file input
    document.getElementById('file-upload').value = '';
}

function showDeleteModal(filename) {
    deleteTarget = filename;
    document.getElementById('delete-filename').textContent = filename;
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

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Delete failed');
        }

        showNotification(`Successfully deleted ${deleteTarget}`, 'success');
        closeDeleteModal();
        loadSounds(); // Reload sounds list

    } catch (error) {
        console.error('Error deleting sound:', error);
        showNotification(`Failed to delete: ${error.message}`, 'error');
    }
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
    const tbody = document.getElementById('sounds-tbody');
    tbody.innerHTML = `<tr><td colspan="5" class="sounds-loading" style="color: #F04747;">${message}</td></tr>`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

console.log('🔊 Sound management initialized');
