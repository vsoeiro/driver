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

export const updateAttribute = async (attributeId, attribute) => {
    const response = await api.patch(`/metadata/attributes/${attributeId}`, attribute);
    return response.data;
};

export const getItemMetadata = async (accountId, itemId) => {
    const response = await api.get(`/metadata/items/${accountId}/${itemId}`);
    return response.data;
};

export const saveItemMetadata = async (metadata) => {
    const response = await api.post('/metadata/items', metadata);
    return response.data;
};

export const updateItemMetadataField = async (accountId, itemId, attributeId, payload) => {
    const response = await api.patch(`/metadata/items/${accountId}/${itemId}/attributes/${attributeId}`, payload);
    return response.data;
};

export const deleteItemMetadata = async (accountId, itemId) => {
    await api.delete(`/metadata/items/${accountId}/${itemId}`);
};

export const updateItemAISuggestions = async (accountId, itemId, payload) => {
    const response = await api.patch(`/metadata/items/${accountId}/${itemId}/ai-suggestions`, payload);
    return response.data;
};

export const acceptItemAISuggestion = async (accountId, itemId, payload) => {
    const response = await api.post(`/metadata/items/${accountId}/${itemId}/ai-suggestions/accept`, payload);
    return response.data;
};

export const rejectItemAISuggestion = async (accountId, itemId, payload) => {
    const response = await api.post(`/metadata/items/${accountId}/${itemId}/ai-suggestions/reject`, payload);
    return response.data;
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

export const listFormLayouts = async () => {
    const response = await api.get('/metadata/layouts');
    return response.data;
};

export const getFormLayout = async (categoryId) => {
    const response = await api.get(`/metadata/layouts/${categoryId}`);
    return response.data;
};

export const saveFormLayout = async (categoryId, payload) => {
    const response = await api.put(`/metadata/layouts/${categoryId}`, payload);
    return response.data;
};

export const getSeriesSummary = async (categoryId, params = {}) => {
    const queryParams = new URLSearchParams();

    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            if (Array.isArray(value)) {
                value.forEach((v) => queryParams.append(key, v));
            } else if (typeof value === 'object') {
                queryParams.append(key, JSON.stringify(value));
            } else {
                queryParams.append(key, value);
            }
        }
    });

    const response = await api.get(`/metadata/categories/${categoryId}/series-summary?${queryParams.toString()}`);
    return response.data;
};

export const listPlugins = async () => {
    const response = await api.get('/metadata/plugins');
    return response.data;
};

export const activatePlugin = async (pluginKey) => {
    const response = await api.post(`/metadata/plugins/${pluginKey}/activate`);
    return response.data;
};

export const deactivatePlugin = async (pluginKey) => {
    const response = await api.post(`/metadata/plugins/${pluginKey}/deactivate`);
    return response.data;
};

export const metadataService = {
    getCategories,
    listCategories: getCategories,
    getCategoryStats,
    listFormLayouts,
    getFormLayout,
    saveFormLayout,
    getSeriesSummary,
    listPlugins,
    activatePlugin,
    deactivatePlugin,
    createCategory,
    deleteCategory,
    createAttribute,
    updateAttribute,
    deleteAttribute,
    getItemMetadata,
    saveItemMetadata,
    updateItemMetadataField,
    updateItemAISuggestions,
    acceptItemAISuggestion,
    rejectItemAISuggestion,
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
