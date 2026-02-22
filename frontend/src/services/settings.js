import api from './api';

export const getRuntimeSettings = async () => {
    const response = await api.get('/admin/settings');
    return response.data;
};

export const updateRuntimeSettings = async (payload) => {
    const response = await api.put('/admin/settings', payload);
    return response.data;
};

export const getObservabilitySnapshot = async ({ period = '24h', forceRefresh = false } = {}) => {
    const response = await api.get('/admin/observability', {
        params: {
            period,
            force_refresh: Boolean(forceRefresh),
        },
    });
    return response.data;
};

export const settingsService = {
    getRuntimeSettings,
    updateRuntimeSettings,
    getObservabilitySnapshot,
};

export default settingsService;
