// State
let socket;
let selectedTaskId = null;
const activeTasks = new Map();
const searchInput = document.getElementById('searchInput');
const searchResults = document.getElementById('searchResults');
const taskList = document.getElementById('taskList');
const completedList = document.getElementById('completedList');
const logViewer = document.getElementById('logViewer');
const downloadModal = document.getElementById('downloadModal');
const selectionModal = document.getElementById('selectionModal');
const chapterTreeContainer = document.getElementById('chapterTreeContainer');
const chapterSearchInput = document.getElementById('chapterSearchInput');

// Navigation elements
const navSearch = document.getElementById('navSearch');
const navLibrary = document.getElementById('navLibrary');
const tasksView = document.getElementById('tasksView');
const libraryActionsView = document.getElementById('libraryActionsView');
const searchView = document.getElementById('searchView');
const libraryView = document.getElementById('libraryView');
const libraryGrid = document.getElementById('libraryGrid');
const librarySearchInput = document.getElementById('librarySearchInput');
const checkUpdatesBtn = document.getElementById('checkUpdatesBtn');
const scanFoldersBtn = document.getElementById('scanFoldersBtn');
const batchImportBtn = document.getElementById('batchImportBtn');
const batchImportModal = document.getElementById('batchImportModal');
const batchImportUrls = document.getElementById('batchImportUrls');
const startBatchDownloadBtn = document.getElementById('startBatchDownloadBtn');
const libraryStats = document.getElementById('libraryStats');

// Theme Logic
const themeToggle = document.getElementById('themeToggle');
const savedTheme = localStorage.getItem('theme');

if (savedTheme) {
    document.body.classList.toggle('dark-theme', savedTheme === 'dark');
} else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    document.body.classList.add('dark-theme');
}

themeToggle.onclick = () => {
    document.body.classList.toggle('dark-theme');
    const theme = document.body.classList.contains('dark-theme') ? 'dark' : 'light';
    localStorage.setItem('theme', theme);
};

// Tab Switching
navSearch.onclick = () => {
    navSearch.classList.add('active');
    navLibrary.classList.remove('active');
    searchView.style.display = 'block';
    libraryView.style.display = 'none';
    tasksView.style.display = 'block';
    libraryActionsView.style.display = 'none';
};

navLibrary.onclick = () => {
    navSearch.classList.remove('active');
    navLibrary.classList.add('active');
    searchView.style.display = 'none';
    libraryView.style.display = 'block';
    tasksView.style.display = 'none';
    libraryActionsView.style.display = 'block';
    renderLibrary();
};

let currentTreeData = [];
let selectedUrls = new Set();
let currentSlug = '';
let currentTitle = '';

// Init WebSocket
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new WebSocket(`${protocol}//${window.location.host}/ws/tasks`);

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleSocketMessage(data);
    };

    socket.onclose = () => {
        addLogEntry('system', { time: new Date().toLocaleTimeString(), level: 'ERROR', message: 'WebSocket connection closed. Reconnecting...' });
        setTimeout(initWebSocket, 3000);
    };
}

function handleSocketMessage(data) {
    if (data.type === 'log') {
        addLogEntry(data.task_id, data);
    } else if (data.type === 'info') {
        updateTask(data.task_id, { title: data.title });
    } else if (data.type === 'status') {
        updateTask(data.task_id, { status: data.status });
    } else if (data.type === 'progress') {
        updateTask(data.task_id, { percent: data.percent, status: data.msg });
    } else if (data.type === 'complete') {
        finishTask(data.task_id, data.path);
    } else if (data.type === 'error') {
        updateTask(data.task_id, { status: `Lỗi: ${data.error}`, error: true });
    } else if (data.type === 'library_check_progress') {
        updateLibraryCheckProgress(data.current, data.total, data.title);
    } else if (data.type === 'library_check_complete') {
        finishLibraryCheck(data.updates_found);
    }
}

function updateLibraryCheckProgress(current, total, title) {
    checkUpdatesBtn.disabled = true;
    const percent = Math.round((current / total) * 100);
    checkUpdatesBtn.innerHTML = `<span class="spinner"></span> (${percent}%) ${title}`;
    
    // Also update a global progress bar
    let progressBar = document.getElementById('libraryCheckProgressBar');
    if (!progressBar) {
        progressBar = document.createElement('div');
        progressBar.id = 'libraryCheckProgressBar';
        progressBar.className = 'global-progress-bar';
        progressBar.innerHTML = '<div class="progress-fill"></div>';
        const container = document.getElementById('globalProgressBarContainer');
        if (container) {
            container.appendChild(progressBar);
        } else {
            // Fallback
            document.querySelector('header').after(progressBar);
        }
    }
    progressBar.querySelector('.progress-fill').style.width = `${percent}%`;
    progressBar.style.display = 'block';
}

function finishLibraryCheck(updatesFound) {
    checkUpdatesBtn.disabled = false;
    checkUpdatesBtn.textContent = 'Kiểm tra cập nhật';
    
    const progressBar = document.getElementById('libraryCheckProgressBar');
    if (progressBar) progressBar.style.display = 'none';
    
    renderLibrary();
    
    if (updatesFound > 0) {
        showNotification(`Đã tìm thấy ${updatesFound} bản cập nhật mới!`);
    }
}

function showNotification(msg) {
    // Simple toast notification
    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }, 100);
}

// Log Handling
function addLogEntry(taskId, data) {
    const task = activeTasks.get(taskId);
    if (!task && taskId !== 'system') return;

    const logMsg = taskId === 'system' ? data : data;
    
    if (taskId !== 'system') {
        task.logs.push(logMsg);
    }

    // Only render if this task is selected or it's a system message
    if (selectedTaskId === taskId || (taskId === 'system' && !selectedTaskId)) {
        renderLogEntry(logMsg);
    }
}

function renderLogEntry(data) {
    const entry = document.createElement('div');
    entry.className = `log-entry ${data.level || ''}`;
    entry.innerHTML = `<span class="time">[${data.time}]</span> <span class="level ${data.level}">${data.level}</span> ${data.message}`;
    logViewer.appendChild(entry);
    logViewer.scrollTop = logViewer.scrollHeight;
}

async function refreshLogViewer() {
    logViewer.innerHTML = '';
    if (!selectedTaskId) {
        logViewer.innerHTML = '<div class="log-entry system">Chọn một nhiệm vụ để xem nhật ký...</div>';
        return;
    }

    const task = activeTasks.get(selectedTaskId);
    if (!task) return;

    // First render what we have in memory
    if (task.logs && task.logs.length > 0) {
        task.logs.forEach(renderLogEntry);
    } else {
        logViewer.innerHTML = '<div class="log-entry system">Đang tải nhật ký...</div>';
    }

    // Then fetch full history from server
    const currentSelectedId = selectedTaskId;
    try {
        const response = await fetch(`/api/tasks/${selectedTaskId}/logs`);
        if (response.ok) {
            const logs = await response.json();
            // Ensure we're still on the same task when request returns
            if (currentSelectedId === selectedTaskId) {
                task.logs = logs;
                logViewer.innerHTML = '';
                task.logs.forEach(renderLogEntry);
            }
        }
    } catch (e) {
        console.error('Failed to fetch logs', e);
    }
}

const outputPathInput = document.getElementById('outputPathInput');
const browseBtn = document.getElementById('browseBtn');

// Browse Folder
browseBtn.onclick = async () => {
    try {
        const response = await fetch('/api/browse');
        const data = await response.json();
        if (data.path) {
            outputPathInput.value = data.path;
        } else if (data.error) {
            alert(data.error);
        }
    } catch (e) {
        console.error('Failed to open folder dialog', e);
        alert('Không thể mở hộp thoại chọn thư mục.');
    }
};

// Search Handling
let searchTimeout;
searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    const query = searchInput.value.trim();
    if (query.length < 3) {
        searchResults.style.display = 'none';
        return;
    }

    searchTimeout = setTimeout(async () => {
        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const data = await response.json();
            displaySearchResults(data);
        } catch (e) {
            console.error('Search failed', e);
        }
    }, 500);
});

function displaySearchResults(results) {
    searchResults.innerHTML = '';
    if (results.length === 0) {
        searchResults.innerHTML = '<div class="search-item">Không tìm thấy kết quả.</div>';
    } else {
        results.forEach(item => {
            const div = document.createElement('div');
            div.className = 'search-item';
            div.innerHTML = `
                <span class="title">${item.title}</span>
                <span class="meta">${item.author} | ${item.status} | ${item.totalChapters} chương</span>
            `;
            div.onclick = () => openPreviewModal(item);
            searchResults.appendChild(div);
        });
    }
    searchResults.style.display = 'block';
}

// Modal Handling
async function openPreviewModal(item) {
    const previewModal = document.getElementById('previewModal');
    
    // Reset/Loading state
    document.getElementById('previewTitle').textContent = item.title;
    document.getElementById('previewAuthor').textContent = item.author;
    document.getElementById('previewStatus').textContent = item.status || '-';
    document.getElementById('previewTotalChapters').textContent = item.totalChapters || '-';
    document.getElementById('previewCover').src = 'https://via.placeholder.com/140x200?text=Loading...';
    document.getElementById('previewGenres').innerHTML = '';
    document.getElementById('previewWordCount').textContent = '-';
    document.getElementById('previewViews').textContent = '-';
    document.getElementById('previewDescContent').textContent = 'Đang tải thông tin...';
    
    previewModal.style.display = 'flex';
    searchResults.style.display = 'none';

    try {
        const response = await fetch(`/api/story_info?slug=${encodeURIComponent(item.slug)}`);
        const data = await response.json();
        
        if (data.error) throw new Error(data.error);

        document.getElementById('previewAuthor').textContent = data.author;
        document.getElementById('previewTotalChapters').textContent = data.total_chapters;
        document.getElementById('previewWordCount').textContent = data.word_count;
        document.getElementById('previewViews').textContent = data.views;
        document.getElementById('previewDescContent').textContent = data.description;
        
        // Use real cover URL if available
        if (data.cover_url) {
            const coverImg = document.getElementById('previewCover');
            coverImg.src = data.cover_url;
            coverImg.onerror = () => {
                coverImg.src = 'https://via.placeholder.com/140x200?text=No+Cover';
            };
        } else {
            document.getElementById('previewCover').src = 'https://via.placeholder.com/140x200?text=VVR+T';
        }

        const genresList = document.getElementById('previewGenres');
        genresList.innerHTML = '';
        if (data.genres) {
            data.genres.forEach(genre => {
                const span = document.createElement('span');
                span.className = 'genre-tag';
                span.textContent = genre;
                genresList.appendChild(span);
            });
        }
    } catch (e) {
        console.error('Failed to fetch story info', e);
        document.getElementById('previewDescContent').textContent = 'Không thể tải thông tin chi tiết.';
    }

    document.getElementById('selectChaptersBtn').onclick = () => {
        closePreviewModal();
        openSelectionModal(item);
    };
}

function closePreviewModal() {
    document.getElementById('previewModal').style.display = 'none';
}

async function openSelectionModal(item) {
    currentSlug = item.slug;
    currentTitle = item.title;
    selectionModal.style.display = 'flex';
    chapterTreeContainer.innerHTML = '<div class="loading-msg">Đang tải danh sách chương...</div>';
    chapterSearchInput.value = '';
    selectedUrls.clear();
    
    try {
        const response = await fetch(`/api/chapters?slug=${encodeURIComponent(item.slug)}`);
        currentTreeData = await response.json();
        renderChapterTree(currentTreeData);
    } catch (e) {
        console.error('Failed to fetch chapters', e);
        chapterTreeContainer.innerHTML = '<div class="loading-msg">Không thể tải danh sách chương.</div>';
    }
}

function closeSelectionModal() {
    selectionModal.style.display = 'none';
}

function renderChapterTree(data) {
    chapterTreeContainer.innerHTML = '';
    let totalChapters = 0;

    data.forEach((volume, vIdx) => {
        const volumeEl = document.createElement('div');
        volumeEl.className = 'volume-item';
        volumeEl.dataset.index = vIdx;

        const volumeHeader = document.createElement('div');
        volumeHeader.className = 'volume-header';
        
        const volumeCheckbox = document.createElement('input');
        volumeCheckbox.type = 'checkbox';
        volumeCheckbox.id = `vol-${vIdx}`;
        
        const volumeTitle = document.createElement('label');
        volumeTitle.htmlFor = `vol-${vIdx}`;
        volumeTitle.textContent = volume.volume;

        volumeHeader.appendChild(volumeCheckbox);
        volumeHeader.appendChild(volumeTitle);
        volumeEl.appendChild(volumeHeader);

        const chapterList = document.createElement('div');
        chapterList.className = 'chapter-list';

        volume.chapters.forEach((chapter, cIdx) => {
            totalChapters++;
            const chapterEl = document.createElement('div');
            chapterEl.className = 'chapter-item';
            if (chapter.locked) chapterEl.classList.add('locked');

            const chapterCheckbox = document.createElement('input');
            chapterCheckbox.type = 'checkbox';
            chapterCheckbox.id = `chap-${vIdx}-${cIdx}`;
            chapterCheckbox.dataset.url = chapter.url;
            chapterCheckbox.disabled = !!chapter.locked;
            
            // Auto-select unlocked chapters by default
            if (!chapter.locked) {
                chapterCheckbox.checked = true;
                selectedUrls.add(chapter.url);
            }

            const chapterLabel = document.createElement('label');
            chapterLabel.htmlFor = `chap-${vIdx}-${cIdx}`;
            chapterLabel.textContent = chapter.title;

            chapterCheckbox.onchange = () => {
                if (chapterCheckbox.checked) {
                    selectedUrls.add(chapter.url);
                } else {
                    selectedUrls.delete(chapter.url);
                }
                updateSelectionStats(totalChapters);
                updateVolumeCheckbox(volumeCheckbox, chapterList);
            };

            chapterEl.appendChild(chapterCheckbox);
            chapterEl.appendChild(chapterLabel);
            chapterList.appendChild(chapterEl);
        });

        volumeCheckbox.onchange = () => {
            const chks = chapterList.querySelectorAll('input[type="checkbox"]:not(:disabled)');
            chks.forEach(chk => {
                chk.checked = volumeCheckbox.checked;
                if (chk.checked) {
                    selectedUrls.add(chk.dataset.url);
                } else {
                    selectedUrls.delete(chk.dataset.url);
                }
            });
            updateSelectionStats(totalChapters);
        };

        // Initial volume checkbox state
        updateVolumeCheckbox(volumeCheckbox, chapterList);

        volumeEl.appendChild(chapterList);
        chapterTreeContainer.appendChild(volumeEl);
    });

    document.getElementById('totalChaptersCount').textContent = totalChapters;
    updateSelectionStats(totalChapters);
}

function updateVolumeCheckbox(volChk, chapList) {
    const chks = chapList.querySelectorAll('input[type="checkbox"]:not(:disabled)');
    const checked = chapList.querySelectorAll('input[type="checkbox"]:checked:not(:disabled)');
    
    if (chks.length === 0) {
        volChk.checked = false;
        volChk.disabled = true;
        return;
    }
    
    volChk.checked = chks.length === checked.length;
    volChk.indeterminate = checked.length > 0 && checked.length < chks.length;
}

function updateSelectionStats(total) {
    document.getElementById('selectedChaptersCount').textContent = selectedUrls.size;
}

// Chapter Search/Filter
chapterSearchInput.addEventListener('input', () => {
    const query = chapterSearchInput.value.toLowerCase().trim();
    const volumeItems = chapterTreeContainer.querySelectorAll('.volume-item');
    
    volumeItems.forEach(volItem => {
        const chapters = volItem.querySelectorAll('.chapter-item');
        let hasVisibleChapter = false;
        
        chapters.forEach(chapItem => {
            const title = chapItem.querySelector('label').textContent.toLowerCase();
            if (title.includes(query)) {
                chapItem.classList.remove('hidden');
                hasVisibleChapter = true;
            } else {
                chapItem.classList.add('hidden');
            }
        });
        
        if (hasVisibleChapter || volItem.querySelector('.volume-header label').textContent.toLowerCase().includes(query)) {
            volItem.classList.remove('hidden');
        } else {
            volItem.classList.add('hidden');
        }
    });
});

document.getElementById('confirmSelectionBtn').onclick = () => {
    if (selectedUrls.size === 0) {
        alert('Vui lòng chọn ít nhất một chương.');
        return;
    }
    closeSelectionModal();
    openDownloadModal({ title: currentTitle, slug: currentSlug });
};

function openDownloadModal(item) {
    document.getElementById('modalTitle').textContent = `Tải: ${item.title}`;
    document.getElementById('modalSlug').value = item.slug;
    downloadModal.style.display = 'flex';
    searchResults.style.display = 'none';
}

function closeModal() {
    downloadModal.style.display = 'none';
}

function openBatchImportModal() {
    batchImportModal.style.display = 'flex';
    batchImportUrls.value = '';
}

function closeBatchImportModal() {
    batchImportModal.style.display = 'none';
}

batchImportBtn.onclick = openBatchImportModal;

startBatchDownloadBtn.onclick = async () => {
    const content = batchImportUrls.value.trim();
    if (!content) {
        alert('Vui lòng nhập ít nhất một URL hoặc Slug.');
        return;
    }

    const items = content.split('\n').map(line => line.trim()).filter(line => line.length > 0);
    
    startBatchDownloadBtn.disabled = true;
    startBatchDownloadBtn.textContent = 'Đang xử lý...';

    try {
        const response = await fetch('/api/batch-import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ items })
        });
        
        const data = await response.json();
        if (response.ok) {
            alert(`Đã thêm ${data.count} truyện vào hàng chờ.`);
            closeBatchImportModal();
        } else {
            alert('Lỗi: ' + (data.error || 'Không thể nhập hàng loạt.'));
        }
    } catch (e) {
        console.error('Batch import failed', e);
        alert('Không thể kết nối đến máy chủ.');
    } finally {
        startBatchDownloadBtn.disabled = false;
        startBatchDownloadBtn.textContent = 'Bắt đầu tải';
    }
};

document.getElementById('downloadForm').onsubmit = async (e) => {
    e.preventDefault();
    const formats = Array.from(document.querySelectorAll('input[name="format"]:checked')).map(cb => cb.value);
    const slug = document.getElementById('modalSlug').value;
    const tasks = parseInt(document.getElementById('tasksInput').value);
    const skipIllus = document.getElementById('skipIllus').checked;
    const outputPath = document.getElementById('outputPathInput').value.trim();

    if (formats.length === 0) {
        alert('Vui lòng chọn ít nhất một định dạng.');
        return;
    }

    try {
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                slug, 
                formats, 
                tasks, 
                skip_illustrations: skipIllus,
                output_folder: outputPath || null,
                selected_urls: Array.from(selectedUrls)
            })
        });
        const data = await response.json();
        createTaskUI(data.task_id, currentTitle || slug);
        closeModal();
    } catch (e) {
        alert('Không thể bắt đầu tải xuống.');
    }
};

// Task UI Handling
function createTaskUI(taskId, title) {
    if (document.querySelector('.empty-msg')) {
        document.querySelector('.empty-msg').remove();
    }

    const taskItem = document.createElement('div');
    taskItem.id = `task-${taskId}`;
    taskItem.className = 'task-item';
    taskItem.onclick = () => selectTask(taskId);
    taskItem.innerHTML = `
        <div class="task-header">
            <span class="task-title">${title}</span>
            <div class="task-controls">
                <button class="pause-btn" title="Tạm dừng">⏸</button>
                <button class="resume-btn" title="Tiếp tục" style="display:none">▶</button>
                <button class="cancel-btn" title="Hủy bỏ">✕</button>
            </div>
            <span class="task-percent">0%</span>
        </div>
        <div class="progress-bar">
            <div class="progress-fill" style="width: 0%"></div>
        </div>
        <div class="task-status">Đang khởi tạo...</div>
    `;

    // Add control event listeners
    taskItem.querySelector('.pause-btn').onclick = (e) => {
        e.stopPropagation();
        pauseTask(taskId);
    };
    taskItem.querySelector('.resume-btn').onclick = (e) => {
        e.stopPropagation();
        resumeTask(taskId);
    };
    taskItem.querySelector('.cancel-btn').onclick = (e) => {
        e.stopPropagation();
        cancelTask(taskId);
    };

    taskList.appendChild(taskItem);
    activeTasks.set(taskId, { id: taskId, title, logs: [], status: 'Đang khởi tạo...', percent: 0 });
    
    // Auto-select the first task added
    if (!selectedTaskId) {
        selectTask(taskId);
    }
}

function selectTask(taskId) {
    if (selectedTaskId) {
        const oldEl = document.getElementById(`task-${selectedTaskId}`);
        if (oldEl) oldEl.classList.remove('selected');
    }

    selectedTaskId = taskId;
    const newEl = document.getElementById(`task-${taskId}`);
    if (newEl) newEl.classList.add('selected');

    const task = activeTasks.get(taskId);
    const infoEl = document.getElementById('selectedTaskInfo');
    if (task && infoEl) {
        infoEl.textContent = `Đang xem: ${task.title}`;
    } else if (infoEl) {
        infoEl.textContent = '';
    }

    refreshLogViewer();
}
function updateTask(taskId, data) {
    const task = activeTasks.get(taskId);
    if (!task) return;

    const el = document.getElementById(`task-${taskId}`);
    
    if (data.title) {
        task.title = data.title;
        if (el) el.querySelector('.task-title').textContent = data.title;
    }
    if (data.status) {
        task.status = data.status;
        if (el) {
            el.querySelector('.task-status').textContent = data.status;
            
            // UI state based on status
            const pauseBtn = el.querySelector('.pause-btn');
            const resumeBtn = el.querySelector('.resume-btn');
            
            if (data.status.includes('Paused') || data.status.includes('Tạm dừng')) {
                if (pauseBtn) pauseBtn.style.display = 'none';
                if (resumeBtn) resumeBtn.style.display = 'inline-block';
            } else if (data.status !== 'Hoàn thành') {
                if (pauseBtn) pauseBtn.style.display = 'inline-block';
                if (resumeBtn) resumeBtn.style.display = 'none';
            }
        }
    }
    if (data.percent !== undefined) {
        task.percent = data.percent;
        if (el) {
            el.querySelector('.task-percent').textContent = `${data.percent}%`;
            el.querySelector('.progress-fill').style.width = `${data.percent}%`;
        }
    }
    if (data.error) {
        if (el) {
            el.style.borderLeftColor = 'var(--error)';
            el.querySelector('.task-percent').style.color = 'var(--error)';
        }
    }
}

async function pauseTask(taskId) {
    try {
        await fetch(`/api/tasks/${taskId}/pause`, { method: 'POST' });
        updateTask(taskId, { status: 'Pausing...' });
    } catch (e) {
        console.error('Failed to pause task', e);
    }
}

async function resumeTask(taskId) {
    try {
        await fetch(`/api/tasks/${taskId}/resume`, { method: 'POST' });
        updateTask(taskId, { status: 'Resuming...' });
    } catch (e) {
        console.error('Failed to resume task', e);
    }
}

async function cancelTask(taskId) {
    if (!confirm('Bạn có chắc chắn muốn hủy nhiệm vụ này?')) return;
    try {
        await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
        const el = document.getElementById(`task-${taskId}`);
        if (el) el.remove();
        activeTasks.delete(taskId);
        if (selectedTaskId === taskId) {
            selectedTaskId = null;
            refreshLogViewer();
        }
    } catch (e) {
        console.error('Failed to cancel task', e);
    }
}

// Settings Logic
const settingsBtn = document.getElementById('settingsBtn');
const settingsModal = document.getElementById('settingsModal');
const settingsForm = document.getElementById('settingsForm');
const browseDefaultBtn = document.getElementById('browseDefaultBtn');

settingsBtn.onclick = async () => {
    await fetchSettings();
    settingsModal.style.display = 'flex';
};

function closeSettingsModal() {
    settingsModal.style.display = 'none';
}

async function fetchSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        document.getElementById('globalNumWorkers').value = data.num_workers || 1;
        document.getElementById('defaultOutputFolder').value = data.default_output_folder || '';
        
        // Update the download form's default output path if it's empty
        if (!document.getElementById('outputPathInput').value && data.default_output_folder) {
            document.getElementById('outputPathInput').value = data.default_output_folder;
        }
    } catch (e) {
        console.error('Failed to fetch settings', e);
    }
}

settingsForm.onsubmit = async (e) => {
    e.preventDefault();
    const num_workers = parseInt(document.getElementById('globalNumWorkers').value);
    const default_output_folder = document.getElementById('defaultOutputFolder').value.trim();

    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ num_workers, default_output_folder })
        });
        if (response.ok) {
            closeSettingsModal();
        } else {
            alert('Lỗi khi lưu cài đặt.');
        }
    } catch (e) {
        console.error('Failed to save settings', e);
        alert('Không thể lưu cài đặt.');
    }
};

browseDefaultBtn.onclick = async () => {
    try {
        const response = await fetch('/api/browse');
        const data = await response.json();
        if (data.path) {
            document.getElementById('defaultOutputFolder').value = data.path;
        } else if (data.error) {
            alert(data.error);
        }
    } catch (e) {
        console.error('Failed to open folder dialog', e);
    }
};

function finishTask(taskId, path) {
    const taskEl = document.getElementById(`task-${taskId}`);
    const task = activeTasks.get(taskId);
    
    if (taskEl) taskEl.remove();

    const completedItem = document.createElement('div');
    completedItem.className = 'completed-item';
    completedItem.innerHTML = `
        <div class="status-dot"></div>
        <span>${task ? task.title : 'Nhiệm vụ'} (Đã xong)</span>
    `;
    completedList.prepend(completedItem);
    
    if (selectedTaskId === taskId) {
        selectedTaskId = null;
        refreshLogViewer();
    }
    
    activeTasks.delete(taskId);

    if (taskList.children.length === 0) {
        taskList.innerHTML = '<p class="empty-msg">Chưa có nhiệm vụ nào.</p>';
    }
}

// Library Management
let libraryData = [];

async function renderLibrary() {
    libraryGrid.innerHTML = '<div class="loading-msg">Đang tải thư viện...</div>';
    
    try {
        const response = await fetch('/api/library');
        libraryData = await response.json();
        filterLibrary();
        updateLibraryStats();
        updateSyncBar();
    } catch (e) {
        console.error('Failed to fetch library', e);
        libraryGrid.innerHTML = '<div class="error-msg">Không thể tải thư viện.</div>';
    }
}

function updateSyncBar() {
    const updatedNovels = libraryData.filter(n => n.has_updates === 1);
    let syncBar = document.getElementById('floatingSyncBar');
    
    if (updatedNovels.length === 0) {
        if (syncBar) syncBar.classList.remove('show');
        return;
    }
    
    if (!syncBar) {
        syncBar = document.createElement('div');
        syncBar.id = 'floatingSyncBar';
        syncBar.className = 'floating-sync-bar';
        syncBar.innerHTML = `
            <div class="sync-info">
                <span class="sync-count">X</span> novels need syncing
            </div>
            <button id="syncAllBtn" class="btn-primary">Download All Updates</button>
        `;
        document.body.appendChild(syncBar);
        
        document.getElementById('syncAllBtn').onclick = async () => {
            const btn = document.getElementById('syncAllBtn');
            btn.disabled = true;
            btn.textContent = 'Queuing tasks...';
            try {
                const response = await fetch('/api/library/sync-all', { method: 'POST' });
                const data = await response.json();
                showNotification(`Queued ${data.queued} incremental updates.`);
                renderLibrary();
                navSearch.click(); // Switch to search/tasks view to see progress
            } catch (e) {
                alert('Failed to sync all updates.');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Download All Updates';
            }
        };
    }
    
    syncBar.querySelector('.sync-count').textContent = updatedNovels.length;
    syncBar.classList.add('show');
}

function filterLibrary() {
    const query = librarySearchInput.value.toLowerCase().trim();
    const filtered = libraryData.filter(novel => 
        novel.title.toLowerCase().includes(query) || 
        (novel.author && novel.author.toLowerCase().includes(query))
    );
    
    libraryGrid.innerHTML = '';
    if (filtered.length === 0) {
        libraryGrid.innerHTML = '<div class="empty-msg">Không tìm thấy truyện nào.</div>';
        return;
    }
    
    filtered.forEach(novel => {
        const card = document.createElement('div');
        card.className = 'novel-card';
        
        let statusClass = 'synced';
        let statusText = 'Đã khớp';
        let updateBadge = '';
        
        const hasUpdates = novel.has_updates === 1;
        const diff = (novel.server_chapter_count || 0) - (novel.last_synced_count || 0);

        if (hasUpdates) {
            statusClass = 'update-available';
            statusText = 'Có chương mới';
            updateBadge = `<div class="update-ribbon">+${diff > 0 ? diff : 'New'}</div>`;
        } else if (novel.status === 'unavailable') {
            statusClass = 'unavailable';
            statusText = 'Mất link';
        } else if (novel.status === 'archived') {
            statusClass = 'archived';
            statusText = 'Đã lưu trữ';
        }
        
        card.innerHTML = `
            ${updateBadge}
            <div class="card-cover">
                <img src="${novel.cover_url || 'https://via.placeholder.com/180x240?text=No+Cover'}" alt="${novel.title}" onerror="this.src='https://via.placeholder.com/180x240?text=No+Cover'">
                <span class="status-badge ${statusClass}">${statusText}</span>
            </div>
            <div class="card-info">
                <div class="card-title" title="${novel.title}">${novel.title}</div>
                <div class="card-author">${novel.author || 'Ẩn danh'}</div>
                <div class="card-meta">
                    <span>${novel.last_synced_count || novel.last_chapter_count || 0} chương</span>
                    <span title="${novel.output_folder || 'Chưa có đường dẫn'}">${novel.output_folder ? '📂' : ''}</span>
                </div>
            </div>
            <div class="card-actions">
                <button class="btn-primary btn-sm update-novel-btn" data-slug="${novel.slug}">Cập nhật</button>
                <button class="btn-secondary btn-sm preview-novel-btn">Chi tiết</button>
            </div>
        `;
        
        card.querySelector('.update-novel-btn').onclick = (e) => {
            e.stopPropagation();
            openPreviewModal(novel);
        };
        
        card.querySelector('.preview-novel-btn').onclick = (e) => {
            e.stopPropagation();
            openPreviewModal(novel);
        };
        
        card.onclick = () => openPreviewModal(novel);
        
        libraryGrid.appendChild(card);
    });
}

function updateLibraryStats() {
    if (!libraryStats) return;
    const total = libraryData.length;
    const updates = libraryData.filter(n => n.has_updates === 1).length;
    libraryStats.innerHTML = `
        <p>Tổng số truyện: <strong>${total}</strong></p>
        <p>Cần cập nhật: <strong style="color:var(--primary)">${updates}</strong></p>
    `;
}

checkUpdatesBtn.onclick = async () => {
    checkUpdatesBtn.disabled = true;
    checkUpdatesBtn.textContent = 'Đang kiểm tra...';
    try {
        const response = await fetch('/api/library/check-updates');
        if (response.ok) {
            // Wait for WebSocket messages to update progress
        } else {
            alert('Lỗi khi kích hoạt kiểm tra cập nhật.');
            checkUpdatesBtn.disabled = false;
            checkUpdatesBtn.textContent = 'Kiểm tra cập nhật';
        }
    } catch (e) {
        alert('Không thể kết nối đến máy chủ.');
        checkUpdatesBtn.disabled = false;
        checkUpdatesBtn.textContent = 'Kiểm tra cập nhật';
    }
};

scanFoldersBtn.onclick = async () => {
    scanFoldersBtn.disabled = true;
    scanFoldersBtn.textContent = 'Đang quét...';
    try {
        const response = await fetch('/api/library/scan', { method: 'POST' });
        const data = await response.json();
        alert(`Đã quét xong. Đã thêm ${data.added} truyện mới, cập nhật ${data.updated} truyện.`);
        renderLibrary();
    } catch (e) {
        alert('Lỗi khi quét thư mục.');
    } finally {
        scanFoldersBtn.disabled = false;
        scanFoldersBtn.textContent = 'Quét thư mục local';
    }
};

librarySearchInput.oninput = filterLibrary;

// Initial Load
initWebSocket();
fetchSettings();

// Close results when clicking outside
document.addEventListener('click', (e) => {
    if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
        searchResults.style.display = 'none';
    }
});
