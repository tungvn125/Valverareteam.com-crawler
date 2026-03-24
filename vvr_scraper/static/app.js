// State
let socket;
const activeTasks = new Map();
const searchInput = document.getElementById('searchInput');
const searchResults = document.getElementById('searchResults');
const taskList = document.getElementById('taskList');
const completedList = document.getElementById('completedList');
const logViewer = document.getElementById('logViewer');
const downloadModal = document.getElementById('downloadModal');

// Init WebSocket
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new WebSocket(`${protocol}//${window.location.host}/ws/tasks`);

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleSocketMessage(data);
    };

    socket.onclose = () => {
        addLogEntry({ time: new Date().toLocaleTimeString(), level: 'ERROR', message: 'WebSocket connection closed. Reconnecting...' });
        setTimeout(initWebSocket, 3000);
    };
}

function handleSocketMessage(data) {
    if (data.type === 'log') {
        addLogEntry(data);
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
function addLogEntry(data) {
    const entry = document.createElement('div');
    entry.className = `log-entry ${data.level || ''}`;
    entry.innerHTML = `<span class="time">[${data.time}]</span> <span class="level ${data.level}">${data.level}</span> ${data.message}`;
    logViewer.appendChild(entry);
    logViewer.scrollTop = logViewer.scrollHeight;
}

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
            div.onclick = () => openDownloadModal(item);
            searchResults.appendChild(div);
        });
    }
    searchResults.style.display = 'block';
}

// Modal Handling
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

    if (formats.length === 0) {
        alert('Vui lòng chọn ít nhất một định dạng.');
        return;
    }

    try {
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slug, formats, tasks, skip_illustrations: skipIllus })
        });
        const data = await response.json();
        createTaskUI(data.task_id, slug);
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
    activeTasks.set(taskId, { id: taskId, title });
}

function updateTask(taskId, data) {
    const el = document.getElementById(`task-${taskId}`);
    if (!el) return;

    if (data.title) el.querySelector('.task-title').textContent = data.title;
    if (data.status) el.querySelector('.task-status').textContent = data.status;
    if (data.percent !== undefined) {
        el.querySelector('.task-percent').textContent = `${data.percent}%`;
        el.querySelector('.progress-fill').style.width = `${data.percent}%`;
    }
    if (data.error) {
        el.style.borderLeftColor = 'var(--error)';
        el.querySelector('.task-percent').style.color = 'var(--error)';
    }
}

function finishTask(taskId, path) {
    const taskEl = document.getElementById(`task-${taskId}`);
    if (taskEl) taskEl.remove();

    const task = activeTasks.get(taskId);
    const completedItem = document.createElement('div');
    completedItem.className = 'completed-item';
    completedItem.innerHTML = `
        <div class="status-dot"></div>
        <span>${task ? task.title : 'Nhiệm vụ'} (Đã xong)</span>
    `;
    completedList.prepend(completedItem);
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
