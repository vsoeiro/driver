const STORAGE_KEY = 'driver_cover_url_cache_v1';
const DEFAULT_TTL_MS = 15 * 60 * 1000;
const MAX_CACHE_ENTRIES = 1000;

const memoryCache = new Map();
let initialized = false;

const now = () => Date.now();

const isBrowser = () => typeof window !== 'undefined' && typeof window.sessionStorage !== 'undefined';

const loadFromStorage = () => {
    if (initialized || !isBrowser()) return;
    initialized = true;
    try {
        const raw = window.sessionStorage.getItem(STORAGE_KEY);
        if (!raw) return;
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return;
        for (const entry of parsed) {
            if (!entry || typeof entry.key !== 'string') continue;
            if (typeof entry.url !== 'string') continue;
            if (typeof entry.expiresAt !== 'number') continue;
            if (entry.expiresAt > now()) {
                memoryCache.set(entry.key, { url: entry.url, expiresAt: entry.expiresAt });
            }
        }
    } catch (_) {
        // Ignore invalid cache payloads.
    }
};

const persistToStorage = () => {
    if (!isBrowser()) return;
    try {
        const entries = Array.from(memoryCache.entries())
            .slice(-MAX_CACHE_ENTRIES)
            .map(([key, value]) => ({ key, ...value }));
        window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    } catch (_) {
        // Ignore storage quota or serialization errors.
    }
};

const pruneExpired = () => {
    const ts = now();
    for (const [key, value] of memoryCache.entries()) {
        if (value.expiresAt <= ts) {
            memoryCache.delete(key);
        }
    }
};

export const buildCoverCacheKey = (accountId, coverItemId) => `${accountId}:${coverItemId}`;

export const getCachedCoverUrl = (key) => {
    loadFromStorage();
    pruneExpired();
    const hit = memoryCache.get(key);
    return hit ? hit.url : null;
};

export const setCachedCoverUrl = (key, url, ttlMs = DEFAULT_TTL_MS) => {
    loadFromStorage();
    pruneExpired();
    memoryCache.set(key, { url, expiresAt: now() + ttlMs });
    if (memoryCache.size > MAX_CACHE_ENTRIES) {
        const oldestKey = memoryCache.keys().next().value;
        if (oldestKey) memoryCache.delete(oldestKey);
    }
    persistToStorage();
};

