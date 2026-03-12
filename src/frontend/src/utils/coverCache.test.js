import { buildCoverCacheKey, getCachedCoverUrl, setCachedCoverUrl } from './coverCache';

describe('coverCache utils', () => {
    beforeEach(() => {
        window.sessionStorage.clear();
    });

    it('builds cache keys and stores cached urls', () => {
        const key = buildCoverCacheKey('acc-1', 'cover-1');
        setCachedCoverUrl(key, 'https://example.test/cover.jpg', 1000);

        expect(key).toBe('acc-1:cover-1');
        expect(getCachedCoverUrl(key)).toBe('https://example.test/cover.jpg');
    });

    it('expires cached values', async () => {
        vi.useFakeTimers();
        const key = buildCoverCacheKey('acc-2', 'cover-2');
        setCachedCoverUrl(key, 'https://example.test/expired.jpg', 10);

        vi.advanceTimersByTime(11);

        expect(getCachedCoverUrl(key)).toBeNull();
        vi.useRealTimers();
    });
});
