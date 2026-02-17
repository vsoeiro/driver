import api from './api';

/**
 * Get files in root or specific folder
 */
export const getFiles = async (accountId) => {
    const response = await api.get(`/drive/${accountId}/files`);
    return response.data;
};

export const getFolderFiles = async (accountId, folderId) => {
    const response = await api.get(`/drive/${accountId}/files/${folderId}`);
    return response.data;
};

/**
 * Get breadcrumb path
 */
export const getPath = async (accountId, itemId) => {
    const response = await api.get(`/drive/${accountId}/path/${itemId}`);
    return response.data;
};

/**
 * Create a new folder
 */
export const createFolder = async (accountId, parentId, name) => {
    const response = await api.post(`/drive/${accountId}/folders`, {
        name,
        parent_folder_id: parentId === 'root' ? undefined : parentId,
        conflict_behavior: 'rename'
    });
    return response.data;
};

/**
 * Delete an item
 */
export const deleteItem = async (accountId, itemId) => {
    await api.delete(`/drive/${accountId}/items/${itemId}`);
};

/**
 * Upload a small file (< 4MB)
 */
export const uploadFileSimple = async (accountId, parentId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    const folderParam = parentId === 'root' ? 'root' : parentId;
    const response = await api.post(`/drive/${accountId}/upload?folder_id=${folderParam}`, formData);
    return response.data;
};

/**
 * Create upload session for large files
 */
export const createUploadSession = async (accountId, parentId, filename, fileSize) => {
    const response = await api.post(`/drive/${accountId}/upload/session`, {
        filename,
        file_size: fileSize,
        folder_id: parentId === 'root' ? 'root' : parentId,
        conflict_behavior: 'rename'
    });
    return response.data;
};

/**
 * Upload a chunk
 */
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

/**
 * Get download URL for a file
 */
export const getDownloadUrl = async (accountId, itemId, options = {}) => {
    const params = new URLSearchParams();
    if (options.autoResolveAccount) {
        params.set('auto_resolve_account', 'true');
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    const response = await api.get(`/drive/${accountId}/download/${itemId}${query}`);
    return response.data.download_url;
};

/**
 * Build backend proxied content URL for browser-safe image/file embedding.
 */
export const getDownloadContentUrl = (accountId, itemId, options = {}) => {
    const params = new URLSearchParams();
    if (options.autoResolveAccount) {
        params.set('auto_resolve_account', 'true');
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return `/api/v1/drive/${encodeURIComponent(accountId)}/download/${encodeURIComponent(itemId)}/content${query}`;
};

/**
 * Get storage quota
 */
export const getQuota = async (accountId) => {
    const response = await api.get(`/drive/${accountId}/quota`);
    return response.data;
};

/**
 * Search for files
 */
export const searchFiles = async (accountId, query) => {
    const response = await api.get(`/drive/${accountId}/search?q=${encodeURIComponent(query)}`);
    return response.data;
};

/**
 * Delete multiple items
 */
export const batchDeleteItems = async (accountId, itemIds) => {
    await api.post(`/drive/${accountId}/items/batch-delete`, { item_ids: itemIds });
};

export const driveService = {
    getFiles,
    getFolderFiles,
    getPath,
    createFolder,
    deleteItem,
    batchDeleteItems,
    uploadFileSimple,
    createUploadSession,
    uploadChunkProxy,
    getDownloadUrl,
    getDownloadContentUrl,
    getQuota,
    searchFiles
};

export default driveService;
