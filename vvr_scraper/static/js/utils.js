/**
 * Format timestamp
 */
export function formatTime(dateStr) {
    if (!dateStr) return '';
    return new Date(dateStr).toLocaleTimeString();
}

/**
 * Format bytes
 */
export function formatBytes(bytes, decimals = 2) {
    if (!+bytes) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

/**
 * ETA Calculator
 */
export class ETACalculator {
    constructor() {
        this.tasks = new Map();
    }

    // Call this when task is added or percent is 0
    start(taskId) {
        this.tasks.set(taskId, { startTime: Date.now(), lastPercent: 0 });
    }

    getETA(taskId, percent) {
        if (!this.tasks.has(taskId)) {
            this.start(taskId);
            return 'Đang tính...';
        }

        const taskData = this.tasks.get(taskId);
        
        // Prevent division by zero or very small numbers early on
        if (percent <= 2) return 'Đang tính...';

        const elapsedMs = Date.now() - taskData.startTime;
        const percentDecimal = percent / 100;
        
        const totalEstimatedMs = elapsedMs / percentDecimal;
        const remainingMs = totalEstimatedMs - elapsedMs;

        if (remainingMs < 0 || !isFinite(remainingMs)) return 'Đang tính...';

        return this.formatMs(remainingMs);
    }

    formatMs(ms) {
        const totalSeconds = Math.max(0, Math.floor(ms / 1000));
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        if (minutes > 0) {
            return `${minutes}m ${seconds}s`;
        }
        return `${seconds}s`;
    }

    remove(taskId) {
        this.tasks.delete(taskId);
    }
}
