vi.mock('./api', () => ({
    default: {
        get: vi.fn(),
        put: vi.fn(),
    },
}));

import api from './api';
import { settingsService } from './settings';

describe('settings service', () => {
    it('gets and updates runtime settings', async () => {
        api.get.mockResolvedValue({ data: { ai_enabled: true } });
        api.put.mockResolvedValue({ data: { updated: true } });

        await expect(settingsService.getRuntimeSettings()).resolves.toEqual({ ai_enabled: true });
        await expect(settingsService.updateRuntimeSettings({ ai_enabled: false })).resolves.toEqual({ updated: true });

        expect(api.get).toHaveBeenCalledWith('/admin/settings');
        expect(api.put).toHaveBeenCalledWith('/admin/settings', { ai_enabled: false });
    });

    it('passes observability params', async () => {
        api.get.mockResolvedValue({ data: { period: '7d' } });

        await settingsService.getObservabilitySnapshot({ period: '7d', forceRefresh: true, signal: 'signal' });

        expect(api.get).toHaveBeenCalledWith('/admin/observability', {
            params: { period: '7d', force_refresh: true },
            signal: 'signal',
        });
    });
});
