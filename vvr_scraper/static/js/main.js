import { state } from './state.js';
import * as api from './api.js';
import * as ui from './ui.js';
import { initWebSocket } from './websocket.js';
import { requestNotificationPermission } from './notifications.js';

// DOM Elements
const searchInput = document.getElementById('searchInput');
const searchResults = document.getElementById('searchResults');
const navSearch = document.getElementById('navSearch');
const navLibrary = document.getElementById('navLibrary');
const searchView = document.getElementById('searchView');
const libraryView = document.getElementById('libraryView');
const tasksView = document.getElementById('tasksView');
const libraryActionsView = document.getElementById('libraryActionsView');
const libraryGrid = document.getElementById('libraryGrid');
const librarySearchInput = document.getElementById('librarySearchInput');
const checkUpdatesBtn = document.getElementById('checkUpdatesBtn');
const scanFoldersBtn = document.getElementById('scanFoldersBtn');
const batchImportBtn = document.getElementById('batchImportBtn');
const batchImportModal = document.getElementById('batchImportModal');
const batchImportUrls = document.getElementById('batchImportUrls');
const startBatchDownloadBtn = document.getElementById('startBatchDownloadBtn');
const libraryStats = document.getElementById('libraryStats');

const themeToggle = document.getElementById('themeToggle');
const vfxIntensityInput = document.getElementById('vfxIntensity');
const vfxIntensityValue = document.getElementById('vfxIntensityValue');
const settingsBtn = document.getElementById('settingsBtn');
const settingsModal = document.getElementById('settingsModal');
const settingsForm = document.getElementById('settingsForm');
const browseDefaultBtn = document.getElementById('browseDefaultBtn');

const downloadModal = document.getElementById('downloadModal');
const selectionModal = document.getElementById('selectionModal');
const chapterTreeContainer = document.getElementById('chapterTreeContainer');
const chapterSearchInput = document.getElementById('chapterSearchInput');
const previewModal = document.getElementById('previewModal');
const outputPathInput = document.getElementById('outputPathInput');
const browseBtn = document.getElementById('browseBtn');

let defaultOutputFolder = '';
let libraryData = [];

function openModal(modal) {
    if (!modal) return;
    modal.style.display = 'flex';
}

function closeModal(modal) {
    if (!modal) return;
    modal.style.display = 'none';
}

function isModalOpen(modal) {
    return !!modal && modal.style.display === 'flex';
}

function initModalDismissal(modal) {
    if (!modal) return;
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal(modal);
        }
    });
}

// Init Theme & Settings
function initTheme() {
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

    let vfxIntensity = localStorage.getItem('vfxIntensity') || 100;
    if (vfxIntensityInput) {
        vfxIntensityInput.value = vfxIntensity;
        vfxIntensityValue.textContent = `${vfxIntensity}%`;
        vfxIntensityInput.oninput = () => {
            vfxIntensity = vfxIntensityInput.value;
            vfxIntensityValue.textContent = `${vfxIntensity}%`;
            localStorage.setItem('vfxIntensity', vfxIntensity);
        };
    }
}

// Navigation
function initNavigation() {
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
}

// Global Library Render Event
window.addEventListener('render-library', () => {
    if (navLibrary.classList.contains('active')) {
        renderLibrary();
    }
});

// Settings Logic
async function openSettings() {
    try {
        const data = await api.fetchSettings();
        defaultOutputFolder = data.default_output_folder || '';
        document.getElementById('globalNumWorkers').value = data.num_workers || 1;
        document.getElementById('defaultOutputFolder').value = defaultOutputFolder;
        
        if (!outputPathInput.value && defaultOutputFolder) {
            outputPathInput.value = defaultOutputFolder;
        }
        openModal(settingsModal);
    } catch (e) {
        console.error(e);
    }
}

settingsBtn.onclick = openSettings;

document.querySelector('#settingsModal .btn-secondary').onclick = () => closeModal(settingsModal);

settingsForm.onsubmit = async (e) => {
    e.preventDefault();
    const num_workers = parseInt(document.getElementById('globalNumWorkers').value);
    const default_output_folder = document.getElementById('defaultOutputFolder').value.trim();
    try {
        await api.saveSettings({ num_workers, default_output_folder });
        closeModal(settingsModal);
    } catch (e) {
        alert('Lỗi khi lưu cài đặt.');
    }
};

browseDefaultBtn.onclick = async () => {
    try {
        const data = await api.browseFolder();
        if (data.path) document.getElementById('defaultOutputFolder').value = data.path;
        else if (data.error) alert(data.error);
    } catch(e) {}
};

browseBtn.onclick = async () => {
    try {
        const data = await api.browseFolder();
        if (data.path) outputPathInput.value = data.path;
        else if (data.error) alert(data.error);
    } catch (e) {}
};

// Search Logic
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
            const results = await api.searchNovels(query);
            displaySearchResults(results);
        } catch (e) {}
    }, 500);
});

function displaySearchResults(results) {
    searchResults.innerHTML = '';
    if (results.length === 0) {
        searchResults.innerHTML = '<div class="search-item">Không tìm thấy kết quả.</div>';
    } else {
        results.forEach(item => {
            const sourceLabel = item.source === 'valvrareteam' ? 'VVR' :
                               item.source === 'truyenfull' ? 'TF' :
                               item.source === 'lnhako' ? 'Hako' : '';
            const sourceTag = sourceLabel ? ` [${sourceLabel}]` : '';
            const div = document.createElement('div');
            div.className = 'search-item';
            div.innerHTML = `
                <span class="title">${esc(item.title)}${esc(sourceTag)}</span>
                <span class="meta">${esc(item.author || '')} | ${esc(item.status || '')} | ${item.totalChapters || '?'} chương</span>
            `;
            div.onclick = () => openPreviewModal(item);
            searchResults.appendChild(div);
        });
    }
    searchResults.style.display = 'block';
}

document.addEventListener('click', (e) => {
    if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
        searchResults.style.display = 'none';
    }
});

// Modals Flow
async function openPreviewModal(item) {
    document.getElementById('previewTitle').textContent = item.title;
    document.getElementById('previewAuthor').textContent = item.author || '-';
    document.getElementById('previewStatus').textContent = item.status || '-';
    document.getElementById('previewTotalChapters').textContent = item.totalChapters || '-';
    document.getElementById('previewCover').src = 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22140%22 height=%22200%22 fill=%22%23333%22%3E%3Crect width=%22100%25%22 height=%22100%25%22 fill=%22%23222%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 font-size=%2214%22 fill=%22%23888%22 text-anchor=%22middle%22 dy=%22.3em%22%3ELoading...%3C/text%3E%3C/svg%3E';
    document.getElementById('previewGenres').innerHTML = '';
    document.getElementById('previewWordCount').textContent = '-';
    document.getElementById('previewViews').textContent = '-';
    document.getElementById('previewDescContent').textContent = 'Đang tải thông tin...';
    
    openModal(previewModal);
    searchResults.style.display = 'none';

    try {
        const data = await api.fetchStoryInfo(item.slug);
        document.getElementById('previewAuthor').textContent = data.author;
        document.getElementById('previewTotalChapters').textContent = data.total_chapters;
        document.getElementById('previewWordCount').textContent = data.word_count;
        document.getElementById('previewViews').textContent = data.views;
        document.getElementById('previewDescContent').textContent = data.description;
        
        if (data.cover_url) {
            const coverImg = document.getElementById('previewCover');
            coverImg.src = data.cover_url;
            coverImg.onerror = () => { coverImg.src = 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22180%22 height=%22240%22 fill=%22%23333%22%3E%3Crect width=%22100%25%22 height=%22100%25%22 fill=%22%23222%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 font-size=%2216%22 fill=%22%23888%22 text-anchor=%22middle%22 dy=%22.3em%22%3ENo Cover%3C/text%3E%3C/svg%3E'; };
        }
        
        if (data.genres) {
            data.genres.forEach(genre => {
                const span = document.createElement('span');
                span.className = 'genre-tag';
                span.textContent = genre;
                document.getElementById('previewGenres').appendChild(span);
            });
        }
    } catch (e) {
        document.getElementById('previewDescContent').textContent = 'Không thể tải thông tin chi tiết.';
    }

    document.getElementById('selectChaptersBtn').onclick = () => {
        closeModal(previewModal);
        openSelectionModal(item);
    };
}

document.querySelector('#previewModal .btn-secondary').onclick = () => closeModal(previewModal);

// Chapter Selection
async function openSelectionModal(item) {
    state.currentSlug = item.slug;
    state.currentTitle = item.title;
    openModal(selectionModal);
    chapterTreeContainer.innerHTML = '<div class="loading-msg">Đang tải danh sách chương...</div>';
    chapterSearchInput.value = '';
    state.selectedUrls.clear();
    
    try {
        state.currentTreeData = await api.fetchChapters(item.slug);
        renderChapterTree(state.currentTreeData);
    } catch (e) {
        chapterTreeContainer.innerHTML = '<div class="loading-msg">Không thể tải danh sách chương.</div>';
    }
}

document.querySelector('#selectionModal .btn-secondary').onclick = () => closeModal(selectionModal);

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
            
            if (!chapter.locked) {
                chapterCheckbox.checked = true;
                state.selectedUrls.add(chapter.url);
            }

            const chapterLabel = document.createElement('label');
            chapterLabel.htmlFor = `chap-${vIdx}-${cIdx}`;
            chapterLabel.textContent = chapter.title;

            chapterCheckbox.onchange = () => {
                if (chapterCheckbox.checked) state.selectedUrls.add(chapter.url);
                else state.selectedUrls.delete(chapter.url);
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
                if (chk.checked) state.selectedUrls.add(chk.dataset.url);
                else state.selectedUrls.delete(chk.dataset.url);
            });
            updateSelectionStats(totalChapters);
        };

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

function updateSelectionStats() {
    document.getElementById('selectedChaptersCount').textContent = state.selectedUrls.size;
}

chapterSearchInput.addEventListener('input', () => {
    const query = chapterSearchInput.value.toLowerCase().trim();
    const volumeItems = chapterTreeContainer.querySelectorAll('.volume-item');
    volumeItems.forEach(volItem => {
        const chapters = volItem.querySelectorAll('.chapter-item');
        let hasVisible = false;
        chapters.forEach(chapItem => {
            const title = chapItem.querySelector('label').textContent.toLowerCase();
            if (title.includes(query)) { chapItem.classList.remove('hidden'); hasVisible = true; }
            else { chapItem.classList.add('hidden'); }
        });
        if (hasVisible || volItem.querySelector('.volume-header label').textContent.toLowerCase().includes(query)) {
            volItem.classList.remove('hidden');
        } else {
            volItem.classList.add('hidden');
        }
    });
});

document.getElementById('confirmSelectionBtn').onclick = () => {
    if (state.selectedUrls.size === 0) { alert('Vui lòng chọn ít nhất một chương.'); return; }
    closeModal(selectionModal);
    document.getElementById('modalTitle').textContent = `Tải: ${state.currentTitle}`;
    document.getElementById('modalSlug').value = state.currentSlug;
    openModal(downloadModal);
};

document.querySelector('#downloadModal .modal-actions .btn-secondary').onclick = () => closeModal(downloadModal);

document.getElementById('downloadForm').onsubmit = async (e) => {
    e.preventDefault();
    const formats = Array.from(document.querySelectorAll('input[name="format"]:checked')).map(cb => cb.value);
    const slug = document.getElementById('modalSlug').value;
    const tasks = parseInt(document.getElementById('tasksInput').value);
    const skipIllus = document.getElementById('skipIllus').checked;
    const outputPath = outputPathInput.value.trim();

    if (formats.length === 0) { alert('Vui lòng chọn ít nhất một định dạng.'); return; }

    try {
        const data = await api.startDownload({ 
            slug, formats, tasks, skip_illustrations: skipIllus,
            output_folder: outputPath || null, selected_urls: Array.from(state.selectedUrls)
        });
        ui.createTaskUI(data.task_id, state.currentTitle || slug);
        closeModal(downloadModal);
    } catch (e) {
        alert('Không thể bắt đầu tải xuống.');
    }
};

batchImportBtn.onclick = () => {
    openModal(batchImportModal);
    batchImportUrls.value = '';
};
document.querySelector('#batchImportModal .btn-secondary').onclick = () => closeModal(batchImportModal);

startBatchDownloadBtn.onclick = async () => {
    const content = batchImportUrls.value.trim();
    if (!content) { alert('Vui lòng nhập ít nhất một URL hoặc Slug.'); return; }
    const items = content.split('\n').map(l => l.trim()).filter(l => l.length > 0);
    startBatchDownloadBtn.disabled = true;
    startBatchDownloadBtn.textContent = 'Đang xử lý...';
    try {
        const data = await api.batchImport(items);
        alert(`Đã thêm ${data.count} truyện vào hàng chờ.`);
        closeModal(batchImportModal);
    } catch (e) {
        alert('Lỗi: ' + e.message);
    } finally {
        startBatchDownloadBtn.disabled = false;
        startBatchDownloadBtn.textContent = 'Bắt đầu tải';
    }
};

// Library
async function renderLibrary() {
    libraryGrid.innerHTML = '<div class="loading-msg">Đang tải thư viện...</div>';
    if (!document.getElementById('libraryWarning')) {
        const warning = document.createElement('p');
        warning.id = 'libraryWarning';
        warning.className = 'warning-text';
        warning.textContent = 'Lưu ý: Không di chuyển thư mục truyện sau khi tải để tránh lỗi OPDS.';
        if (libraryGrid.parentNode) libraryGrid.parentNode.insertBefore(warning, libraryGrid);
    }
    
    try {
        const res = await fetch('/api/library');
        libraryData = await res.json();
        filterLibrary();
        updateLibraryStats();
        updateSyncBar();
    } catch (e) {
        libraryGrid.innerHTML = '<div class="error-msg">Không thể tải thư viện.</div>';
    }
}

function filterLibrary() {
    const query = librarySearchInput.value.toLowerCase().trim();
    const filtered = libraryData.filter(n => n.title.toLowerCase().includes(query) || (n.author && n.author.toLowerCase().includes(query)));
    
    libraryGrid.innerHTML = '';
    if (filtered.length === 0) {
        libraryGrid.innerHTML = '<div class="empty-msg">Không tìm thấy truyện nào.</div>';
        return;
    }
    
    filtered.forEach(novel => {
        const card = document.createElement('div');
        card.className = 'novel-card';
        
        let statusClass = 'synced', statusText = 'Đã khớp', updateBadge = '';
        if (novel.has_updates === 1) {
            statusClass = 'update-available'; statusText = 'Có chương mới';
            const diff = (novel.server_chapter_count || 0) - (novel.last_synced_count || 0);
            updateBadge = `<div class="update-ribbon">+${diff > 0 ? diff : 'New'}</div>`;
        } else if (novel.status === 'unavailable') {
            statusClass = 'unavailable'; statusText = 'Mất link';
        } else if (novel.status === 'archived') {
            statusClass = 'archived'; statusText = 'Đã lưu trữ';
        }

        const hasCinema = novel.formats && novel.formats.includes('AD-MP3');
        const cinemaBtn = hasCinema && novel.output_folder ? `<button class="btn-primary btn-sm watch-cinema-btn" style="background: linear-gradient(135deg, #00cfd5, #a855f7); border: none;">Xem Cinema 🎬</button>` : '';
        const correctBtn = hasCinema ? `<button class="btn-secondary btn-sm correct-novel-btn">Sửa kịch bản</button>` : '';
        
        // Escape HTML to prevent XSS
        const esc = (s) => s ? s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;') : '';
        const safeTitle = esc(novel.title);
        const safeAuthor = esc(novel.author || 'Ẩn danh');
        const safeCoverUrl = esc(novel.cover_url || '');
        const safeStatusClass = esc(statusClass);
        const safeStatusText = esc(statusText);
        const noCoverSvg = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='240' fill='%23333'%3E%3Crect width='100%25' height='100%25' fill='%23222'/%3E%3Ctext x='50%25' y='50%25' font-size='16' fill='%23888' text-anchor='middle' dy='.3em'%3ENo Cover%3C/text%3E%3C/svg%3E";

        card.innerHTML = `
            ${updateBadge}
            <div class="card-cover">
                <img src="${safeCoverUrl || noCoverSvg}" alt="${safeTitle}" onerror="this.src='${noCoverSvg}'">
                <span class="status-badge ${safeStatusClass}">${safeStatusText}</span>
            </div>
            <div class="card-info">
                <div class="card-title" title="${safeTitle}">${safeTitle}</div>
                <div class="card-author">${safeAuthor}</div>
                <div class="card-meta">
                    <span>${novel.last_synced_count || novel.last_chapter_count || 0} chương</span>
                </div>
            </div>
            <div class="card-actions">
                ${cinemaBtn}
                ${correctBtn}
                <button class="btn-primary btn-sm update-novel-btn">Cập nhật</button>
                <button class="btn-secondary btn-sm preview-novel-btn">Chi tiết</button>
            </div>
        `;
        
        if (hasCinema && novel.output_folder) {
            card.querySelector('.watch-cinema-btn').onclick = (e) => {
                e.stopPropagation();
                let relPath = novel.output_folder;
                if (relPath && defaultOutputFolder && relPath.startsWith(defaultOutputFolder)) {
                    relPath = relPath.substring(defaultOutputFolder.length).replace(/^[\\\/]+/, '');
                }
                const intensity = localStorage.getItem('vfxIntensity') || 100;
                window.open(`/static/cinema.html?path=${encodeURIComponent(relPath)}&vfx=${intensity}`, '_blank');
            };
        }
        
        card.querySelector('.update-novel-btn').onclick = (e) => { e.stopPropagation(); openPreviewModal(novel); };
        card.querySelector('.preview-novel-btn').onclick = (e) => { e.stopPropagation(); openPreviewModal(novel); };
        
        const correctBtnEl = card.querySelector('.correct-novel-btn');
        if (correctBtnEl) {
            correctBtnEl.onclick = (e) => {
                e.stopPropagation();
                window.open(`/static/correction.html?slug=${encodeURIComponent(novel.slug)}`, '_blank');
            };
        }
        
        card.onclick = () => openPreviewModal(novel);
        
        libraryGrid.appendChild(card);
    });
}

function updateLibraryStats() {
    if (!libraryStats) return;
    const total = libraryData.length;
    const updates = libraryData.filter(n => n.has_updates === 1).length;
    libraryStats.innerHTML = `<p>Tổng số truyện: <strong>${total}</strong></p><p>Cần cập nhật: <strong style="color:var(--primary)">${updates}</strong></p>`;
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
            <div class="sync-info"><span class="sync-count">X</span> novels need syncing</div>
            <button id="syncAllBtn" class="btn-primary">Download All Updates</button>
        `;
        document.body.appendChild(syncBar);
        
        document.getElementById('syncAllBtn').onclick = async () => {
            const btn = document.getElementById('syncAllBtn');
            btn.disabled = true;
            btn.textContent = 'Queuing tasks...';
            try {
                const res = await fetch('/api/library/sync-all', { method: 'POST' });
                const data = await res.json();
                ui.showNotification(`Queued ${data.queued} incremental updates.`);
                renderLibrary();
                navSearch.click();
            } catch (e) { alert('Failed to sync all updates.'); } 
            finally { btn.disabled = false; btn.textContent = 'Download All Updates'; }
        };
    }
    
    syncBar.querySelector('.sync-count').textContent = updatedNovels.length;
    syncBar.classList.add('show');
}

checkUpdatesBtn.onclick = async () => {
    checkUpdatesBtn.disabled = true;
    checkUpdatesBtn.textContent = 'Đang kiểm tra...';
    try {
        await api.checkLibraryUpdates();
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
        const res = await fetch('/api/library/scan', { method: 'POST' });
        const data = await res.json();
        alert(`Đã quét xong. Đã thêm ${data.added} truyện mới, cập nhật ${data.updated} truyện.`);
        renderLibrary();
    } catch (e) { alert('Lỗi khi quét thư mục.'); } 
    finally { scanFoldersBtn.disabled = false; scanFoldersBtn.textContent = 'Quét thư mục local'; }
};

librarySearchInput.oninput = filterLibrary;

[previewModal, selectionModal, downloadModal, settingsModal, batchImportModal].forEach(initModalDismissal);

document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const activeModal = [batchImportModal, downloadModal, selectionModal, previewModal, settingsModal].find(isModalOpen);
    if (activeModal) {
        closeModal(activeModal);
    }
});

// App Init
async function initApp() {
    initTheme();
    initNavigation();
    initWebSocket();
    
    try {
        const data = await api.fetchSettings();
        defaultOutputFolder = data.default_output_folder || '';
    } catch (e) {}

    // Require desktop notifications (quietly on init or we could trigger on first button press. But it's better to fire early)
    requestNotificationPermission().catch(console.error);

    renderLibrary();
}

initApp();
