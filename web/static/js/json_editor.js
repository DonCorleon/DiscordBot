/**
 * JSON Editor - Generic JSON file editor with table view
 * Supports sorting, filtering, inline editing, bulk operations
 */

class JSONEditor {
    constructor() {
        this.currentFile = null;
        this.currentData = null;
        this.originalData = null;
        this.selectedRows = new Set();
        this.sortColumn = null;
        this.sortDirection = 'asc';
        this.searchTerm = '';
        this.filterCategory = '';
        this.filterType = '';
        this.hasUnsavedChanges = false;

        this.init();
    }

    async init() {
        this.setupEventListeners();
        await this.loadFileList();
    }

    setupEventListeners() {
        // File selection
        document.getElementById('file-select').addEventListener('change', (e) => {
            this.loadFile(e.target.value);
        });

        document.getElementById('reload-file').addEventListener('click', () => {
            if (this.currentFile) {
                this.loadFile(this.currentFile);
            }
        });

        // Toolbar actions
        document.getElementById('add-row').addEventListener('click', () => this.addNewRow());
        document.getElementById('add-field').addEventListener('click', () => this.showAddFieldModal());
        document.getElementById('delete-selected').addEventListener('click', () => this.deleteSelected());
        document.getElementById('export-json').addEventListener('click', () => this.exportJSON());
        document.getElementById('import-json').addEventListener('click', () => {
            document.getElementById('import-file').click();
        });
        document.getElementById('import-file').addEventListener('change', (e) => this.importJSON(e));
        document.getElementById('save-changes').addEventListener('click', () => this.saveChanges());

        // Search and filters
        document.getElementById('search-box').addEventListener('input', (e) => {
            this.searchTerm = e.target.value.toLowerCase();
            this.renderTable();
        });

        document.getElementById('filter-category').addEventListener('change', (e) => {
            this.filterCategory = e.target.value;
            this.renderTable();
        });

        document.getElementById('filter-type').addEventListener('change', (e) => {
            this.filterType = e.target.value;
            this.renderTable();
        });

        // Modal event listeners
        document.getElementById('modal-close').addEventListener('click', () => this.hideAddFieldModal());
        document.getElementById('modal-cancel').addEventListener('click', () => this.hideAddFieldModal());
        document.getElementById('modal-add').addEventListener('click', () => this.addField());

        // Close modal on background click
        document.getElementById('add-field-modal').addEventListener('click', (e) => {
            if (e.target.id === 'add-field-modal') {
                this.hideAddFieldModal();
            }
        });

        // Warn before leaving with unsaved changes
        window.addEventListener('beforeunload', (e) => {
            if (this.hasUnsavedChanges) {
                e.preventDefault();
                e.returnValue = '';
            }
        });
    }

    async loadFileList() {
        try {
            const response = await fetch('/api/v1/json-files/');
            const data = await response.json();

            const select = document.getElementById('file-select');
            select.innerHTML = '<option value="">-- Select a file --</option>';

            data.files.forEach(file => {
                const option = document.createElement('option');
                option.value = file.filename;
                option.textContent = `${file.filename} (${this.formatFileSize(file.size)})`;
                select.appendChild(option);
            });

            this.setStatus(`Found ${data.files.length} JSON files`);

            // Auto-load last opened file
            const lastFile = localStorage.getItem('json-editor-last-file');
            if (lastFile && data.files.some(f => f.filename === lastFile)) {
                select.value = lastFile;
                this.loadFile(lastFile);
            }
        } catch (error) {
            console.error('Error loading file list:', error);
            this.setStatus('Error loading files', 'error');
        }
    }

    async loadFile(filename) {
        if (!filename) {
            this.showEmptyState();
            return;
        }

        this.showLoadingState();
        this.setStatus(`Loading ${filename}...`);

        try {
            const response = await fetch(`/api/v1/json-files/${filename}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const fileData = await response.json();

            this.currentFile = filename;
            this.currentData = fileData.data;
            this.originalData = JSON.parse(JSON.stringify(fileData.data)); // Deep copy

            // Save to localStorage for auto-load next time
            localStorage.setItem('json-editor-last-file', filename);

            // Update file info
            document.getElementById('file-size').textContent = `Size: ${this.formatFileSize(fileData.size)}`;
            document.getElementById('file-modified').textContent = `Modified: ${new Date(fileData.modified).toLocaleString()}`;

            if (Array.isArray(this.currentData)) {
                document.getElementById('item-count').textContent = `Items: ${this.currentData.length}`;
            }

            document.getElementById('file-info').style.display = 'flex';

            // Enable toolbar
            this.enableToolbar();

            // Populate filters if this is config_inventory.json
            if (filename === 'config_inventory.json') {
                this.populateFilters();
            }

            // Render table
            this.renderTable();

            this.hasUnsavedChanges = false;
            this.updateUnsavedIndicator();
            this.setStatus(`Loaded ${filename} successfully`);

        } catch (error) {
            console.error('Error loading file:', error);
            this.setStatus(`Error loading ${filename}: ${error.message}`, 'error');
            this.showEmptyState();
        }
    }

    renderTable() {
        if (!this.currentData) {
            this.showEmptyState();
            return;
        }

        // Only support array data for now
        if (!Array.isArray(this.currentData)) {
            this.setStatus('Only array-type JSON files are supported for table editing', 'error');
            this.showEmptyState();
            return;
        }

        if (this.currentData.length === 0) {
            document.getElementById('table-wrapper').style.display = 'block';
            document.getElementById('table-header-wrapper').style.display = 'block';
            document.getElementById('loading-state').style.display = 'none';
            document.getElementById('table-body').innerHTML = '<tr><td colspan="100" style="text-align: center; padding: 40px;">No data</td></tr>';
            return;
        }

        // Get all unique keys from all objects (excluding internal fields)
        const allKeys = new Set();
        this.currentData.forEach(item => {
            if (typeof item === 'object' && item !== null) {
                Object.keys(item).forEach(key => {
                    // Exclude internal fields
                    if (!key.startsWith('_')) {
                        allKeys.add(key);
                    }
                });
            }
        });

        const keys = Array.from(allKeys);

        // Filter data
        let filteredData = this.currentData.filter((item, index) => {
            item._index = index; // Store original index

            // Search filter
            if (this.searchTerm) {
                const itemStr = JSON.stringify(item).toLowerCase();
                if (!itemStr.includes(this.searchTerm)) return false;
            }

            // Category filter
            if (this.filterCategory && item.suggested_category !== this.filterCategory) {
                return false;
            }

            // Type filter
            if (this.filterType && item.value_type !== this.filterType) {
                return false;
            }

            return true;
        });

        // Sort data
        if (this.sortColumn) {
            filteredData.sort((a, b) => {
                const aVal = a[this.sortColumn];
                const bVal = b[this.sortColumn];

                if (aVal === bVal) return 0;
                if (aVal === null || aVal === undefined) return 1;
                if (bVal === null || bVal === undefined) return -1;

                const comparison = aVal < bVal ? -1 : 1;
                return this.sortDirection === 'asc' ? comparison : -comparison;
            });
        }

        // Render headers
        const thead = document.getElementById('table-headers');
        thead.innerHTML = '<th class="cell-checkbox"><input type="checkbox" id="select-all"></th>';

        keys.forEach(key => {
            const th = document.createElement('th');

            // Create text span for header content
            const textSpan = document.createElement('span');
            textSpan.textContent = key;
            th.appendChild(textSpan);

            // Create resize handle
            const resizeHandle = document.createElement('div');
            resizeHandle.classList.add('resize-handle');
            th.appendChild(resizeHandle);

            th.classList.add('sortable');
            th.dataset.column = key;

            if (this.sortColumn === key) {
                th.classList.add(this.sortDirection === 'asc' ? 'sorted-asc' : 'sorted-desc');
            }

            // Click to sort (but not on resize handle)
            textSpan.addEventListener('click', () => this.sortBy(key));

            // Resize functionality
            this.makeResizable(th, resizeHandle);

            thead.appendChild(th);
        });

        // Add Notes column at the end
        const notesHeader = document.createElement('th');
        const notesSpan = document.createElement('span');
        notesSpan.textContent = '📝 Notes';
        notesHeader.appendChild(notesSpan);
        const notesResizeHandle = document.createElement('div');
        notesResizeHandle.classList.add('resize-handle');
        notesHeader.appendChild(notesResizeHandle);
        notesHeader.classList.add('notes-column');
        this.makeResizable(notesHeader, notesResizeHandle);
        thead.appendChild(notesHeader);

        // Select all checkbox
        document.getElementById('select-all').addEventListener('change', (e) => {
            filteredData.forEach(item => {
                if (e.target.checked) {
                    this.selectedRows.add(item._index);
                } else {
                    this.selectedRows.delete(item._index);
                }
            });
            this.renderTable();
            this.updateSelectedCount();
        });

        // Render rows
        const tbody = document.getElementById('table-body');
        tbody.innerHTML = '';

        filteredData.forEach(item => {
            const tr = document.createElement('tr');
            tr.dataset.index = item._index;

            if (this.selectedRows.has(item._index)) {
                tr.classList.add('selected');
            }

            // Checkbox cell
            const checkCell = document.createElement('td');
            checkCell.classList.add('cell-checkbox');
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = this.selectedRows.has(item._index);
            checkbox.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.selectedRows.add(item._index);
                } else {
                    this.selectedRows.delete(item._index);
                }
                tr.classList.toggle('selected', e.target.checked);
                this.updateSelectedCount();
            });
            checkCell.appendChild(checkbox);
            tr.appendChild(checkCell);

            // Data cells
            keys.forEach(key => {
                const td = document.createElement('td');
                td.classList.add('cell-editable');
                td.dataset.key = key;
                td.dataset.index = item._index;

                const value = item[key];
                const formattedValue = this.formatCellValue(value);
                td.textContent = formattedValue;

                // Add tooltip with full content
                td.title = formattedValue;

                // Make editable
                td.addEventListener('click', () => this.editCell(td, item, key));

                tr.appendChild(td);
            });

            // Notes cell
            const notesCell = document.createElement('td');
            notesCell.classList.add('cell-editable', 'notes-cell');
            notesCell.dataset.key = '_notes';
            notesCell.dataset.index = item._index;
            const notesValue = item._notes || '';
            notesCell.textContent = notesValue;
            notesCell.title = notesValue; // Add tooltip
            notesCell.addEventListener('click', () => this.editCell(notesCell, item, '_notes'));
            tr.appendChild(notesCell);

            tbody.appendChild(tr);
        });

        document.getElementById('table-wrapper').style.display = 'block';
        document.getElementById('table-header-wrapper').style.display = 'block';
        document.getElementById('loading-state').style.display = 'none';
        document.getElementById('empty-state').style.display = 'none';

        // Synchronize horizontal scrolling between header and body
        this.syncScrolling();
    }

    syncScrolling() {
        const headerWrapper = document.getElementById('table-header-wrapper');
        const bodyWrapper = document.getElementById('table-wrapper');

        if (!headerWrapper || !bodyWrapper) return;

        // Remove old listeners to avoid duplicates
        bodyWrapper.removeEventListener('scroll', this.scrollHandler);

        // Create scroll handler
        this.scrollHandler = () => {
            headerWrapper.scrollLeft = bodyWrapper.scrollLeft;
        };

        bodyWrapper.addEventListener('scroll', this.scrollHandler);
    }

    sortBy(column) {
        if (this.sortColumn === column) {
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortColumn = column;
            this.sortDirection = 'asc';
        }
        this.renderTable();
    }

    makeResizable(th, resizeHandle) {
        let startX, startWidth, columnIndex;

        const onMouseDown = (e) => {
            // Prevent sorting when clicking resize handle
            e.stopPropagation();

            startX = e.pageX;
            startWidth = th.offsetWidth;

            // Get column index
            columnIndex = Array.from(th.parentElement.children).indexOf(th);

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);

            // Prevent text selection during resize
            document.body.style.userSelect = 'none';
        };

        const onMouseMove = (e) => {
            const width = startWidth + (e.pageX - startX);
            // Set minimum width
            if (width >= 50) {
                const widthPx = width + 'px';

                // Update header column
                th.style.width = widthPx;
                th.style.minWidth = widthPx;
                th.style.maxWidth = widthPx;

                // Update corresponding body columns
                const bodyTable = document.getElementById('json-table');
                const bodyRows = bodyTable.querySelectorAll('tbody tr');
                bodyRows.forEach(row => {
                    const cell = row.children[columnIndex];
                    if (cell) {
                        cell.style.width = widthPx;
                        cell.style.minWidth = widthPx;
                        cell.style.maxWidth = widthPx;
                    }
                });
            }
        };

        const onMouseUp = () => {
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);

            // Re-enable text selection
            document.body.style.userSelect = '';
        };

        resizeHandle.addEventListener('mousedown', onMouseDown);
    }

    editCell(cell, item, key) {
        if (cell.classList.contains('cell-editing')) return;

        const currentValue = item[key];
        const originalText = cell.textContent;

        cell.classList.add('cell-editing');
        const input = document.createElement('input');
        input.type = 'text';
        input.value = typeof currentValue === 'object' ? JSON.stringify(currentValue) : currentValue;
        input.style.width = '100%';
        input.style.padding = '4px';
        input.style.border = 'none';
        input.style.background = 'white';
        input.style.color = 'black';

        cell.textContent = '';
        cell.appendChild(input);
        input.focus();
        input.select();

        const saveEdit = () => {
            let newValue = input.value;

            // Try to parse as JSON if it looks like JSON
            if (newValue.startsWith('{') || newValue.startsWith('[')) {
                try {
                    newValue = JSON.parse(newValue);
                } catch (e) {
                    // Keep as string
                }
            }

            // Type coercion based on original type
            if (typeof currentValue === 'number') {
                newValue = parseFloat(newValue);
            } else if (typeof currentValue === 'boolean') {
                newValue = newValue === 'true';
            }

            item[key] = newValue;
            cell.textContent = this.formatCellValue(newValue);
            cell.classList.remove('cell-editing');

            this.markAsChanged();
        };

        const cancelEdit = () => {
            cell.textContent = originalText;
            cell.classList.remove('cell-editing');
        };

        input.addEventListener('blur', saveEdit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                saveEdit();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                cancelEdit();
            }
        });
    }

    formatCellValue(value) {
        if (value === null) return 'null';
        if (value === undefined) return 'undefined';
        if (typeof value === 'object') return JSON.stringify(value);
        if (typeof value === 'boolean') return value ? 'true' : 'false';
        if (Array.isArray(value)) return `[${value.join(', ')}]`;
        return String(value);
    }

    addNewRow() {
        if (!Array.isArray(this.currentData)) return;

        // Create empty object with same keys as first item
        const template = this.currentData[0] || {};
        const newItem = {};

        Object.keys(template).forEach(key => {
            // Skip internal fields when creating template
            if (!key.startsWith('_')) {
                newItem[key] = '';
            }
        });

        // Initialize notes as empty
        newItem._notes = '';

        this.currentData.push(newItem);
        this.markAsChanged();
        this.renderTable();
        this.setStatus('Added new row');
    }

    deleteSelected() {
        if (this.selectedRows.size === 0) return;

        if (!confirm(`Delete ${this.selectedRows.size} selected row(s)?`)) return;

        // Sort indices in descending order to delete from end to start
        const indices = Array.from(this.selectedRows).sort((a, b) => b - a);

        indices.forEach(index => {
            this.currentData.splice(index, 1);
        });

        this.selectedRows.clear();
        this.markAsChanged();
        this.renderTable();
        this.updateSelectedCount();
        this.setStatus(`Deleted ${indices.length} row(s)`);
    }

    showAddFieldModal() {
        if (!Array.isArray(this.currentData)) return;

        // Clear previous values
        document.getElementById('field-name').value = '';
        document.getElementById('field-type').value = 'text';
        document.getElementById('field-default').value = '';

        document.getElementById('add-field-modal').style.display = 'flex';
        document.getElementById('field-name').focus();
    }

    hideAddFieldModal() {
        document.getElementById('add-field-modal').style.display = 'none';
    }

    addField() {
        const fieldName = document.getElementById('field-name').value.trim();
        const fieldType = document.getElementById('field-type').value;
        const fieldDefault = document.getElementById('field-default').value.trim();

        if (!fieldName) {
            alert('Please enter a field name');
            return;
        }

        // Check if field already exists
        if (this.currentData.length > 0 && this.currentData[0].hasOwnProperty(fieldName)) {
            alert(`Field "${fieldName}" already exists!`);
            return;
        }

        // Convert default value based on type
        let defaultValue = '';
        if (fieldDefault) {
            switch (fieldType) {
                case 'number':
                    defaultValue = parseFloat(fieldDefault) || 0;
                    break;
                case 'boolean':
                    defaultValue = fieldDefault.toLowerCase() === 'true';
                    break;
                case 'array':
                    defaultValue = fieldDefault.split(',').map(s => s.trim());
                    break;
                default:
                    defaultValue = fieldDefault;
            }
        } else {
            // Set sensible defaults for empty values
            switch (fieldType) {
                case 'number':
                    defaultValue = 0;
                    break;
                case 'boolean':
                    defaultValue = false;
                    break;
                case 'array':
                    defaultValue = [];
                    break;
                default:
                    defaultValue = '';
            }
        }

        // Add field to all existing rows
        this.currentData.forEach(item => {
            item[fieldName] = defaultValue;
        });

        this.markAsChanged();
        this.renderTable();
        this.hideAddFieldModal();
        this.setStatus(`Added field "${fieldName}" to all rows`);
    }

    populateFilters() {
        // Get unique categories and types
        const categories = new Set();
        const types = new Set();

        this.currentData.forEach(item => {
            if (item.suggested_category) categories.add(item.suggested_category);
            if (item.value_type) types.add(item.value_type);
        });

        // Populate category filter
        const categorySelect = document.getElementById('filter-category');
        categorySelect.innerHTML = '<option value="">All Categories</option>';
        Array.from(categories).sort().forEach(cat => {
            const option = document.createElement('option');
            option.value = cat;
            option.textContent = cat;
            categorySelect.appendChild(option);
        });

        // Populate type filter
        const typeSelect = document.getElementById('filter-type');
        typeSelect.innerHTML = '<option value="">All Types</option>';
        Array.from(types).sort().forEach(type => {
            const option = document.createElement('option');
            option.value = type;
            option.textContent = type;
            typeSelect.appendChild(option);
        });
    }

    async saveChanges() {
        if (!this.currentFile || !this.currentData) return;

        if (!confirm(`Save changes to ${this.currentFile}?`)) return;

        this.setStatus('Saving...');

        try {
            // Clean data before saving (remove _index but keep _notes)
            const cleanData = this.currentData.map(item => {
                const cleaned = { ...item };
                delete cleaned._index;
                return cleaned;
            });

            const response = await fetch(`/api/v1/json-files/${this.currentFile}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ data: cleanData })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const result = await response.json();

            this.originalData = JSON.parse(JSON.stringify(this.currentData));
            this.hasUnsavedChanges = false;
            this.updateUnsavedIndicator();

            this.setStatus(`✅ Saved successfully. Backup: ${result.backup}`, 'success');

        } catch (error) {
            console.error('Error saving file:', error);
            this.setStatus(`❌ Error saving: ${error.message}`, 'error');
        }
    }

    exportJSON() {
        if (!this.currentData) return;

        // Clean data before export (remove _index but keep _notes)
        const cleanData = this.currentData.map(item => {
            const cleaned = { ...item };
            delete cleaned._index;
            return cleaned;
        });

        const dataStr = JSON.stringify(cleanData, null, 2);
        const blob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = this.currentFile || 'export.json';
        a.click();

        URL.revokeObjectURL(url);
        this.setStatus('Exported JSON');
    }

    importJSON(event) {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();

        reader.onload = (e) => {
            try {
                const imported = JSON.parse(e.target.result);

                if (!Array.isArray(imported)) {
                    alert('Imported data must be an array');
                    return;
                }

                if (confirm(`Import ${imported.length} items? This will replace current data.`)) {
                    this.currentData = imported;
                    this.markAsChanged();
                    this.renderTable();
                    this.setStatus(`Imported ${imported.length} items`);
                }

            } catch (error) {
                alert(`Error parsing JSON: ${error.message}`);
            }
        };

        reader.readAsText(file);
        event.target.value = ''; // Reset file input
    }

    markAsChanged() {
        this.hasUnsavedChanges = true;
        this.updateUnsavedIndicator();
        document.getElementById('save-changes').disabled = false;
    }

    updateUnsavedIndicator() {
        const indicator = document.getElementById('unsaved-indicator');
        indicator.style.display = this.hasUnsavedChanges ? 'block' : 'none';
    }

    updateSelectedCount() {
        document.getElementById('selected-count').textContent = this.selectedRows.size;
        document.getElementById('delete-selected').disabled = this.selectedRows.size === 0;
    }

    enableToolbar() {
        document.getElementById('add-row').disabled = false;
        document.getElementById('add-field').disabled = false;
        document.getElementById('search-box').disabled = false;
        document.getElementById('filter-category').disabled = false;
        document.getElementById('filter-type').disabled = false;
        document.getElementById('export-json').disabled = false;
        document.getElementById('import-json').disabled = false;
    }

    showLoadingState() {
        document.getElementById('loading-state').style.display = 'block';
        document.getElementById('table-wrapper').style.display = 'none';
        document.getElementById('empty-state').style.display = 'none';
    }

    showEmptyState() {
        document.getElementById('loading-state').style.display = 'none';
        document.getElementById('table-wrapper').style.display = 'none';
        document.getElementById('table-header-wrapper').style.display = 'none';
        document.getElementById('empty-state').style.display = 'block';
    }

    setStatus(message, type = 'info') {
        const statusEl = document.getElementById('status-message');
        statusEl.textContent = message;

        if (type === 'error') {
            statusEl.style.color = 'var(--error-color, #dc3545)';
        } else if (type === 'success') {
            statusEl.style.color = 'var(--success-color, #28a745)';
        } else {
            statusEl.style.color = 'var(--text-secondary)';
        }

        // Clear success/error color after 5 seconds
        if (type !== 'info') {
            setTimeout(() => {
                statusEl.style.color = 'var(--text-secondary)';
            }, 5000);
        }
    }

    formatFileSize(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
}

// Initialize editor when page loads
document.addEventListener('DOMContentLoaded', () => {
    new JSONEditor();
});
