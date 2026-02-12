import axios from 'axios';

const api = axios.create({
    baseURL: '/api/v1', // Proxy handles this in dev
});

export const getAccounts = async () => {
    const response = await api.get('/accounts');
    return response.data.accounts;
};

export const linkAccount = () => {
    // Redirect to backend auth endpoint
    // Since we are decoupling, we need full URL or proxy
    // In dev, proxy handles specific paths. But this is a window location change.
    // If backend is on 8000, we should point there.
    // The current backend redirect URI is hardcoded probably.
    // But OAuth flow redirects back to callback.
    // We should probably redirect to backend auth URL directly.
    window.location.href = 'http://localhost:8000/api/v1/auth/microsoft/login';
};

export const getFiles = async (accountId, folderId = 'root') => {
    const endpoint = folderId === 'root'
        ? `/drive/${accountId}/files`
        : `/drive/${accountId}/files/${folderId}`;
    const response = await api.get(endpoint);
    return response.data;
};

export const getPath = async (accountId, itemId) => {
    const response = await api.get(`/drive/${accountId}/path/${itemId}`);
    return response.data;
};

export const createFolder = async (accountId, parentId, name) => {
    const response = await api.post(`/drive/${accountId}/folders`, {
        name,
        parent_folder_id: parentId === 'root' ? undefined : parentId,
        conflict_behavior: 'rename'
    });
    return response.data;
};

export const deleteItem = async (accountId, itemId) => {
    await api.delete(`/drive/${accountId}/items/${itemId}`);
};

export const getDownloadUrl = async (accountId, itemId) => {
    const response = await api.get(`/drive/${accountId}/download/${itemId}`);
    return response.data.download_url;
};

// Upload
export const uploadFileSimple = async (accountId, parentId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    const folderParam = parentId === 'root' ? 'root' : parentId;
    const response = await api.post(`/drive/${accountId}/upload?folder_id=${folderParam}`, formData);
    return response.data;
};

export const createUploadSession = async (accountId, parentId, filename, fileSize) => {
    const response = await api.post(`/drive/${accountId}/upload/session`, {
        filename,
        file_size: fileSize,
        folder_id: parentId === 'root' ? 'root' : parentId,
        conflict_behavior: 'rename'
    });
    return response.data;
};

export const uploadChunk = async (uploadUrl, chunk, start, end, totalSize) => {
    // Match the backend proxy logic: 
    // PUT /drive/{accountId}/upload/chunk?upload_url=...
    // But wait, the previous `uploadChunk` in api.js used `API_BASE` which was `/api/v1`.
    // The backend route is `@router.put("/{account_id}/upload/chunk")`.
    // So we need accountId here as well or handle it.
    // Let's pass accountId to this function too.
};

export const uploadChunkProxy = async (accountId, uploadUrl, chunk, start, end, totalSize) => {
    const formData = new FormData();
    formData.append('file', new Blob([chunk])); // Ensure binary

    const params = new URLSearchParams({
        upload_url: uploadUrl,
        start_byte: start.toString(),
        end_byte: end.toString(),
        total_size: totalSize.toString()
    });

    const response = await api.put(`/drive/${accountId}/upload/chunk?${params.toString()}`, formData);
    return response.data;
};

export const getQuota = async (accountId) => {
    const response = await api.get(`/drive/${accountId}/quota`);
    return response.data;
};
