import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { useDriveActions, useDriveBreadcrumbQuery, useDriveListingQuery } from '../features/drive/hooks/useDriveData';

export function useDrive(accountId, folderId, options = {}) {
    const queryClient = useQueryClient();
    const { batchDeleteItems, createFolder, deleteItem } = useDriveActions();
    const [searchQuery, setSearchQuery] = useState('');
    const [currentCursor, setCurrentCursor] = useState(null);
    const [cursorHistory, setCursorHistory] = useState([]);
    const pageSize = Number.isFinite(Number(options.pageSize)) ? Math.max(1, Math.floor(Number(options.pageSize))) : 50;

    // Reset search on navigation
    useEffect(() => {
        setSearchQuery('');
        setCurrentCursor(null);
        setCursorHistory([]);
    }, [folderId, accountId, pageSize]);

    const listQueryParams = useMemo(
        () => ({
            accountId,
            folderId,
            searchQuery,
            cursor: currentCursor,
            pageSize,
        }),
        [accountId, currentCursor, folderId, pageSize, searchQuery],
    );

    const filesQuery = useDriveListingQuery(listQueryParams, {
        staleTime: 30000,
    });

    const breadcrumbQuery = useDriveBreadcrumbQuery(accountId, folderId, {
        enabled: Boolean(accountId && folderId && !searchQuery),
    });

    const files = filesQuery.data?.items || [];
    const nextCursor = searchQuery ? null : filesQuery.data?.next_link || null;
    const loading = filesQuery.isPending && !filesQuery.data;
    const error = filesQuery.error?.message || null;
    const breadcrumbs = useMemo(() => {
        if (searchQuery) {
            return [{ id: 'search', name: `Search results: ${searchQuery}` }];
        }
        if (!folderId) {
            return [];
        }
        return (breadcrumbQuery.data?.breadcrumb || []).filter((item) => item.name.toLowerCase() !== 'root');
    }, [breadcrumbQuery.data?.breadcrumb, folderId, searchQuery]);

    const refresh = useCallback(async () => {
        if (!accountId) return;
        await Promise.all([
            queryClient.invalidateQueries({ queryKey: queryKeys.drive.list(listQueryParams) }),
            folderId
                ? queryClient.invalidateQueries({ queryKey: queryKeys.drive.breadcrumb(accountId, folderId) })
                : Promise.resolve(),
        ]);
    }, [accountId, folderId, listQueryParams, queryClient]);

    const handleDelete = async (itemId) => {
        await deleteItem(accountId, itemId);
        await refresh();
    };

    const handleBatchDelete = async (itemIds) => {
        await batchDeleteItems(accountId, Array.from(itemIds));
        await refresh();
    };

    const handleCreateFolder = async (name) => {
        await createFolder(accountId, folderId || 'root', name);
        await refresh();
    };

    const canNextPage = !searchQuery && !!nextCursor;
    const canPrevPage = !searchQuery && cursorHistory.length > 0;
    const page = !searchQuery ? cursorHistory.length + 1 : 1;

    const goToNextPage = () => {
        if (!canNextPage) return;
        setCursorHistory((prev) => [...prev, currentCursor]);
        setCurrentCursor(nextCursor);
    };

    const goToPrevPage = () => {
        if (!canPrevPage) return;
        const targetCursor = cursorHistory[cursorHistory.length - 1] ?? null;
        setCursorHistory((prev) => prev.slice(0, -1));
        setCurrentCursor(targetCursor);
    };

    const resetPagination = () => {
        setCurrentCursor(null);
        setCursorHistory([]);
    };

    return {
        files,
        breadcrumbs,
        loading,
        error,
        refresh,
        handleDelete,
        handleBatchDelete,
        handleCreateFolder,
        searchQuery,
        setSearchQuery,
        page,
        canNextPage,
        canPrevPage,
        goToNextPage,
        goToPrevPage,
        resetPagination,
    };
}
