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

export const createExtractZipJob = async (
    sourceAccountId,
    sourceItemId,
    destinationAccountId,
    destinationFolderId = 'root',
    deleteSourceAfterExtract = false,
) => {
    const response = await api.post('/jobs/zip/extract', {
        source_account_id: sourceAccountId,
        source_item_id: sourceItemId,
        destination_account_id: destinationAccountId,
        destination_folder_id: destinationFolderId,
        delete_source_after_extract: deleteSourceAfterExtract,
    });
    return response.data;
};

export const getJobs = async (limit = 50, offset = 0, statuses = [], filters = {}, options = {}) => {
    const safeLimit = Number.isFinite(Number(limit)) ? Math.max(1, Math.floor(Number(limit))) : 50;
    const safeOffset = Number.isFinite(Number(offset)) ? Math.max(0, Math.floor(Number(offset))) : 0;
    const normalizedStatuses = Array.isArray(statuses)
        ? statuses.map((status) => String(status || '').trim().toUpperCase()).filter(Boolean)
        : [];
    const normalizedTypes = Array.isArray(filters?.types)
        ? filters.types.map((type) => String(type || '').trim().toLowerCase()).filter(Boolean)
        : [];
    const createdAfter = typeof filters?.createdAfter === 'string' ? filters.createdAfter.trim() : '';
    const includeEstimates = typeof options?.includeEstimates === 'boolean' ? options.includeEstimates : true;
    const params = { limit: safeLimit, offset: safeOffset };
    params.include_estimates = includeEstimates;
    if (normalizedStatuses.length === 1) {
        params.status = normalizedStatuses[0];
    } else if (normalizedStatuses.length > 1) {
        params.status = normalizedStatuses.join(',');
    }
    if (normalizedTypes.length === 1) {
        params.type = normalizedTypes[0];
    } else if (normalizedTypes.length > 1) {
        params.type = normalizedTypes.join(',');
    }
    if (createdAfter) {
        params.created_after = createdAfter;
    }
    const response = await api.get('/jobs/', {
        params,
        signal: options.signal,
    });
    return response.data;
};

export const deleteJob = async (jobId) => {
    await api.delete(`/jobs/${jobId}`);
};

export const cancelJob = async (jobId) => {
    const response = await api.post(`/jobs/${jobId}/cancel`);
    return response.data;
};

export const reprocessJob = async (jobId) => {
    const response = await api.post(`/jobs/${jobId}/reprocess`);
    return response.data;
};

export const getJobAttempts = async (jobId, limit = 20) => {
    const safeLimit = Number.isFinite(Number(limit)) ? Math.max(1, Math.floor(Number(limit))) : 20;
    const response = await api.get(`/jobs/${jobId}/attempts`, {
        params: { limit: safeLimit },
    });
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

export const createSyncJob = async (accountId) => {
    const response = await api.post('/jobs/sync', {
        account_id: accountId,
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

export const createExtractBookAssetsJob = async (accountId, itemIds) => {
    const response = await api.post('/jobs/books/extract', {
        account_id: accountId,
        item_ids: itemIds,
    });
    return response.data;
};

export const createAnalyzeImageAssetsJob = async (accountId, itemIds, useIndexedItems = true, reprocess = false) => {
    const response = await api.post('/jobs/images/analyze', {
        account_id: accountId,
        item_ids: itemIds,
        use_indexed_items: useIndexedItems,
        reprocess: reprocess,
    });
    return response.data;
};

export const createAnalyzeLibraryImageAssetsJob = async (accountIds = null, chunkSize = 500, reprocess = false) => {
    const payload = { chunk_size: chunkSize, reprocess: reprocess };
    if (Array.isArray(accountIds) && accountIds.length > 0) {
        payload.account_ids = accountIds;
    }
    const response = await api.post('/jobs/images/analyze-library', payload);
    return response.data;
};

export const createReindexComicCoversJob = async (libraryKey = 'comics_core') => {
    const response = await api.post('/jobs/comics/reindex-covers', {
        library_key: libraryKey,
    });
    return response.data;
};

export const createExtractLibraryComicAssetsJob = async (accountIds = null, chunkSize = 1000) => {
    const payload = {};
    if (Array.isArray(accountIds) && accountIds.length > 0) {
        payload.account_ids = accountIds;
    }
    payload.chunk_size = chunkSize;
    const response = await api.post('/jobs/comics/extract-library', payload);
    return response.data;
};

export const createMapLibraryBooksJob = async (accountIds = null, chunkSize = 500) => {
    const payload = { chunk_size: chunkSize };
    if (Array.isArray(accountIds) && accountIds.length > 0) {
        payload.account_ids = accountIds;
    }
    const response = await api.post('/jobs/books/extract-library', payload);
    return response.data;
};

export const createExtractLibraryBookAssetsJob = async (accountIds = null, chunkSize = 500) => {
    const payload = { chunk_size: chunkSize };
    if (Array.isArray(accountIds) && accountIds.length > 0) {
        payload.account_ids = accountIds;
    }
    const response = await api.post('/jobs/books/extract-library', payload);
    return response.data;
};

export const createRemoveDuplicatesJob = async (payload) => {
    const response = await api.post('/jobs/remove-duplicates', payload);
    return response.data;
};

export const jobsService = {
    createMoveJob,
    createExtractZipJob,
    getJobs,
    cancelJob,
    reprocessJob,
    getJobAttempts,
    deleteJob,
    uploadFileBackground,
    createSyncJob,
    createMetadataUpdateJob,
    applyMetadataRecursive,
    removeMetadataRecursive,
    createMetadataUndoJob,
    createApplyRuleJob,
    createExtractComicAssetsJob,
    createExtractBookAssetsJob,
    createAnalyzeImageAssetsJob,
    createAnalyzeLibraryImageAssetsJob,
    createExtractLibraryComicAssetsJob,
    createMapLibraryBooksJob,
    createExtractLibraryBookAssetsJob,
    createReindexComicCoversJob,
    createRemoveDuplicatesJob,
};

export default jobsService;
