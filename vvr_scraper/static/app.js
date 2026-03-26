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
    }
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

function refreshLogViewer() {
    logViewer.innerHTML = '';
    const task = activeTasks.get(selectedTaskId);
    if (task) {
        task.logs.forEach(renderLogEntry);
    } else {
        logViewer.innerHTML = '<div class="log-entry system">Chọn một nhiệm vụ để xem nhật ký...</div>';
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
        document.getElementById('previewDescContent').textContent = data.description;
        
        // Try to find a real cover URL if possible (though scraper_core saves it locally)
        // For now keep placeholder or a fallback
        document.getElementById('previewCover').src = 'https://via.placeholder.com/140x200?text=VVR+T';

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
            <span class="task-percent">0%</span>
        </div>
        <div class="progress-bar">
            <div class="progress-fill" style="width: 0%"></div>
        </div>
        <div class="task-status">Đang khởi tạo...</div>
    `;
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
        if (el) el.querySelector('.task-status').textContent = data.status;
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

// Initial Load
initWebSocket();

// Close results when clicking outside
document.addEventListener('click', (e) => {
    if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
        searchResults.style.display = 'none';
    }
});
