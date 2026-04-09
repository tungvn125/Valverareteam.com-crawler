import { state } from './state.js';
import { getActionableErrorSuggestion, sendDesktopNotification } from './notifications.js';
import { ETACalculator } from './utils.js';
import { taskAction, fetchTaskLogs } from './api.js';

export const etaCalc = new ETACalculator();

// Shared UI Functions
export function showNotification(msg) {
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

// Log Viewer
export function addLogEntry(taskId, data) {
    const task = state.activeTasks.get(taskId);
    if (!task && taskId !== 'system') return;

    const logMsg = taskId === 'system' ? data : data;
    if (taskId !== 'system') {
        task.logs.push(logMsg);
    }

    if (state.selectedTaskId === taskId || (taskId === 'system' && !state.selectedTaskId)) {
        renderLogEntry(logMsg);
    }
}

export function renderLogEntry(data) {
    const logViewer = document.getElementById('logViewer');
    if (!logViewer) return;

    const entry = document.createElement('div');
    entry.className = `log-entry ${data.level || ''}`;
    
    // Actionable Errors Parser inclusion
    let errActionHTML = '';
    if (data.level === 'ERROR') {
        const suggestion = getActionableErrorSuggestion(data.message);
        if (suggestion) {
            errActionHTML = `<div style="margin-top:5px; padding:8px; background:var(--error); color:#fff; border-radius:5px; font-weight:bold;">💡 Gợi ý xử lý: ${suggestion}</div>`;
        }
    }

    entry.innerHTML = `<span class="time">[${data.time || new Date().toLocaleTimeString()}]</span> <span class="level ${data.level || 'INFO'}">${data.level || 'INFO'}</span> ${data.message} ${errActionHTML}`;
    logViewer.appendChild(entry);
    logViewer.scrollTop = logViewer.scrollHeight;
}

export async function refreshLogViewer() {
    const logViewer = document.getElementById('logViewer');
    logViewer.innerHTML = '';
    if (!state.selectedTaskId) {
        logViewer.innerHTML = '<div class="log-entry system">Chọn một nhiệm vụ để xem nhật ký...</div>';
        return;
    }

    const task = state.activeTasks.get(state.selectedTaskId);
    if (!task) return;

    if (task.logs && task.logs.length > 0) {
        task.logs.forEach(renderLogEntry);
    } else {
        logViewer.innerHTML = '<div class="log-entry system">Đang tải nhật ký...</div>';
    }

    const currentSelectedId = state.selectedTaskId;
    try {
        const logs = await fetchTaskLogs(state.selectedTaskId);
        if (currentSelectedId === state.selectedTaskId) {
            task.logs = Array.isArray(logs) ? logs : [];
            logViewer.innerHTML = '';
            task.logs.forEach(renderLogEntry);
        }
    } catch (e) {
        console.error('Failed to fetch logs', e);
    }
}

// Task UI Functions
export function createTaskUI(taskId, title) {
    const taskList = document.getElementById('taskList');
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

    taskItem.querySelector('.pause-btn').onclick = async (e) => {
        e.stopPropagation();
        try {
            await taskAction(taskId, 'pause');
            updateTask(taskId, { status: 'Pausing...' });
        } catch(err) { console.error(err); }
    };
    taskItem.querySelector('.resume-btn').onclick = async (e) => {
        e.stopPropagation();
        try {
            await taskAction(taskId, 'resume');
            updateTask(taskId, { status: 'Resuming...' });
            etaCalc.start(taskId); // Reset ETA when resuming
        } catch(err) { console.error(err); }
    };
    taskItem.querySelector('.cancel-btn').onclick = async (e) => {
        e.stopPropagation();
        if (!confirm('Bạn có chắc chắn muốn hủy nhiệm vụ này?')) return;
        try {
            await taskAction(taskId, 'cancel');
            taskItem.remove();
            state.activeTasks.delete(taskId);
            etaCalc.remove(taskId);
            if (state.selectedTaskId === taskId) {
                state.selectedTaskId = null;
                refreshLogViewer();
            }
        } catch(err) { console.error(err); }
    };

    taskList.appendChild(taskItem);
    state.activeTasks.set(taskId, { id: taskId, title, logs: [], status: 'Đang khởi tạo...', percent: 0 });
    etaCalc.start(taskId);
    
    if (!state.selectedTaskId) selectTask(taskId);
}

export function selectTask(taskId) {
    if (state.selectedTaskId) {
        const oldEl = document.getElementById(`task-${state.selectedTaskId}`);
        if (oldEl) oldEl.classList.remove('selected');
    }

    state.selectedTaskId = taskId;
    const newEl = document.getElementById(`task-${taskId}`);
    if (newEl) newEl.classList.add('selected');

    const task = state.activeTasks.get(taskId);
    const infoEl = document.getElementById('selectedTaskInfo');
    if (infoEl) infoEl.textContent = task ? `Đang xem: ${task.title}` : '';

    refreshLogViewer();
}

export function updateTask(taskId, data) {
    const task = state.activeTasks.get(taskId);
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
            const pauseBtn = el.querySelector('.pause-btn');
            const resumeBtn = el.querySelector('.resume-btn');
            
            if (data.status.toLowerCase().includes('pause') || data.status.toLowerCase().includes('tạm dừng')) {
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
            const etaStr = etaCalc.getETA(taskId, data.percent);
            el.querySelector('.task-percent').textContent = `${data.percent}% (ETA: ${etaStr})`;
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

export function finishTask(taskId, path) {
    const el = document.getElementById(`task-${taskId}`);
    if (el) el.remove();
    const task = state.activeTasks.get(taskId);
    
    if (task) {
        sendDesktopNotification(`Tải xong: ${task.title}`, { body: `Lưu tại: ${path}` });
        
        const clist = document.getElementById('completedList');
        const item = document.createElement('div');
        item.className = 'completed-item';
        item.innerHTML = `<span class="status-dot tooltip" title="Lưu tại: ${path}"></span> <span class="title">${task.title}</span>`;
        clist.prepend(item);
    }
    
    state.activeTasks.delete(taskId);
    etaCalc.remove(taskId);
    if (state.selectedTaskId === taskId) {
        document.getElementById('selectedTaskInfo').textContent = '';
        state.selectedTaskId = null;
    }
}
