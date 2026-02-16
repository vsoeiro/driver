import { useState, useEffect, useCallback } from 'react';
import { getFiles, getFolderFiles, getPath, deleteItem, batchDeleteItems, createFolder, searchFiles } from '../services/drive';

export function useDrive(accountId, folderId) {
    const [files, setFiles] = useState([]);
    const [breadcrumbs, setBreadcrumbs] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const [searchQuery, setSearchQuery] = useState('');

    // Reset search on navigation
    useEffect(() => {
        setSearchQuery('');
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
            } else if (folderId) {
                data = await getFolderFiles(accountId, folderId);
                setFiles(data.items || []);
                try {
                    const pathData = await getPath(accountId, folderId);
                    const cleanPath = (pathData.breadcrumb || []).filter(b => b.name.toLowerCase() !== 'root');
                    setBreadcrumbs(cleanPath);
                } catch (e) {
                    console.warn("Failed to fetch path", e);
                    setBreadcrumbs([]);
                }
            } else {
                data = await getFiles(accountId);
                setFiles(data.items || []);
                setBreadcrumbs([]);
            }
        } catch (err) {
            console.error(err);
            setError(err.message || 'Failed to load files');
        } finally {
            setLoading(false);
        }
    }, [accountId, folderId, searchQuery]);

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

    return { files, breadcrumbs, loading, error, refresh: fetchFiles, handleDelete, handleBatchDelete, handleCreateFolder, searchQuery, setSearchQuery };
}
