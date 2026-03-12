import userEvent from '@testing-library/user-event';
import { screen, waitFor } from '@testing-library/react';

const useAccountsQueryMock = vi.fn();
const useItemsListQueryMock = vi.fn();
const useMetadataCategoriesQueryMock = vi.fn();
const useMetadataLibrariesQueryMock = vi.fn();
const getDownloadUrlMock = vi.fn();
const getDownloadContentUrlMock = vi.fn();
const batchDeleteItemsMock = vi.fn();
const updateItemMock = vi.fn();
const createExtractComicAssetsJobMock = vi.fn();
const createAnalyzeImageAssetsJobMock = vi.fn();
const createExtractBookAssetsJobMock = vi.fn();
const createExtractLibraryComicAssetsJobMock = vi.fn();
const createAnalyzeLibraryImageAssetsJobMock = vi.fn();
const createMapLibraryBooksJobMock = vi.fn();
const uploadFileBackgroundMock = vi.fn();
const showToastMock = vi.fn();

vi.mock('../hooks/useAppQueries', () => ({
    useAccountsQuery: (...args) => useAccountsQueryMock(...args),
    useItemsListQuery: (...args) => useItemsListQueryMock(...args),
    useMetadataCategoriesQuery: (...args) => useMetadataCategoriesQueryMock(...args),
    useMetadataLibrariesQuery: (...args) => useMetadataLibrariesQueryMock(...args),
}));

vi.mock('../services/drive', () => ({
    driveService: {
        getDownloadUrl: (...args) => getDownloadUrlMock(...args),
        getDownloadContentUrl: (...args) => getDownloadContentUrlMock(...args),
        batchDeleteItems: (...args) => batchDeleteItemsMock(...args),
        renameItem: vi.fn(),
        updateItem: (...args) => updateItemMock(...args),
    },
}));

vi.mock('../services/jobs', () => ({
    jobsService: {
        createExtractComicAssetsJob: (...args) => createExtractComicAssetsJobMock(...args),
        createAnalyzeImageAssetsJob: (...args) => createAnalyzeImageAssetsJobMock(...args),
        createExtractBookAssetsJob: (...args) => createExtractBookAssetsJobMock(...args),
        createExtractLibraryComicAssetsJob: (...args) => createExtractLibraryComicAssetsJobMock(...args),
        createAnalyzeLibraryImageAssetsJob: (...args) => createAnalyzeLibraryImageAssetsJobMock(...args),
        createMapLibraryBooksJob: (...args) => createMapLibraryBooksJobMock(...args),
        uploadFileBackground: (...args) => uploadFileBackgroundMock(...args),
    },
}));

vi.mock('../contexts/ToastContext', () => ({
    ToastProvider: ({ children }) => children,
    useToast: () => ({ showToast: showToastMock }),
}));

vi.mock('../components/BatchMetadataModal', () => ({
    default: ({ isOpen }) => (isOpen ? <div>Batch Metadata Modal</div> : null),
}));

vi.mock('../components/MetadataModal', () => ({
    default: ({ isOpen }) => (isOpen ? <div>Metadata Modal</div> : null),
}));

vi.mock('../components/RemoveMetadataModal', () => ({
    default: ({ isOpen }) => (isOpen ? <div>Remove Metadata Modal</div> : null),
}));

vi.mock('../components/MoveModal', () => ({
    default: ({ isOpen }) => (isOpen ? <div>Move Modal</div> : null),
}));

import { renderWithProviders } from '../test/render';
import AllFiles from './AllFiles';

const accounts = [
    {
        id: 'acc-1',
        email: 'reader@example.com',
        provider: 'onedrive',
    },
];

const metadataLibraries = [
    { key: 'comics_core', is_active: true },
    { key: 'images_core', is_active: true },
    { key: 'books_core', is_active: true },
];

const metadataCategories = [
    { id: 'cat-1', name: 'Comics' },
    { id: 'cat-2', name: 'Books' },
];

const rootItemsResponse = {
    items: [
        {
            id: 'row-file-1',
            item_id: 'file-1',
            account_id: 'acc-1',
            parent_id: 'folder-1',
            item_type: 'file',
            name: 'cover.png',
            size: 1024,
            modified_at: '2026-03-10T12:00:00Z',
            path: '/Books/cover.png',
            metadata: { category_name: 'Comics' },
        },
        {
            id: 'row-folder-1',
            item_id: 'folder-1',
            account_id: 'acc-1',
            parent_id: null,
            item_type: 'folder',
            name: 'Books',
            size: 0,
            modified_at: '2026-03-10T12:00:00Z',
            path: '/Books',
            metadata: null,
        },
    ],
    total: 2,
    total_pages: 1,
};

const folderItemsResponse = {
    items: [
        {
            id: 'row-file-2',
            item_id: 'file-2',
            account_id: 'acc-1',
            parent_id: 'folder-1',
            item_type: 'file',
            name: 'issue-01.cbz',
            size: 2048,
            modified_at: '2026-03-10T12:10:00Z',
            path: '/Books/issue-01.cbz',
            metadata: { category_name: 'Comics' },
        },
    ],
    total: 1,
    total_pages: 1,
};

describe('AllFiles page', () => {
    beforeEach(() => {
        useAccountsQueryMock.mockReset();
        useItemsListQueryMock.mockReset();
        useMetadataCategoriesQueryMock.mockReset();
        useMetadataLibrariesQueryMock.mockReset();
        getDownloadUrlMock.mockReset();
        getDownloadContentUrlMock.mockReset();
        batchDeleteItemsMock.mockReset();
        updateItemMock.mockReset();
        createExtractComicAssetsJobMock.mockReset();
        createAnalyzeImageAssetsJobMock.mockReset();
        createExtractBookAssetsJobMock.mockReset();
        createExtractLibraryComicAssetsJobMock.mockReset();
        createAnalyzeLibraryImageAssetsJobMock.mockReset();
        createMapLibraryBooksJobMock.mockReset();
        uploadFileBackgroundMock.mockReset();
        showToastMock.mockReset();

        useAccountsQueryMock.mockReturnValue({ data: accounts });
        useMetadataCategoriesQueryMock.mockReturnValue({ data: metadataCategories });
        useMetadataLibrariesQueryMock.mockReturnValue({ data: metadataLibraries });
        useItemsListQueryMock.mockReturnValue({
            data: {
                items: [],
                total: 0,
                total_pages: 1,
            },
            isPending: false,
        });
        getDownloadUrlMock.mockResolvedValue('https://example.test/download.bin');
        getDownloadContentUrlMock.mockReturnValue('https://example.test/cover.png');
        batchDeleteItemsMock.mockResolvedValue(undefined);
        updateItemMock.mockResolvedValue(undefined);
        createExtractComicAssetsJobMock.mockResolvedValue(undefined);
        createAnalyzeImageAssetsJobMock.mockResolvedValue(undefined);
        createExtractBookAssetsJobMock.mockResolvedValue(undefined);
        createExtractLibraryComicAssetsJobMock.mockResolvedValue({ total_jobs: 2, total_items: 12, chunk_size: 1000 });
        createAnalyzeLibraryImageAssetsJobMock.mockResolvedValue({ total_jobs: 1, total_items: 8, chunk_size: 1000 });
        createMapLibraryBooksJobMock.mockResolvedValue({ total_jobs: 1, total_items: 5, chunk_size: 500 });
        uploadFileBackgroundMock.mockResolvedValue(undefined);
        window.localStorage.clear();
        window.open = vi.fn();
    });

    it('renders the empty state when there are no items', async () => {
        renderWithProviders(<AllFiles />);

        expect(screen.getAllByText(/file library/i)).toHaveLength(2);
        expect(await screen.findByText(/no items found/i)).toBeInTheDocument();
        expect(screen.getByText(/try adjusting filters or search/i)).toBeInTheDocument();
    });

    it('renders items, previews a file and navigates into its folder path', async () => {
        const user = userEvent.setup();
        useItemsListQueryMock.mockImplementation((params) => ({
            data: params.path_prefix === '/Books' ? folderItemsResponse : rootItemsResponse,
            isPending: false,
        }));

        renderWithProviders(<AllFiles />);

        expect(screen.getByText('cover.png')).toBeInTheDocument();
        expect(screen.getByText('Books')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: 'cover.png' }));
        await waitFor(() => expect(screen.getByAltText('cover.png')).toBeInTheDocument());

        await user.click(screen.getByRole('button', { name: '/Books/cover.png' }));

        await waitFor(() => {
            expect(screen.getByText('/Books')).toBeInTheDocument();
            expect(screen.getByText('issue-01.cbz')).toBeInTheDocument();
        });
    });

    it('opens metadata actions, renames and deletes the selected item', async () => {
        const user = userEvent.setup();
        useItemsListQueryMock.mockReturnValue({
            data: rootItemsResponse,
            isPending: false,
        });

        renderWithProviders(<AllFiles />);

        await screen.findByText('Books');
        await user.click(screen.getByText('Books'));
        expect(screen.getByText('1 selected')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /metadata/i }));
        await user.click(screen.getByRole('button', { name: /edit metadata/i }));
        expect(await screen.findByText('Metadata Modal')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /move/i }));
        expect(await screen.findByText('Move Modal')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /metadata/i }));
        await user.click(screen.getByRole('button', { name: /^rename$/i }));
        const renameInput = await screen.findByDisplayValue('Books');
        await user.clear(renameInput);
        await user.type(renameInput, 'Archive');
        await user.click(screen.getByRole('button', { name: /^rename$/i }));

        await waitFor(() => {
            expect(updateItemMock).toHaveBeenCalledWith('acc-1', 'folder-1', { name: 'Archive' });
        });
        expect(showToastMock).toHaveBeenCalledWith('Renamed successfully', 'success');

        await user.click(screen.getByRole('button', { name: /delete/i }));
        expect(await screen.findByText(/are you sure you want to delete the selected items/i)).toBeInTheDocument();
        await user.click(screen.getAllByRole('button', { name: /^delete$/i }).at(-1));

        await waitFor(() => {
            expect(batchDeleteItemsMock).toHaveBeenCalledWith('acc-1', ['folder-1']);
        });
        expect(showToastMock).toHaveBeenCalledWith('Selected items deleted', 'success');
    }, 15000);

    it('applies and clears filters while persisting column visibility', async () => {
        const user = userEvent.setup();
        useItemsListQueryMock.mockReturnValue({
            data: rootItemsResponse,
            isPending: false,
        });

        renderWithProviders(<AllFiles />);

        await screen.findByText('cover.png');
        await user.click(screen.getByRole('button', { name: /filters/i }));
        const [, accountSelect, categorySelect, metadataSelect, typeSelect] = screen.getAllByRole('combobox');
        await user.selectOptions(accountSelect, 'acc-1');
        await user.selectOptions(categorySelect, 'cat-1');
        await user.selectOptions(metadataSelect, 'true');
        await user.selectOptions(typeSelect, 'file');
        await user.type(screen.getByPlaceholderText(/e\.g\./i), 'cbz, pdf');
        await user.click(screen.getByRole('button', { name: /^apply$/i }));

        await waitFor(() => {
            const latestCall = useItemsListQueryMock.mock.calls.at(-1)?.[0];
            expect(latestCall).toMatchObject({
                account_id: 'acc-1',
                category_id: 'cat-1',
                has_metadata: 'true',
                item_type: 'file',
                extensions: ['cbz', 'pdf'],
            });
        });

        await user.click(screen.getByRole('button', { name: /columns/i }));
        const pathCheckbox = screen.getByRole('checkbox', { name: /path/i });
        expect(pathCheckbox).toBeChecked();
        await user.click(pathCheckbox);
        expect(pathCheckbox).not.toBeChecked();

        const savedColumns = JSON.parse(window.localStorage.getItem('driver-all-files-columns-v1'));
        expect(savedColumns.visibility.path).toBe(false);

        await user.click(screen.getByRole('button', { name: /filters/i }));
        await user.click(screen.getByRole('button', { name: /^clear$/i }));

        await waitFor(() => {
            const latestCall = useItemsListQueryMock.mock.calls.at(-1)?.[0];
            expect(latestCall).toMatchObject({
                account_id: '',
                category_id: '',
                has_metadata: '',
                item_type: '',
                extensions: [],
            });
        });
    });

    it('runs library actions and download flow for selected files', async () => {
        const user = userEvent.setup();
        useItemsListQueryMock.mockReturnValue({
            data: {
                items: [
                    {
                        id: 'row-file-book',
                        item_id: 'file-book',
                        account_id: 'acc-1',
                        parent_id: null,
                        item_type: 'file',
                        name: 'issue-01.cbz',
                        size: 2048,
                        modified_at: '2026-03-10T12:10:00Z',
                        path: '/issue-01.cbz',
                        metadata: { category_name: 'Comics' },
                    },
                ],
                total: 1,
                total_pages: 1,
            },
            isPending: false,
        });

        renderWithProviders(<AllFiles />);

        await screen.findByText('issue-01.cbz');
        await user.click(screen.getByText('issue-01.cbz').closest('.group'));

        await user.click(screen.getByRole('button', { name: /download/i }));
        await waitFor(() => expect(getDownloadUrlMock).toHaveBeenCalledWith('acc-1', 'file-book'));
        expect(window.open).toHaveBeenCalledWith('https://example.test/download.bin', '_blank');

        await user.click(screen.getByRole('button', { name: /map all as/i }));
        await user.click(screen.getByRole('button', { name: /map all comics/i }));
        await user.click(await screen.findByRole('button', { name: /^confirm$/i }));
        await waitFor(() => expect(createExtractLibraryComicAssetsJobMock).toHaveBeenCalledWith(null, 1000));

        await user.click(screen.getByRole('button', { name: /map all as/i }));
        await user.click(screen.getByRole('button', { name: /map all images/i }));
        await user.click(await screen.findByRole('button', { name: /^confirm$/i }));
        await waitFor(() => expect(createAnalyzeLibraryImageAssetsJobMock).toHaveBeenCalledWith(null, 1000, false));

        await user.click(screen.getByRole('button', { name: /map all as/i }));
        await user.click(screen.getByRole('button', { name: /map all books/i }));
        await user.click(await screen.findByRole('button', { name: /^confirm$/i }));
        await waitFor(() => expect(createMapLibraryBooksJobMock).toHaveBeenCalledWith(null, 1000));
    }, 15000);
});
