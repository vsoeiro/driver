import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { accountsService } from '../services/accounts';
import { metadataService } from '../services/metadata';
import { settingsService } from '../services/settings';
import { driveService } from '../services/drive';
import { itemsService } from '../services/items';
import { normalizeDriveListParams, normalizeItemsListParams, queryKeys } from '../lib/queryKeys';

export function useAccountsQuery(options = {}) {
    return useQuery({
        queryKey: queryKeys.accounts.all(),
        queryFn: ({ signal }) => accountsService.getAccounts({ signal }),
        staleTime: 60000,
        ...options,
    });
}

export function useMetadataCategoriesQuery(options = {}) {
    return useQuery({
        queryKey: queryKeys.metadata.categories(),
        queryFn: ({ signal }) => metadataService.listCategories({ signal }),
        staleTime: 30000,
        ...options,
    });
}

export function useMetadataLibrariesQuery(options = {}) {
    return useQuery({
        queryKey: queryKeys.metadata.libraries(),
        queryFn: ({ signal }) => metadataService.listMetadataLibraries({ signal }),
        staleTime: 30000,
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

export function useQuotaQuery(accountId, options = {}) {
    return useQuery({
        queryKey: queryKeys.quota.detail(accountId),
        queryFn: ({ signal }) => driveService.getQuota(accountId, { signal }),
        enabled: Boolean(accountId),
        staleTime: 45000,
        ...options,
    });
}

export function useDriveListingQuery(params = {}, options = {}) {
    const normalizedParams = normalizeDriveListParams(params);
    const { accountId, folderId, searchQuery, cursor, pageSize } = normalizedParams;

    return useQuery({
        queryKey: queryKeys.drive.list(normalizedParams),
        queryFn: ({ signal }) => {
            if (searchQuery) {
                return driveService.searchFiles(accountId, searchQuery, { signal });
            }
            if (folderId) {
                return driveService.getFolderFiles(accountId, folderId, {
                    nextLink: cursor,
                    pageSize,
                    signal,
                });
            }
            return driveService.getFiles(accountId, {
                nextLink: cursor,
                pageSize,
                signal,
            });
        },
        enabled: Boolean(accountId) && (options.enabled ?? true),
        placeholderData: keepPreviousData,
        ...options,
    });
}

export function useDriveBreadcrumbQuery(accountId, folderId, options = {}) {
    return useQuery({
        queryKey: queryKeys.drive.breadcrumb(accountId, folderId),
        queryFn: ({ signal }) => driveService.getPath(accountId, folderId, { signal }),
        enabled: Boolean(accountId && folderId) && (options.enabled ?? true),
        staleTime: 5 * 60 * 1000,
        ...options,
    });
}

export function useItemsListQuery(params = {}, options = {}) {
    const normalizedParams = normalizeItemsListParams(params);

    return useQuery({
        queryKey: queryKeys.items.list(normalizedParams),
        queryFn: ({ signal }) => itemsService.listItems(normalizedParams, { signal }),
        placeholderData: keepPreviousData,
        ...options,
    });
}
