const API_BASE = '/api/v1';

export const API = {
    // Accounts
    async getAccounts() {
        const response = await fetch(`${API_BASE}/accounts`);
        if (!response.ok) throw new Error('Failed to fetch accounts');
        return await response.json();
    },

    linkAccount() {
        // Redirects the user to the OAuth flow
        window.location.href = `${API_BASE}/auth/microsoft/login`;
    },

    // Drive / Files
    async getFiles(accountId, folderId = 'root') {
        const endpoint = folderId === 'root'
            ? `${API_BASE}/drive/${accountId}/files`
            : `${API_BASE}/drive/${accountId}/files/${folderId}`;

        const response = await fetch(endpoint);
        if (!response.ok) throw new Error('Failed to fetch files');
        return await response.json();
    },

    async getFileMetadata(accountId, itemId) {
        const response = await fetch(`${API_BASE}/drive/${accountId}/file/${itemId}`);
        if (!response.ok) throw new Error('Failed to fetch file metadata');
        return await response.json();
    },

    async getDownloadUrl(accountId, itemId) {
        const response = await fetch(`${API_BASE}/drive/${accountId}/download/${itemId}`);
        if (!response.ok) throw new Error('Failed to get download URL');
        const data = await response.json();
        return data.download_url;
    },

    async createFolder(accountId, parentId, name) {
        const response = await fetch(`${API_BASE}/drive/${accountId}/folders`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                parent_folder_id: parentId === 'root' ? undefined : parentId,
                conflict_behavior: 'rename'
            })
        });
        if (!response.ok) throw new Error('Failed to create folder');
        return await response.json();
    },

    async uploadFile(accountId, parentId, file) {
        const formData = new FormData();
        formData.append('file', file);
        const folderParam = parentId === 'root' ? 'root' : parentId;

        // Simple upload (for files < 4MB, logic for larger files can be added here or in app.js switching)
        const response = await fetch(`${API_BASE}/drive/${accountId}/upload?folder_id=${folderParam}`, {
            method: 'POST',
            body: formData
        });
        if (!response.ok) {
            const errorText = await response.text();
            try {
                const errJson = JSON.parse(errorText);
                throw new Error(errJson.detail || 'Upload failed');
            } catch (e) {
                if (e.message !== 'Upload failed') throw e;
                throw new Error('Upload failed: ' + errorText);
            }
        }
        return await response.json();
    },

    async deleteItem(accountId, itemId) {
        const response = await fetch(`${API_BASE}/drive/${accountId}/items/${itemId}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error('Failed to delete item');
    },

    async getPath(accountId, itemId) {
        const response = await fetch(`${API_BASE}/drive/${accountId}/path/${itemId}`);
        if (!response.ok) throw new Error('Failed to fetch path');
        return await response.json();
    }
};
