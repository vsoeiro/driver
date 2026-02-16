import api from './api';

export const getRuntimeSettings = async () => {
    const response = await api.get('/admin/settings');
    return response.data;
};

export const updateRuntimeSettings = async (payload) => {
    const response = await api.put('/admin/settings', payload);
    return response.data;
};

export const settingsService = {
    getRuntimeSettings,
    updateRuntimeSettings,
};

export default settingsService;

