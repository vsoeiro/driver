import { useState, useEffect, useCallback } from 'react';
import { getFiles, getPath, deleteItem, createFolder } from '../services/api';

export function useDrive(accountId, folderId) {
    const [files, setFiles] = useState([]);
    const [breadcrumbs, setBreadcrumbs] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchFiles = useCallback(async () => {
        if (!accountId) return;
        setLoading(true);
        setError(null);
        try {
            const data = await getFiles(accountId, folderId || 'root');
            setFiles(data.items);

            // Breadcrumbs
            if (folderId && folderId !== 'root') {
                try {
                    const pathData = await getPath(accountId, folderId);
                    // Filter out "root" from API response to avoid duplication if we handle it manually
                    const cleanPath = pathData.breadcrumb.filter(b => b.name.toLowerCase() !== 'root');
                    setBreadcrumbs(cleanPath);
                } catch (e) {
                    console.warn("Failed to fetch path", e);
                    setBreadcrumbs([]);
                }
            } else {
                setBreadcrumbs([]);
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, [accountId, folderId]);

    useEffect(() => {
        fetchFiles();
    }, [fetchFiles]);

    const handleDelete = async (itemId) => {
        try {
            await deleteItem(accountId, itemId);
            fetchFiles();
        } catch (e) {
            throw e;
        }
    };

    const handleCreateFolder = async (name) => {
        try {
            await createFolder(accountId, folderId || 'root', name);
            fetchFiles();
        } catch (e) {
            throw e;
        }
    };

    return { files, breadcrumbs, loading, error, refresh: fetchFiles, handleDelete, handleCreateFolder };
}
