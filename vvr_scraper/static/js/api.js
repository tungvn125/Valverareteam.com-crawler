/**
 * API Wrappers
 */

export async function fetchSettings() {
    const res = await fetch('/api/settings');
    if (!res.ok) throw new Error('Failed to fetch settings');
    return await res.json();
}

export async function saveSettings(settings) {
    const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
    });
    if (!res.ok) throw new Error('Failed to save settings');
    return await res.json();
}

export async function searchNovels(query) {
    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    if (!res.ok) throw new Error('Search failed');
    return await res.json();
}

export async function fetchStoryInfo(slug) {
    const res = await fetch(`/api/story_info?slug=${encodeURIComponent(slug)}`);
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    return data;
}

export async function fetchChapters(slug) {
    const res = await fetch(`/api/chapters?slug=${encodeURIComponent(slug)}`);
    if (!res.ok) throw new Error('Failed to fetch chapters');
    return await res.json();
}

export async function browseFolder() {
    const res = await fetch('/api/browse');
    return await res.json();
}

export async function batchImport(items) {
    const res = await fetch('/api/batch-import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to batch import');
    return data;
}

export async function startDownload(payload) {
    const res = await fetch('/api/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Failed to start download');
    return await res.json();
}

export async function fetchTaskLogs(taskId) {
    const res = await fetch(`/api/tasks/${taskId}/logs`);
    if (!res.ok) throw new Error('Failed to fetch logs');
    return await res.json();
}

export async function taskAction(taskId, action) {
    const res = await fetch(`/api/tasks/${taskId}/${action}`, { method: 'POST' });
    if (!res.ok) throw new Error(`Failed to ${action} task`);
    return res;
}

export async function checkLibraryUpdates() {
    const res = await fetch('/api/library/check-updates', { method: 'GET' });
    if (!res.ok) throw new Error('Failed to trigger update check');
    return await res.json();
}
