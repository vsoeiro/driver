import api from './api';

export const getCategories = async () => {
    const response = await api.get('/metadata/categories');
    return response.data;
};

export const createCategory = async (name, description) => {
    const response = await api.post('/metadata/categories', { name, description });
    return response.data;
};

export const deleteCategory = async (categoryId) => {
    await api.delete(`/metadata/categories/${categoryId}`);
};

export const createAttribute = async (categoryId, attribute) => {
    const response = await api.post(`/metadata/categories/${categoryId}/attributes`, attribute);
    return response.data;
};

export const deleteAttribute = async (attributeId) => {
    await api.delete(`/metadata/attributes/${attributeId}`);
};

export const getItemMetadata = async (accountId, itemId) => {
    const response = await api.get(`/metadata/items/${accountId}/${itemId}`);
    return response.data;
};

export const saveItemMetadata = async (metadata) => {
    const response = await api.post('/metadata/items', metadata);
    return response.data;
};

export const deleteItemMetadata = async (accountId, itemId) => {
    await api.delete(`/metadata/items/${accountId}/${itemId}`);
};

export const batchDeleteMetadata = async (accountId, itemIds) => {
    // Backend expects item_ids as a list in the body
    await api.post('/metadata/items/batch-delete', itemIds, {
        params: { account_id: accountId }
    });
};

export const getItemMetadataHistory = async (accountId, itemId) => {
    const response = await api.get(`/metadata/items/${accountId}/${itemId}/history`);
    return response.data;
};

export const undoMetadataBatch = async (batchId) => {
    const response = await api.post(`/metadata/batches/${batchId}/undo`);
    return response.data;
};

export const listRules = async () => {
    const response = await api.get('/metadata/rules');
    return response.data;
};

export const createRule = async (rule) => {
    const response = await api.post('/metadata/rules', rule);
    return response.data;
};

export const updateRule = async (ruleId, rule) => {
    const response = await api.patch(`/metadata/rules/${ruleId}`, rule);
    return response.data;
};

export const deleteRule = async (ruleId) => {
    await api.delete(`/metadata/rules/${ruleId}`);
};

export const previewRule = async (payload) => {
    const response = await api.post('/metadata/rules/preview', payload);
    return response.data;
};

export const getCategoryStats = async () => {
    const response = await api.get('/metadata/categories/stats');
    return response.data;
};

export const metadataService = {
    getCategories,
    listCategories: getCategories,
    getCategoryStats,
    createCategory,
    deleteCategory,
    createAttribute,
    deleteAttribute,
    getItemMetadata,
    saveItemMetadata,
    deleteItemMetadata,
    batchDeleteMetadata,
    getItemMetadataHistory,
    undoMetadataBatch,
    listRules,
    createRule,
    updateRule,
    deleteRule,
    previewRule,
};

export default metadataService;
