import { useCallback, useMemo } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { normalizeDriveListParams, queryKeys } from '../../../lib/queryKeys';
import { driveService } from '../../../services/drive';

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

export function useDriveActions() {
    const getFiles = useCallback((accountId, options = {}) => driveService.getFiles(accountId, options), []);
    const getFolderFiles = useCallback((accountId, folderId, options = {}) => driveService.getFolderFiles(accountId, folderId, options), []);
    const getPath = useCallback((accountId, itemId, options = {}) => driveService.getPath(accountId, itemId, options), []);
    const createFolder = useCallback((accountId, parentId, name) => driveService.createFolder(accountId, parentId, name), []);
    const deleteItem = useCallback((accountId, itemId) => driveService.deleteItem(accountId, itemId), []);
    const batchDeleteItems = useCallback((accountId, itemIds) => driveService.batchDeleteItems(accountId, itemIds), []);
    const uploadFileSimple = useCallback((accountId, parentId, file) => driveService.uploadFileSimple(accountId, parentId, file), []);
    const createUploadSession = useCallback((accountId, parentId, filename, fileSize) => driveService.createUploadSession(accountId, parentId, filename, fileSize), []);
    const uploadChunkProxy = useCallback(
        (accountId, uploadUrl, chunk, start, end, totalSize) => driveService.uploadChunkProxy(accountId, uploadUrl, chunk, start, end, totalSize),
        [],
    );
    const getDownloadUrl = useCallback((accountId, itemId, options = {}) => driveService.getDownloadUrl(accountId, itemId, options), []);
    const getDownloadContentUrl = useCallback((accountId, itemId, options = {}) => driveService.getDownloadContentUrl(accountId, itemId, options), []);
    const createComicReaderSession = useCallback((accountId, itemId) => driveService.createComicReaderSession(accountId, itemId), []);
    const getComicReaderPageUrl = useCallback((accountId, sessionId, pageIndex) => driveService.getComicReaderPageUrl(accountId, sessionId, pageIndex), []);
    const getQuota = useCallback((accountId, options = {}) => driveService.getQuota(accountId, options), []);
    const searchFiles = useCallback((accountId, query, options = {}) => driveService.searchFiles(accountId, query, options), []);
    const updateItem = useCallback((accountId, itemId, payload) => driveService.updateItem(accountId, itemId, payload), []);
    const listFolderEntries = useCallback(
        (accountId, folderId = 'root', options = {}) => (folderId === 'root'
            ? driveService.getFiles(accountId, options)
            : driveService.getFolderFiles(accountId, folderId, options)),
        [],
    );

    return useMemo(() => ({
        getFiles,
        getFolderFiles,
        getPath,
        createFolder,
        deleteItem,
        batchDeleteItems,
        uploadFileSimple,
        createUploadSession,
        uploadChunkProxy,
        getDownloadUrl,
        getDownloadContentUrl,
        createComicReaderSession,
        getComicReaderPageUrl,
        getQuota,
        searchFiles,
        updateItem,
        listFolderEntries,
    }), [
        batchDeleteItems,
        createFolder,
        createUploadSession,
        deleteItem,
        getDownloadContentUrl,
        getDownloadUrl,
        createComicReaderSession,
        getComicReaderPageUrl,
        getFiles,
        getFolderFiles,
        getPath,
        getQuota,
        listFolderEntries,
        searchFiles,
        updateItem,
        uploadChunkProxy,
        uploadFileSimple,
    ]);
}

export default useDriveListingQuery;
