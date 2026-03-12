vi.mock('./api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        delete: vi.fn(),
    },
}));

import api from './api';
import { aiService } from './ai';

describe('ai service', () => {
    it('handles chat session lifecycle', async () => {
        api.post.mockResolvedValue({ data: { id: 'session-1' } });
        api.get.mockResolvedValue({ data: { sessions: [] } });
        api.delete.mockResolvedValue({});

        await aiService.createChatSession('Driver');
        await aiService.listChatSessions(40, 2);
        await aiService.deleteChatSession('session-1');
        await aiService.generateSessionTitle('session-1');
        await aiService.listSessionMessages('session-1', 50);
        await aiService.postChatMessage('session-1', 'hello', { signal: 'signal' });
        await aiService.resolveConfirmation('session-1', 'confirm-1', true);
        await aiService.getToolsCatalog();

        expect(api.post).toHaveBeenCalledWith('/ai/chat/sessions', { title: 'Driver' });
        expect(api.get).toHaveBeenCalledWith('/ai/chat/sessions', { params: { limit: 40, offset: 2 } });
        expect(api.delete).toHaveBeenCalledWith('/ai/chat/sessions/session-1');
        expect(api.post).toHaveBeenCalledWith('/ai/chat/sessions/session-1/messages', { message: 'hello' }, { signal: 'signal' });
        expect(api.post).toHaveBeenCalledWith('/ai/chat/sessions/session-1/confirmations/confirm-1', { approve: true });
        expect(api.get).toHaveBeenCalledWith('/ai/tools/catalog');
    });
});
