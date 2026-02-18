import { useState, useEffect, useCallback } from 'react';
import { getFiles, getFolderFiles, getPath, deleteItem, batchDeleteItems, createFolder, searchFiles } from '../services/drive';

export function useDrive(accountId, folderId) {
    const [files, setFiles] = useState([]);
    const [breadcrumbs, setBreadcrumbs] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const [searchQuery, setSearchQuery] = useState('');
    const [currentCursor, setCurrentCursor] = useState(null);
    const [cursorHistory, setCursorHistory] = useState([]);
    const [nextCursor, setNextCursor] = useState(null);

    // Reset search on navigation
    useEffect(() => {
        setSearchQuery('');
        setCurrentCursor(null);
        setCursorHistory([]);
        setNextCursor(null);
    }, [folderId, accountId]);

    const fetchFiles = useCallback(async () => {
        if (!accountId) return;
        setLoading(true);
        setError(null);
        try {
            let data;
            if (searchQuery) {
                data = await searchFiles(accountId, searchQuery);
                setFiles(data.items || []);
                setBreadcrumbs([{ id: 'search', name: `Search results: ${searchQuery}` }]);
                setCurrentCursor(null);
                setCursorHistory([]);
                setNextCursor(null);
            } else if (folderId) {
                data = await getFolderFiles(accountId, folderId, { nextLink: currentCursor });
                setFiles(data.items || []);
                setNextCursor(data.next_link || null);
                try {
                    const pathData = await getPath(accountId, folderId);
                    const cleanPath = (pathData.breadcrumb || []).filter(b => b.name.toLowerCase() !== 'root');
                    setBreadcrumbs(cleanPath);
                } catch (e) {
                    console.warn("Failed to fetch path", e);
                    setBreadcrumbs([]);
                }
            } else {
                data = await getFiles(accountId, { nextLink: currentCursor });
                setFiles(data.items || []);
                setBreadcrumbs([]);
                setNextCursor(data.next_link || null);
            }
        } catch (err) {
            console.error(err);
            setError(err.message || 'Failed to load files');
        } finally {
            setLoading(false);
        }
    }, [accountId, folderId, searchQuery, currentCursor]);

    useEffect(() => {
        fetchFiles();
    }, [fetchFiles]);

    const handleDelete = async (itemId) => {
        await deleteItem(accountId, itemId);
        fetchFiles();
    };

    const handleBatchDelete = async (itemIds) => {
        // If single item, fallback to simple delete? No, batch endpoint handles list.
        await batchDeleteItems(accountId, Array.from(itemIds));
        fetchFiles();
    };

    const handleCreateFolder = async (name) => {
        await createFolder(accountId, folderId || 'root', name);
        fetchFiles();
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
        setNextCursor(null);
    };

    return {
        files,
        breadcrumbs,
        loading,
        error,
        refresh: fetchFiles,
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
