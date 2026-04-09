import { addLogEntry, updateTask, finishTask, showNotification } from './ui.js';

let socket;

export function initWebSocket() {
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

// Global UI handling for library checks (we define it here since it's closely tied to WS events)
function updateLibraryCheckProgress(current, total, title) {
    const checkUpdatesBtn = document.getElementById('checkUpdatesBtn');
    if (checkUpdatesBtn) {
        checkUpdatesBtn.disabled = true;
        const percent = Math.round((current / total) * 100);
        checkUpdatesBtn.innerHTML = `<span class="spinner"></span> (${percent}%) ${title}`;
        
        let progressBar = document.getElementById('libraryCheckProgressBar');
        if (!progressBar) {
            progressBar = document.createElement('div');
            progressBar.id = 'libraryCheckProgressBar';
            progressBar.className = 'global-progress-bar';
            progressBar.innerHTML = '<div class="progress-fill"></div>';
            const container = document.getElementById('globalProgressBarContainer');
            if (container) container.appendChild(progressBar);
        }
        progressBar.querySelector('.progress-fill').style.width = `${percent}%`;
        progressBar.style.display = 'block';
    }
}

function finishLibraryCheck(updatesFound) {
    const checkUpdatesBtn = document.getElementById('checkUpdatesBtn');
    if (checkUpdatesBtn) {
        checkUpdatesBtn.disabled = false;
        checkUpdatesBtn.textContent = 'Kiểm tra cập nhật';
        
        const progressBar = document.getElementById('libraryCheckProgressBar');
        if (progressBar) progressBar.style.display = 'none';
        
        // This relies on main app event bus or global renderLibrary event
        window.dispatchEvent(new Event('render-library'));
        
        if (updatesFound > 0) {
            showNotification(`Đã tìm thấy ${updatesFound} bản cập nhật mới!`);
            // Also pushing Desktop notification if interested
            import('./notifications.js').then(module => {
                module.sendDesktopNotification('Thư viện cập nhật', { body: `Có ${updatesFound} truyện mới.` });
            });
        } else {
            showNotification('Thư viện đã ở phiên bản mới nhất.');
        }
    }
}
