import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';

vi.mock('../services/accounts', () => ({
    accountsService: {
        getAccounts: vi.fn(async () => [{ id: 'acc-1' }]),
    },
}));

vi.mock('../services/metadata', () => ({
    metadataService: {
        listCategories: vi.fn(async () => ({ categories: [] })),
        listMetadataLibraries: vi.fn(async () => ({ libraries: [] })),
    },
}));

vi.mock('../services/settings', () => ({
    settingsService: {
        getObservabilitySnapshot: vi.fn(async ({ period, forceRefresh }) => ({ period, forceRefresh })),
    },
}));

vi.mock('../services/drive', () => ({
    driveService: {
        getQuota: vi.fn(async (accountId) => ({ accountId })),
        getFolderFiles: vi.fn(async (accountId, folderId, options) => ({ accountId, folderId, options })),
        getFiles: vi.fn(async (accountId, options) => ({ accountId, options })),
        getPath: vi.fn(async (accountId, folderId) => ({ accountId, folderId })),
        searchFiles: vi.fn(async (accountId, searchQuery) => ({ accountId, searchQuery })),
    },
}));

vi.mock('../services/items', () => ({
    itemsService: {
        listItems: vi.fn(async (params) => ({ items: [], params })),
    },
}));

import { accountsService } from '../services/accounts';
import { driveService } from '../services/drive';
import { itemsService } from '../services/items';
import { settingsService } from '../services/settings';
import {
    useAccountsQuery,
    useDriveBreadcrumbQuery,
    useDriveListingQuery,
    useItemsListQuery,
    useObservabilityQuery,
    useQuotaQuery,
} from './useAppQueries';

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: {
                retry: false,
            },
        },
    });

    return function Wrapper({ children }) {
        return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    };
}

describe('useAppQueries', () => {
    it('loads accounts', async () => {
        const { result } = renderHook(() => useAccountsQuery(), { wrapper: createWrapper() });

        await waitFor(() => expect(result.current.isSuccess).toBe(true));
        expect(accountsService.getAccounts).toHaveBeenCalled();
        expect(result.current.data).toEqual([{ id: 'acc-1' }]);
    });

    it('uses search when a search query exists', async () => {
        const { result } = renderHook(
            () => useDriveListingQuery({ accountId: 'acc-1', searchQuery: 'dylan' }),
            { wrapper: createWrapper() },
        );

        await waitFor(() => expect(result.current.isSuccess).toBe(true));
        expect(driveService.searchFiles).toHaveBeenCalledWith('acc-1', 'dylan', expect.any(Object));
    });

    it('uses folder listing when a folder id exists', async () => {
        const { result } = renderHook(
            () => useDriveListingQuery({ accountId: 'acc-1', folderId: 'folder-1', cursor: 'next', pageSize: 25 }),
            { wrapper: createWrapper() },
        );

        await waitFor(() => expect(result.current.isSuccess).toBe(true));
        expect(driveService.getFolderFiles).toHaveBeenCalledWith(
            'acc-1',
            'folder-1',
            expect.objectContaining({ nextLink: 'next', pageSize: 25 }),
        );
    });

    it('uses root listing when only account exists', async () => {
        const { result } = renderHook(() => useDriveListingQuery({ accountId: 'acc-1' }), { wrapper: createWrapper() });

        await waitFor(() => expect(result.current.isSuccess).toBe(true));
        expect(driveService.getFiles).toHaveBeenCalledWith('acc-1', expect.any(Object));
    });

    it('disables quota requests without account id', () => {
        const { result } = renderHook(() => useQuotaQuery('', {}), { wrapper: createWrapper() });

        expect(result.current.fetchStatus).toBe('idle');
        expect(driveService.getQuota).not.toHaveBeenCalled();
    });

    it('loads breadcrumb and items list', async () => {
        const { result: breadcrumb } = renderHook(() => useDriveBreadcrumbQuery('acc-1', 'folder-1'), {
            wrapper: createWrapper(),
        });
        const { result: items } = renderHook(
            () => useItemsListQuery({ q: 'file', extensions: ['cbz'], page: 2 }),
            { wrapper: createWrapper() },
        );

        await waitFor(() => expect(breadcrumb.current.isSuccess).toBe(true));
        await waitFor(() => expect(items.current.isSuccess).toBe(true));
        expect(driveService.getPath).toHaveBeenCalledWith('acc-1', 'folder-1', expect.any(Object));
        expect(itemsService.listItems).toHaveBeenCalledWith(
            expect.objectContaining({ q: 'file', extensions: ['cbz'], page: 2 }),
            expect.any(Object),
        );
    });

    it('passes observability options through', async () => {
        const { result } = renderHook(
            () => useObservabilityQuery({ period: '7d', forceRefresh: true }),
            { wrapper: createWrapper() },
        );

        await waitFor(() => expect(result.current.isSuccess).toBe(true));
        expect(settingsService.getObservabilitySnapshot).toHaveBeenCalledWith(
            expect.objectContaining({ period: '7d', forceRefresh: true }),
        );
    });
});
