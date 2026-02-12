import { API } from './api.js';

// State
const state = {
    currentView: 'accounts', // 'accounts' | 'files'
    accounts: [],
    currentAccountId: null,
    currentFolderId: 'root',
    files: [],
    breadcrumbs: [],
    darkMode: localStorage.getItem('theme') === 'dark'
};

// DOM Elements
const elements = {
    app: document.getElementById('app'),
    viewContainer: document.getElementById('view-container'),
    navAccounts: document.querySelector('.nav-item[data-view="accounts"]'),
    accountNavList: document.getElementById('account-nav-list'),
    viewAccounts: document.getElementById('view-accounts'),
    viewFiles: document.getElementById('view-files'),
    accountsList: document.getElementById('accounts-list'),
    fileList: document.getElementById('file-list'),
    breadcrumbs: document.getElementById('breadcrumbs'),
    linkAccountBtn: document.getElementById('link-account-btn'),
    themeToggle: document.getElementById('theme-toggle'),
    uploadBtn: document.getElementById('upload-btn'),
    createFolderBtn: document.getElementById('create-folder-btn'),
    currentAccountName: document.getElementById('current-account-name'),
};

// Utils
function formatSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDate(dateString) {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('en-GB', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
}

// Initialization
async function init() {
    setupEventListeners();
    applyTheme();

    // Check URL params for view routing (simple hash routing)
    if (window.location.hash.startsWith('#files')) {
        const parts = window.location.hash.split('/');
        // #files/account_id/folder_id
        if (parts[1]) {
            await loadFilesView(parts[1], parts[2] || 'root');
            return;
        }
    }

    await loadAccountsView();
}

function setupEventListeners() {
    elements.linkAccountBtn.addEventListener('click', () => API.linkAccount());

    elements.navAccounts.addEventListener('click', () => {
        window.location.hash = '';
        loadAccountsView();
    });

    elements.themeToggle.addEventListener('click', toggleTheme);

    elements.uploadBtn.addEventListener('click', triggerUpload);
    elements.createFolderBtn.addEventListener('click', triggerCreateFolder);
}

function toggleTheme() {
    state.darkMode = !state.darkMode;
    localStorage.setItem('theme', state.darkMode ? 'dark' : 'light');
    applyTheme();
}

function applyTheme() {
    if (state.darkMode) {
        document.body.classList.add('dark-mode');
        elements.themeToggle.innerHTML = '<i class="ri-sun-line"></i>';
    } else {
        document.body.classList.remove('dark-mode');
        elements.themeToggle.innerHTML = '<i class="ri-moon-line"></i>';
    }
}

// Views
async function loadAccountsView() {
    state.currentView = 'accounts';
    elements.navAccounts.classList.add('active');

    // Hide/Show sections
    elements.viewAccounts.classList.add('active');
    elements.viewAccounts.classList.remove('hidden');
    elements.viewFiles.classList.remove('active');
    elements.viewFiles.classList.add('hidden');

    // Reset breadcrumbs
    renderBreadcrumbs([]);

    elements.accountsList.innerHTML = '<div class="loading-spinner"><i class="ri-loader-4-line ri-spin"></i> Loading...</div>';

    try {
        const data = await API.getAccounts();
        state.accounts = data.accounts;
        renderAccounts();
        renderSidebarAccounts();
    } catch (err) {
        elements.accountsList.innerHTML = `<div class="error">Failed to load accounts: ${err.message}</div>`;
    }
}

async function loadFilesView(accountId, folderId = 'root') {
    state.currentView = 'files';
    state.currentAccountId = accountId;
    state.currentFolderId = folderId;
    window.location.hash = `#files/${accountId}/${folderId}`;

    elements.navAccounts.classList.remove('active');

    elements.viewAccounts.classList.remove('active');
    elements.viewAccounts.classList.add('hidden');
    elements.viewFiles.classList.add('active');
    elements.viewFiles.classList.remove('hidden');

    elements.fileList.innerHTML = '<div class="loading-spinner"><i class="ri-loader-4-line ri-spin"></i> Loading files...</div>';

    try {
        // Ensure account name is known (if coming deeply linked, might need to fetch account info)
        let account = state.accounts.find(a => a.id === accountId);
        if (!account) {
            // Fetch accounts if not loaded yet
            const data = await API.getAccounts();
            state.accounts = data.accounts;
            renderSidebarAccounts();
            account = state.accounts.find(a => a.id === accountId);
        }
        if (account) {
            elements.currentAccountName.textContent = account.display_name + " - Files";
        }

        // Fetch Files
        const filesData = await API.getFiles(accountId, folderId);
        state.files = filesData.items;
        renderFiles();

        // Fetch and Render Breadcrumbs
        if (folderId !== 'root') {
            try {
                const pathData = await API.getPath(accountId, folderId);
                // Transform pathData to breadcrumbs
                const breads = pathData.breadcrumb.map(b => ({
                    name: b.name === 'root' ? 'Root' : b.name,
                    id: b.id
                }));
                renderBreadcrumbs(breads);
            } catch (e) {
                console.warn("Failed to load breadcrumbs", e);
                // Fallback breadcrumbs
                renderBreadcrumbs([{ name: 'Root', id: 'root' }, { name: 'Current', id: folderId }]);
            }
        } else {
            renderBreadcrumbs([{ name: 'Root', id: 'root' }]);
        }

    } catch (err) {
        elements.fileList.innerHTML = `<div class="error">Failed to load files: ${err.message}</div>`;
    }
}

// Rendering
function renderAccounts() {
    elements.accountsList.innerHTML = '';
    if (state.accounts.length === 0) {
        elements.accountsList.innerHTML = '<div class="empty-state">No accounts linked. Click "Link Account" to get started.</div>';
        return;
    }

    state.accounts.forEach(account => {
        const card = document.createElement('div');
        card.className = 'account-card';
        card.onclick = () => loadFilesView(account.id);

        card.innerHTML = `
            <div class="account-card-header">
                <div class="provider-icon"><i class="ri-microsoft-fill"></i></div>
                <div class="account-status status-active">Active</div>
            </div>
            <div class="account-email">${account.email}</div>
            <div class="account-id">ID: ${account.id.substring(0, 8)}...</div>
            <div class="account-footer">
                <span><i class="ri-calendar-line"></i> ${new Date(account.created_at).toLocaleDateString()}</span>
                <i class="ri-arrow-right-line"></i>
            </div>
        `;
        elements.accountsList.appendChild(card);
    });
}

function renderSidebarAccounts() {
    elements.accountNavList.innerHTML = '';
    state.accounts.forEach(account => {
        const item = document.createElement('div');
        item.className = 'nav-item';
        item.style.fontSize = '0.85rem';
        item.innerHTML = `<i class="ri-hard-drive-2-line"></i> ${account.display_name}`;
        item.onclick = () => loadFilesView(account.id);
        elements.accountNavList.appendChild(item);
    });
}

function renderFiles() {
    elements.fileList.innerHTML = '';
    if (state.files.length === 0) {
        elements.fileList.innerHTML = '<div class="loading-spinner">This folder is empty.</div>';
        return;
    }

    // Sort: Folders first, then files
    const sortedFiles = [...state.files].sort((a, b) => {
        const aIsFolder = a.item_type === 'folder';
        const bIsFolder = b.item_type === 'folder';
        if (aIsFolder === bIsFolder) return a.name.localeCompare(b.name);
        return aIsFolder ? -1 : 1;
    });

    sortedFiles.forEach(file => {
        const row = document.createElement('div');
        row.className = 'file-item';

        const isFolder = file.item_type === 'folder';
        const iconClass = isFolder ? 'ri-folder-3-fill file-icon-folder' : 'ri-file-3-fill file-icon-file';

        row.innerHTML = `
            <div class="col-icon">
                <i class="${iconClass}"></i>
            </div>
            <div class="col-name" data-id="${file.id}">
                ${file.name}
            </div>
            <div class="col-size">${isFolder ? '-' : formatSize(file.size)}</div>
            <div class="col-date">${formatDate(file.modified_at)}</div>
            <div class="col-actions file-actions-cell">
                ${!isFolder ? `<button title="Download" onclick="downloadFile('${file.id}')"><i class="ri-download-line"></i></button>` : ''}
                <button title="Delete" class="delete-btn" onclick="deleteItem('${file.id}')"><i class="ri-delete-bin-line"></i></button>
            </div>
        `;

        // Click name to navigate
        const nameCol = row.querySelector('.col-name');
        nameCol.addEventListener('click', () => {
            if (isFolder) {
                loadFilesView(state.currentAccountId, file.id);
            } else {
                downloadFile(file.id);
            }
        });

        elements.fileList.appendChild(row);
    });
}

function renderBreadcrumbs(pathItems) {
    elements.breadcrumbs.innerHTML = '';

    // Add Home
    const home = document.createElement('span');
    home.className = 'breadcrumb-item';
    home.textContent = 'Home';
    home.onclick = loadAccountsView;
    elements.breadcrumbs.appendChild(home);

    if (pathItems.length === 0) return;

    elements.breadcrumbs.appendChild(createSeparator());

    pathItems.forEach((item, index) => {
        const el = document.createElement('span');
        el.className = 'breadcrumb-item';
        el.textContent = item.name;
        el.onclick = () => loadFilesView(state.currentAccountId, item.id);

        elements.breadcrumbs.appendChild(el);

        if (index < pathItems.length - 1) {
            elements.breadcrumbs.appendChild(createSeparator());
        }
    });
}

function createSeparator() {
    const s = document.createElement('span');
    s.className = 'breadcrumb-separator';
    s.innerHTML = '<i class="ri-arrow-right-s-line"></i>';
    return s;
}

// Global actions for onclick handlers in HTML string
window.downloadFile = async (itemId) => {
    try {
        const url = await API.getDownloadUrl(state.currentAccountId, itemId);
        window.open(url, '_blank');
    } catch (e) {
        alert('Failed to get download URL: ' + e.message);
    }
};

window.deleteItem = async (itemId) => {
    if (!confirm('Are you sure you want to delete this item?')) return;
    try {
        await API.deleteItem(state.currentAccountId, itemId);
        // Refresh
        loadFilesView(state.currentAccountId, state.currentFolderId);
    } catch (e) {
        alert('Failed to delete: ' + e.message);
    }
};

async function triggerUpload() {
    const input = document.createElement('input');
    input.type = 'file';
    input.onchange = async () => {
        if (input.files.length > 0) {
            const file = input.files[0];
            try {
                // Show uploading state
                const btn = elements.uploadBtn;
                const originalText = btn.innerHTML;
                btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> Uploading...';
                btn.disabled = true;

                await API.uploadFile(state.currentAccountId, state.currentFolderId, file);

                // Refresh
                await loadFilesView(state.currentAccountId, state.currentFolderId);

                btn.innerHTML = originalText;
                btn.disabled = false;
            } catch (e) {
                alert('Upload failed: ' + e.message);
                elements.uploadBtn.innerHTML = '<i class="ri-upload-cloud-2-line"></i> Upload';
                elements.uploadBtn.disabled = false;
            }
        }
    };
    input.click();
}

async function triggerCreateFolder() {
    const name = prompt("Enter folder name:");
    if (!name) return;

    try {
        await API.createFolder(state.currentAccountId, state.currentFolderId, name);
        loadFilesView(state.currentAccountId, state.currentFolderId);
    } catch (e) {
        alert("Failed to create folder: " + e.message);
    }
}

// Start app
init();
