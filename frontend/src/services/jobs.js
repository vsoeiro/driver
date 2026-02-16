import api from './api';

/**
 * Create a job to move items.
 * @param {string} sourceAccountId 
 * @param {string} sourceItemId 
 * @param {string} destinationAccountId 
 * @param {string} destinationFolderId 
 */
export const createMoveJob = async (sourceAccountId, sourceItemId, destinationAccountId, destinationFolderId = 'root') => {
    const response = await api.post('/jobs/move', {
        source_account_id: sourceAccountId,
        source_item_id: sourceItemId,
        destination_account_id: destinationAccountId,
        destination_folder_id: destinationFolderId,
    });
    return response.data;
};

export const getJobs = async () => {
    const response = await api.get('/jobs/');
    return response.data;
};

export const deleteJob = async (jobId) => {
    await api.delete(`/jobs/${jobId}`);
};

export const cancelJob = async (jobId) => {
    const response = await api.post(`/jobs/${jobId}/cancel`);
    return response.data;
};

export const uploadFileBackground = async (accountId, folderId, file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('account_id', accountId);
    formData.append('folder_id', folderId);

    const response = await api.post('/jobs/upload', formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent) => {
            if (onProgress) {
                const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                onProgress(percentCompleted);
            }
        },
    });
    return response.data;
};

export const createMetadataUpdateJob = async (accountId, rootItemId, metadata, categoryName) => {
    const response = await api.post('/jobs/metadata-update', {
        account_id: accountId,
        root_item_id: rootItemId,
        metadata: metadata,
        category_name: categoryName,
    });
    return response.data;
};

export const applyMetadataRecursive = async (accountId, pathPrefix, categoryId, values = {}, includeFolders = false) => {
    const response = await api.post('/jobs/apply-metadata-recursive', {
        account_id: accountId,
        path_prefix: pathPrefix,
        category_id: categoryId,
        values,
        include_folders: includeFolders,
    });
    return response.data;
};

export const removeMetadataRecursive = async (accountId, pathPrefix) => {
    const response = await api.post('/jobs/remove-metadata-recursive', {
        account_id: accountId,
        path_prefix: pathPrefix,
    });
    return response.data;
};

export const createMetadataUndoJob = async (batchId) => {
    const response = await api.post('/jobs/metadata-undo', {
        batch_id: batchId,
    });
    return response.data;
};

export const createApplyRuleJob = async (ruleId) => {
    const response = await api.post('/jobs/apply-rule', {
        rule_id: ruleId,
    });
    return response.data;
};

export const createExtractComicAssetsJob = async (accountId, itemIds) => {
    const response = await api.post('/jobs/comics/extract', {
        account_id: accountId,
        item_ids: itemIds,
    });
    return response.data;
};

export const jobsService = {
    createMoveJob,
    getJobs,
    cancelJob,
    deleteJob,
    uploadFileBackground,
    createMetadataUpdateJob,
    applyMetadataRecursive,
    removeMetadataRecursive,
    createMetadataUndoJob,
    createApplyRuleJob,
    createExtractComicAssetsJob,
};

export default jobsService;
