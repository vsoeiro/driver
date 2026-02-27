import api from './api';

export const createChatSession = async (title = null) => {
    const response = await api.post('/ai/chat/sessions', { title });
    return response.data;
};

export const listChatSessions = async (limit = 30, offset = 0) => {
    const response = await api.get('/ai/chat/sessions', { params: { limit, offset } });
    return response.data;
};

export const deleteChatSession = async (sessionId) => {
    await api.delete(`/ai/chat/sessions/${sessionId}`);
};

export const generateSessionTitle = async (sessionId) => {
    const response = await api.post(`/ai/chat/sessions/${sessionId}/title`);
    return response.data;
};

export const listSessionMessages = async (sessionId, limit = 200) => {
    const response = await api.get(`/ai/chat/sessions/${sessionId}/messages`, { params: { limit } });
    return response.data;
};

export const postChatMessage = async (sessionId, message, options = {}) => {
    const response = await api.post(
        `/ai/chat/sessions/${sessionId}/messages`,
        { message },
        { signal: options.signal }
    );
    return response.data;
};

export const resolveConfirmation = async (sessionId, confirmationId, approve) => {
    const response = await api.post(
        `/ai/chat/sessions/${sessionId}/confirmations/${confirmationId}`,
        { approve }
    );
    return response.data;
};

export const getToolsCatalog = async () => {
    const response = await api.get('/ai/tools/catalog');
    return response.data;
};

export const aiService = {
    createChatSession,
    listChatSessions,
    deleteChatSession,
    generateSessionTitle,
    listSessionMessages,
    postChatMessage,
    resolveConfirmation,
    getToolsCatalog,
};

export default aiService;
