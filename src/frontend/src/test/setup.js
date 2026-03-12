import '@testing-library/jest-dom/vitest';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';

import { server } from './server';

beforeAll(() => {
    window.localStorage.setItem('driver-language', 'en');
    server.listen({ onUnhandledRequest: 'error' });
    window.HTMLElement.prototype.scrollIntoView = window.HTMLElement.prototype.scrollIntoView || vi.fn();
    window.matchMedia = window.matchMedia || function matchMedia() {
        return {
            matches: false,
            addEventListener: () => {},
            removeEventListener: () => {},
            addListener: () => {},
            removeListener: () => {},
            dispatchEvent: () => false,
        };
    };
    window.scrollTo = window.scrollTo || (() => {});
    window.URL.createObjectURL = window.URL.createObjectURL || vi.fn(() => 'blob:mock-url');
    window.URL.revokeObjectURL = window.URL.revokeObjectURL || vi.fn();
});

afterEach(() => {
    server.resetHandlers();
    vi.clearAllMocks();
});

afterAll(() => {
    server.close();
});
