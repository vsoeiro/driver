import { useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { queryKeys } from '../../../lib/queryKeys';
import { settingsService } from '../../../services/settings';

export function useRuntimeSettingsQuery(options = {}) {
    return useQuery({
        queryKey: queryKeys.settings.runtime(),
        queryFn: () => settingsService.getRuntimeSettings(),
        ...options,
    });
}

export function useObservabilityQuery({ period = '24h', forceRefresh = false, ...options } = {}) {
    return useQuery({
        queryKey: queryKeys.observability.detail(period),
        queryFn: ({ signal }) => settingsService.getObservabilitySnapshot({ period, forceRefresh, signal }),
        staleTime: 15000,
        ...options,
    });
}

export function useObservabilitySnapshot({ period = '24h', forceRefresh = false, ...options } = {}) {
    const queryClient = useQueryClient();
    const query = useObservabilityQuery({ period, forceRefresh, ...options });

    const refreshSnapshot = useCallback(async ({ forceRefresh: nextForceRefresh = false } = {}) => {
        const data = await settingsService.getObservabilitySnapshot({
            period,
            forceRefresh: nextForceRefresh,
        });
        queryClient.setQueryData(queryKeys.observability.detail(period), data);
        return data;
    }, [period, queryClient]);

    return useMemo(() => ({
        ...query,
        refreshSnapshot,
    }), [query, refreshSnapshot]);
}

export function useSettingsActions() {
    const queryClient = useQueryClient();

    const getRuntimeSettings = useCallback(() => settingsService.getRuntimeSettings(), []);
    const updateRuntimeSettings = useCallback(async (payload) => {
        const data = await settingsService.updateRuntimeSettings(payload);
        queryClient.setQueryData(queryKeys.settings.runtime(), data);
        return data;
    }, [queryClient]);
    const getObservabilitySnapshot = useCallback((options = {}) => settingsService.getObservabilitySnapshot(options), []);

    return useMemo(() => ({
        getRuntimeSettings,
        updateRuntimeSettings,
        getObservabilitySnapshot,
    }), [getObservabilitySnapshot, getRuntimeSettings, updateRuntimeSettings]);
}

export default useObservabilityQuery;
