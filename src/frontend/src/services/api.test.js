import api from './api';

describe('api service', () => {
    it('uses the expected base config and response interceptor', async () => {
        expect(api.defaults.baseURL).toBe('/api/v1');
        expect(api.defaults.headers['Content-Type'] || api.defaults.headers.common?.['Content-Type']).toBeTruthy();

        const rejected = api.interceptors.response.handlers[0].rejected;
        await expect(rejected(new Error('boom'))).rejects.toThrow('boom');
    });
});
