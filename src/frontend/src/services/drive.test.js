vi.mock('./api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        delete: vi.fn(),
        put: vi.fn(),
        patch: vi.fn(),
    },
}));

import api from './api';
import {
    batchDeleteItems,
    createFolder,
    createComicReaderSession,
    createUploadSession,
    deleteItem,
    getComicReaderPageUrl,
    getDownloadContentUrl,
    getDownloadUrl,
    getFiles,
    getFolderFiles,
    getPath,
    getQuota,
    searchFiles,
    updateItem,
} from './drive';

describe('drive service', () => {
    it('fetches root files with pagination params', async () => {
        api.get.mockResolvedValue({ data: { items: [] } });

        await expect(getFiles('acc-1', { nextLink: 'next', pageSize: 25, signal: 'signal' })).resolves.toEqual({ items: [] });
        expect(api.get).toHaveBeenCalledWith('/drive/acc-1/files', {
            params: { next_link: 'next', page_size: 25 },
            signal: 'signal',
        });
    });

    it('fetches folder files and breadcrumb path', async () => {
        api.get
            .mockResolvedValueOnce({ data: { items: [] } })
            .mockResolvedValueOnce({ data: { path: ['/Root'] } });

        await getFolderFiles('acc-1', 'folder-1');
        await getPath('acc-1', 'folder-1', { signal: 'sig' });

        expect(api.get).toHaveBeenNthCalledWith(1, '/drive/acc-1/files/folder-1', {
            params: {},
            signal: undefined,
        });
        expect(api.get).toHaveBeenNthCalledWith(2, '/drive/acc-1/path/folder-1', { signal: 'sig' });
    });

    it('creates folders and upload sessions', async () => {
        api.post.mockResolvedValue({ data: { ok: true } });

        await createFolder('acc-1', 'root', 'Docs');
        await createUploadSession('acc-1', 'folder-1', 'book.cbz', 321);

        expect(api.post).toHaveBeenNthCalledWith(1, '/drive/acc-1/folders', {
            name: 'Docs',
            parent_folder_id: undefined,
            conflict_behavior: 'rename',
        });
        expect(api.post).toHaveBeenNthCalledWith(2, '/drive/acc-1/upload/session', {
            filename: 'book.cbz',
            file_size: 321,
            folder_id: 'folder-1',
            conflict_behavior: 'rename',
        });
    });

    it('builds download urls and search requests', async () => {
        api.get
            .mockResolvedValueOnce({ data: { download_url: 'https://example.test/file' } })
            .mockResolvedValueOnce({ data: { total: 1 } })
            .mockResolvedValueOnce({ data: { remaining: 99 } });

        await expect(getDownloadUrl('acc 1', 'item/1', { autoResolveAccount: true })).resolves.toBe('https://example.test/file');
        expect(getDownloadContentUrl('acc 1', 'item/1', { autoResolveAccount: true })).toBe(
            '/api/v1/drive/acc%201/download/item%2F1/content?auto_resolve_account=true',
        );
        await searchFiles('acc-1', 'Dylan Dog', { signal: 'signal' });
        await getQuota('acc-1', { signal: 'signal' });

        expect(api.get).toHaveBeenNthCalledWith(1, '/drive/acc 1/download/item/1?auto_resolve_account=true');
        expect(api.get).toHaveBeenNthCalledWith(2, '/drive/acc-1/search?q=Dylan%20Dog', { signal: 'signal' });
        expect(api.get).toHaveBeenNthCalledWith(3, '/drive/acc-1/quota', { signal: 'signal' });
    });

    it('creates reader sessions and builds page urls', async () => {
        api.post.mockResolvedValue({ data: { session_id: 'session-1' } });

        await expect(createComicReaderSession('acc-1', 'item-9')).resolves.toEqual({ session_id: 'session-1' });
        expect(getComicReaderPageUrl('acc 1', 'session/1', 3)).toBe(
            '/api/v1/drive/acc%201/reader/comics/sessions/session%2F1/pages/3',
        );
        expect(api.post).toHaveBeenCalledWith('/drive/acc-1/reader/comics/item-9/sessions');
    });

    it('deletes, batch deletes and updates items', async () => {
        api.delete.mockResolvedValue({});
        api.post.mockResolvedValue({ data: { removed: true } });
        api.patch.mockResolvedValue({ data: { id: 'item-1' } });

        await deleteItem('acc-1', 'item-1');
        await batchDeleteItems('acc-1', ['a', 'b']);
        await expect(updateItem('acc-1', 'item-1', { name: 'Renamed' })).resolves.toEqual({ id: 'item-1' });

        expect(api.delete).toHaveBeenCalledWith('/drive/acc-1/items/item-1');
        expect(api.post).toHaveBeenCalledWith('/drive/acc-1/items/batch-delete', { item_ids: ['a', 'b'] });
        expect(api.patch).toHaveBeenCalledWith('/drive/acc-1/items/item-1', { name: 'Renamed' });
    });
});
