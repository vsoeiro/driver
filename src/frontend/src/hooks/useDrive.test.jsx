import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { act } from 'react';

const invalidateQueries = vi.fn(() => Promise.resolve());
const useDriveListingQueryMock = vi.fn();
const useDriveBreadcrumbQueryMock = vi.fn();
const deleteItemMock = vi.fn(() => Promise.resolve());
const batchDeleteItemsMock = vi.fn(() => Promise.resolve());
const createFolderMock = vi.fn(() => Promise.resolve());

vi.mock('@tanstack/react-query', async () => {
    const actual = await vi.importActual('@tanstack/react-query');
    return {
        ...actual,
        useQueryClient: () => ({
            invalidateQueries,
        }),
    };
});

vi.mock('../features/drive/hooks/useDriveData', () => ({
    useDriveListingQuery: (...args) => useDriveListingQueryMock(...args),
    useDriveBreadcrumbQuery: (...args) => useDriveBreadcrumbQueryMock(...args),
    useDriveActions: () => ({
        deleteItem: (...args) => deleteItemMock(...args),
        batchDeleteItems: (...args) => batchDeleteItemsMock(...args),
        createFolder: (...args) => createFolderMock(...args),
    }),
}));

import { useDrive } from './useDrive';

function createWrapper() {
    const client = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
        },
    });
    return function Wrapper({ children }) {
        return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    };
}

describe('useDrive', () => {
    beforeEach(() => {
        invalidateQueries.mockClear();
        deleteItemMock.mockClear();
        batchDeleteItemsMock.mockClear();
        createFolderMock.mockClear();
        useDriveListingQueryMock.mockReturnValue({
            data: { items: [{ id: 'item-1' }], next_link: 'next-page' },
            isPending: false,
            error: null,
        });
        useDriveBreadcrumbQueryMock.mockReturnValue({
            data: { breadcrumb: [{ id: 'root', name: 'Root' }, { id: 'folder-1', name: 'Folder 1' }] },
        });
    });

    it('exposes files, breadcrumbs and pagination state', () => {
        const { result } = renderHook(() => useDrive('acc-1', 'folder-1', { pageSize: '25' }), {
            wrapper: createWrapper(),
        });

        expect(result.current.files).toEqual([{ id: 'item-1' }]);
        expect(result.current.breadcrumbs).toEqual([{ id: 'folder-1', name: 'Folder 1' }]);
        expect(result.current.page).toBe(1);
        expect(result.current.canNextPage).toBe(true);
        expect(result.current.canPrevPage).toBe(false);
        expect(useDriveListingQueryMock).toHaveBeenCalledWith(
            {
                accountId: 'acc-1',
                folderId: 'folder-1',
                searchQuery: '',
                cursor: null,
                pageSize: 25,
            },
            { staleTime: 30000 },
        );
    });

    it('switches to search breadcrumb and paginates', async () => {
        const { result } = renderHook(() => useDrive('acc-1', 'folder-1'), { wrapper: createWrapper() });

        act(() => {
            result.current.setSearchQuery('Dylan');
        });

        expect(result.current.breadcrumbs).toEqual([{ id: 'search', name: 'Search results: Dylan' }]);
        expect(result.current.canNextPage).toBe(false);

        act(() => {
            result.current.setSearchQuery('');
        });

        await waitFor(() => expect(result.current.canNextPage).toBe(true));

        act(() => {
            result.current.goToNextPage();
        });

        await waitFor(() => expect(result.current.page).toBe(2));
        expect(result.current.canPrevPage).toBe(true);

        act(() => {
            result.current.goToPrevPage();
        });

        expect(result.current.page).toBe(1);
    });

    it('refreshes and runs file actions', async () => {
        const { result } = renderHook(() => useDrive('acc-1', 'folder-1'), { wrapper: createWrapper() });

        await result.current.refresh();
        await result.current.handleDelete('item-1');
        await result.current.handleBatchDelete(new Set(['item-1', 'item-2']));
        await result.current.handleCreateFolder('Docs');

        expect(deleteItemMock).toHaveBeenCalledWith('acc-1', 'item-1');
        expect(batchDeleteItemsMock).toHaveBeenCalledWith('acc-1', ['item-1', 'item-2']);
        expect(createFolderMock).toHaveBeenCalledWith('acc-1', 'folder-1', 'Docs');
        expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['drive', 'list', expect.any(Object)] });
        expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['drive', 'breadcrumb', 'acc-1', 'folder-1'] });
    });

    it('resets search and cursor when navigation changes', async () => {
        const { result, rerender } = renderHook(
            ({ accountId, folderId }) => useDrive(accountId, folderId),
            {
                initialProps: { accountId: 'acc-1', folderId: 'folder-1' },
                wrapper: createWrapper(),
            },
        );

        act(() => {
            result.current.setSearchQuery('Query');
            result.current.goToNextPage();
        });

        rerender({ accountId: 'acc-1', folderId: 'folder-2' });

        await waitFor(() => expect(result.current.searchQuery).toBe(''));
        expect(result.current.page).toBe(1);
    });
});
