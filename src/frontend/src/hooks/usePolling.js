import { useEffect, useRef } from 'react';

export function usePolling({
    callback,
    intervalMs,
    enabled = true,
    pauseWhenHidden = true,
    runImmediately = true,
}) {
    const savedCallback = useRef(callback);

    useEffect(() => {
        savedCallback.current = callback;
    }, [callback]);

    useEffect(() => {
        if (!enabled || !Number.isFinite(intervalMs) || intervalMs <= 0) {
            return undefined;
        }

        let cancelled = false;

        const tick = async () => {
            if (cancelled) return;
            if (pauseWhenHidden && typeof document !== 'undefined' && document.visibilityState === 'hidden') {
                return;
            }
            await savedCallback.current?.();
        };

        if (runImmediately) {
            tick();
        }

        const timer = setInterval(tick, intervalMs);
        return () => {
            cancelled = true;
            clearInterval(timer);
        };
    }, [enabled, intervalMs, pauseWhenHidden, runImmediately]);
}

export default usePolling;
