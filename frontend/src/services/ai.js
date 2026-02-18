import api from './api';

export const aiService = {
    async health() {
        const response = await api.get('/ai/health');
        return response.data;
    },

    async suggestCategorySchema(payload) {
        const response = await api.post('/ai/suggest-category-schema', payload);
        return response.data;
    },

    async extractMetadata(payload) {
        const response = await api.post('/ai/extract-metadata', payload);
        return response.data;
    },

    async suggestComicMetadata(payload) {
        const response = await api.post('/ai/suggest-comic-metadata', payload);
        return response.data;
    },
};

export default aiService;
