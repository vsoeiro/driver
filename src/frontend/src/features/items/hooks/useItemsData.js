import { useCallback, useMemo } from 'react';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';

import { normalizeItemsListParams, normalizeSimilarReportParams, queryKeys } from '../../../lib/queryKeys';
import { itemsService } from '../../../services/items';

export function useItemsListQuery(params = {}, options = {}) {
    const normalizedParams = normalizeItemsListParams(params);

    return useQuery({
        queryKey: queryKeys.items.list(normalizedParams),
        queryFn: ({ signal }) => itemsService.listItems(normalizedParams, { signal }),
        placeholderData: keepPreviousData,
        ...options,
    });
}

export function useSimilarFilesReportQuery(params = {}, options = {}) {
    const normalizedParams = normalizeSimilarReportParams(params);

    return useQuery({
        queryKey: queryKeys.items.similarReport(normalizedParams),
        queryFn: ({ signal }) => itemsService.getSimilarReport(normalizedParams, { signal }),
        ...options,
    });
}

export function useItemsActions() {
    const listItems = useCallback((params, options = {}) => itemsService.listItems(params, options), []);
    const getSimilarReport = useCallback((params = {}, options = {}) => itemsService.getSimilarReport(params, options), []);
    const batchUpdateMetadata = useCallback(
        (accountId, itemIds, categoryId, values) => itemsService.batchUpdateMetadata(accountId, itemIds, categoryId, values),
        [],
    );

    return useMemo(() => ({
        listItems,
        getSimilarReport,
        batchUpdateMetadata,
    }), [batchUpdateMetadata, getSimilarReport, listItems]);
}

export function useItemsCacheActions() {
    const queryClient = useQueryClient();

    const invalidateItemsList = useCallback(
        () => queryClient.invalidateQueries({ queryKey: queryKeys.items.listRoot() }),
        [queryClient],
    );

    return useMemo(() => ({
        invalidateItemsList,
    }), [invalidateItemsList]);
}

export default useItemsListQuery;
