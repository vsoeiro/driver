import { renderHook } from '@testing-library/react';
import { act } from 'react';

import { useDebouncedValue } from './useDebouncedValue';

describe('useDebouncedValue', () => {
    it('keeps the previous value until the timeout finishes', () => {
        vi.useFakeTimers();
        const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 250), {
            initialProps: { value: 'first' },
        });

        rerender({ value: 'second' });
        expect(result.current).toBe('first');

        act(() => {
            vi.advanceTimersByTime(250);
        });

        expect(result.current).toBe('second');
        vi.useRealTimers();
    });
});
