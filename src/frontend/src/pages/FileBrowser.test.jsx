import userEvent from '@testing-library/user-event';
import { fireEvent, screen, waitFor } from '@testing-library/react';

const useDriveMock = vi.fn();
const useUploadMock = vi.fn();
const useAccountsQueryMock = vi.fn();
const useMetadataLibrariesQueryMock = vi.fn();
const getDownloadUrlMock = vi.fn();
const updateItemMock = vi.fn();
const showToastMock = vi.fn();
const batchDeleteMetadataMock = vi.fn();
const batchUpdateMetadataMock = vi.fn();
const createSyncJobMock = vi.fn();
const createExtractComicAssetsJobMock = vi.fn();
const createExtractBookAssetsJobMock = vi.fn();
const createAnalyzeImageAssetsJobMock = vi.fn();
const createExtractZipJobMock = vi.fn();
const createMetadataUpdateJobMock = vi.fn();
const applyMetadataRecursiveMock = vi.fn();

vi.mock('react-router-dom', async () => {
    const actual = await vi.importActual('react-router-dom');
    return {
        ...actual,
        useParams: () => ({ accountId: 'acc-1', folderId: 'root' }),
    };
});

vi.mock('../hooks/useDrive', () => ({
    useDrive: (...args) => useDriveMock(...args),
}));

vi.mock('../hooks/useUpload', () => ({
    useUpload: (...args) => useUploadMock(...args),
}));

vi.mock('../hooks/useAppQueries', () => ({
    useAccountsQuery: (...args) => useAccountsQueryMock(...args),
    useMetadataLibrariesQuery: (...args) => useMetadataLibrariesQueryMock(...args),
}));

vi.mock('../services/drive', () => ({
    driveService: {
        getDownloadUrl: (...args) => getDownloadUrlMock(...args),
        getDownloadContentUrl: vi.fn(() => 'https://example.test/cover.png'),
        updateItem: (...args) => updateItemMock(...args),
    },
}));

vi.mock('../services/metadata', () => ({
    batchDeleteMetadata: (...args) => batchDeleteMetadataMock(...args),
    metadataService: {
        getCategories: vi.fn(() => Promise.resolve([])),
        getItemMetadata: vi.fn(() => Promise.resolve(null)),
        listFormLayouts: vi.fn(() => Promise.resolve([])),
        getItemMetadataHistory: vi.fn(() => Promise.resolve([])),
        saveItemMetadata: vi.fn(() => Promise.resolve(undefined)),
        listCategories: vi.fn(() => Promise.resolve([])),
    },
}));

vi.mock('../services/jobs', () => ({
    jobsService: {
        createSyncJob: (...args) => createSyncJobMock(...args),
        createExtractComicAssetsJob: (...args) => createExtractComicAssetsJobMock(...args),
        createExtractBookAssetsJob: (...args) => createExtractBookAssetsJobMock(...args),
        createAnalyzeImageAssetsJob: (...args) => createAnalyzeImageAssetsJobMock(...args),
        createExtractZipJob: (...args) => createExtractZipJobMock(...args),
        createMetadataUpdateJob: (...args) => createMetadataUpdateJobMock(...args),
        applyMetadataRecursive: (...args) => applyMetadataRecursiveMock(...args),
    },
}));

vi.mock('../services/items', () => ({
    itemsService: {
        batchUpdateMetadata: (...args) => batchUpdateMetadataMock(...args),
    },
}));

vi.mock('../contexts/ToastContext', () => ({
    ToastProvider: ({ children }) => children,
    useToast: () => ({ showToast: showToastMock }),
}));

vi.mock('../components/MetadataModal', () => ({
    __esModule: true,
    default: ({ isOpen }) => (isOpen ? <div>Metadata Modal</div> : null),
}));

vi.mock('../components/BatchMetadataModal', () => ({
    __esModule: true,
    default: ({ isOpen }) => (isOpen ? <div>Batch Metadata Modal</div> : null),
}));

vi.mock('../components/MetadataModal.jsx', () => ({
    __esModule: true,
    default: ({ isOpen }) => (isOpen ? <div>Metadata Modal</div> : null),
}));

vi.mock('../components/BatchMetadataModal.jsx', () => ({
    __esModule: true,
    default: ({ isOpen }) => (isOpen ? <div>Batch Metadata Modal</div> : null),
}));

vi.mock('../components/MoveModal', () => ({
    default: ({ isOpen }) => (isOpen ? <div>Move Modal</div> : null),
}));

vi.mock('../components/ExtractZipModal', () => ({
    __esModule: true,
    default: ({ isOpen, onConfirm }) => (
        isOpen ? (
            <button
                type="button"
                onClick={() => onConfirm({
                    target: { account_id: 'dest-acc', folder_id: 'folder-9', folder_path: 'Root/Extracted' },
                    deleteSourceAfterExtract: true,
                })}
            >
                Confirm Extract ZIP
            </button>
        ) : null
    ),
}));

vi.mock('../components/ExtractZipModal.jsx', () => ({
    __esModule: true,
    default: ({ isOpen, onConfirm }) => (
        isOpen ? (
            <button
                type="button"
                onClick={() => onConfirm({
                    target: { account_id: 'dest-acc', folder_id: 'folder-9', folder_path: 'Root/Extracted' },
                    deleteSourceAfterExtract: true,
                })}
            >
                Confirm Extract ZIP
            </button>
        ) : null
    ),
}));

import { renderWithProviders } from '../test/render';
import FileBrowser from './FileBrowser';

function makeDriveState(overrides = {}) {
    return {
        files: [],
        breadcrumbs: [],
        loading: false,
        error: null,
        refresh: vi.fn(),
        handleBatchDelete: vi.fn(),
        handleCreateFolder: vi.fn(),
        searchQuery: '',
        setSearchQuery: vi.fn(),
        page: 1,
        canNextPage: false,
        canPrevPage: false,
        goToNextPage: vi.fn(),
        goToPrevPage: vi.fn(),
        resetPagination: vi.fn(),
        ...overrides,
    };
}

describe('FileBrowser page', () => {
    beforeEach(() => {
        showToastMock.mockReset();
        batchDeleteMetadataMock.mockReset();
        batchUpdateMetadataMock.mockReset();
        createSyncJobMock.mockReset();
        createExtractComicAssetsJobMock.mockReset();
        createExtractBookAssetsJobMock.mockReset();
        createAnalyzeImageAssetsJobMock.mockReset();
        createExtractZipJobMock.mockReset();
        createMetadataUpdateJobMock.mockReset();
        applyMetadataRecursiveMock.mockReset();
        getDownloadUrlMock.mockReset();
        updateItemMock.mockReset();
        useUploadMock.mockReturnValue({
            upload: vi.fn(),
            uploading: false,
            progress: 0,
        });
        useAccountsQueryMock.mockReturnValue({
            data: [{ id: 'acc-1', email: 'reader@example.com' }],
        });
        batchDeleteMetadataMock.mockResolvedValue(undefined);
        batchUpdateMetadataMock.mockResolvedValue(undefined);
        createSyncJobMock.mockResolvedValue({ id: 'job-sync' });
        createExtractComicAssetsJobMock.mockResolvedValue({ id: 'job-comics' });
        createExtractBookAssetsJobMock.mockResolvedValue({ id: 'job-books' });
        createAnalyzeImageAssetsJobMock.mockResolvedValue({ id: 'job-images' });
        createExtractZipJobMock.mockResolvedValue({ id: 'job-zip' });
        createMetadataUpdateJobMock.mockResolvedValue({ id: 'job-metadata' });
        applyMetadataRecursiveMock.mockResolvedValue({ id: 'job-recursive' });
        getDownloadUrlMock.mockResolvedValue('https://example.test/download');
        updateItemMock.mockResolvedValue({ id: 'file-1', name: 'issue-02.epub' });
        useMetadataLibrariesQueryMock.mockReturnValue({
            data: [],
        });
        useDriveMock.mockReturnValue(makeDriveState());
    });

    it('renders empty and error states', () => {
        const emptyView = renderWithProviders(<FileBrowser />);
        expect(screen.getByText(/this folder is empty/i)).toBeInTheDocument();
        expect(screen.getByText(/0 items/i)).toBeInTheDocument();

        useDriveMock.mockReturnValue(makeDriveState({ error: 'boom' }));
        emptyView.unmount();
        renderWithProviders(<FileBrowser />);

        expect(screen.getByText(/boom/i)).toBeInTheDocument();
    });

    it('renders files list and opens image preview', async () => {
        const user = userEvent.setup();
        useDriveMock.mockReturnValue(
            makeDriveState({
                files: [
                    {
                        id: 'file-1',
                        name: 'cover.png',
                        item_type: 'file',
                        size: 1024,
                        modified_at: '2026-03-10T12:00:00Z',
                    },
                    {
                        id: 'folder-1',
                        name: 'Books',
                        item_type: 'folder',
                        size: 0,
                        modified_at: '2026-03-10T12:00:00Z',
                    },
                ],
            }),
        );

        renderWithProviders(<FileBrowser />);

        expect(screen.getByText('cover.png')).toBeInTheDocument();
        expect(screen.getByText('Books')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: 'cover.png' }));

        await waitFor(() => expect(screen.getByAltText('cover.png')).toBeInTheDocument());
    });

    it('syncs, creates folders and opens metadata actions for single and batch selections', async () => {
        const user = userEvent.setup();
        const handleCreateFolder = vi.fn().mockResolvedValue(undefined);
        const refresh = vi.fn();

        useMetadataLibrariesQueryMock.mockReturnValue({
            data: [
                { key: 'comics_core', is_active: true },
                { key: 'images_core', is_active: true },
                { key: 'books_core', is_active: true },
            ],
        });
        useDriveMock.mockReturnValue(
            makeDriveState({
                refresh,
                handleCreateFolder,
                files: [
                    {
                        id: 'folder-1',
                        name: 'Books',
                        item_type: 'folder',
                        size: 0,
                        modified_at: '2026-03-10T12:00:00Z',
                    },
                    {
                        id: 'file-1',
                        name: 'issue-01.cbz',
                        item_type: 'file',
                        size: 2048,
                        modified_at: '2026-03-10T12:10:00Z',
                    },
                ],
            }),
        );

        renderWithProviders(<FileBrowser />);

        await user.click(screen.getByRole('button', { name: /sync/i }));
        await waitFor(() => expect(createSyncJobMock).toHaveBeenCalledWith('acc-1'));

        await user.click(screen.getByRole('button', { name: /new folder/i }));
        await user.type(screen.getAllByRole('textbox').at(-1), 'Archive');
        await user.click(screen.getByRole('button', { name: /^create$/i }));
        await waitFor(() => expect(handleCreateFolder).toHaveBeenCalledWith('Archive'));

        await user.click(screen.getByText('0 B'));
        expect(screen.getByText('1 selected')).toBeInTheDocument();

        const metadataButton = screen.getByRole('button', { name: /^metadata$/i });
        fireEvent.mouseEnter(metadataButton.parentElement);
        await user.click(screen.getByRole('button', { name: /edit metadata/i }));
        expect(await screen.findByText('Metadata: Books')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /close modal/i }));

        await user.click(screen.getByText('2 KB'));
        expect(screen.getByText('2 selected')).toBeInTheDocument();

        fireEvent.mouseEnter(metadataButton.parentElement);
        await user.click(screen.getByRole('button', { name: /edit metadata/i }));
        expect(await screen.findByText('Edit metadata (2 selected)')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /close modal/i }));

        fireEvent.mouseEnter(metadataButton.parentElement);
        await user.click(screen.getByRole('button', { name: /remove metadata/i }));
        await user.click(screen.getByRole('button', { name: /^remove$/i }));
        await waitFor(() => {
            expect(batchDeleteMetadataMock).toHaveBeenCalledWith('acc-1', ['folder-1', 'file-1']);
        });

        fireEvent.mouseEnter(metadataButton.parentElement);
        await user.click(screen.getByRole('button', { name: /comics/i }));
        await waitFor(() => {
            expect(createExtractComicAssetsJobMock).toHaveBeenCalledWith('acc-1', ['folder-1', 'file-1']);
        });
    }, 15000);

    it('submits search, renames, clears it, downloads, deletes and accepts dropped uploads', async () => {
        const user = userEvent.setup();
        const uploadMock = vi.fn();
        const setSearchQuery = vi.fn();
        const resetPagination = vi.fn();
        const handleBatchDelete = vi.fn().mockResolvedValue(undefined);
        const windowOpenMock = vi.spyOn(window, 'open').mockImplementation(() => null);

        useUploadMock.mockReturnValue({
            upload: uploadMock,
            uploading: false,
            progress: 0,
        });
        useDriveMock.mockReturnValue(
            makeDriveState({
                handleBatchDelete,
                setSearchQuery,
                resetPagination,
                files: [
                    {
                        id: 'file-1',
                        name: 'issue-01.epub',
                        item_type: 'file',
                        size: 2048,
                        modified_at: '2026-03-10T12:10:00Z',
                    },
                ],
            }),
        );

        renderWithProviders(<FileBrowser />);

        const searchInput = screen.getByPlaceholderText(/search files/i);
        await user.type(searchInput, 'issue');
        fireEvent.keyDown(searchInput, { key: 'Enter' });

        expect(resetPagination).toHaveBeenCalled();
        expect(setSearchQuery).toHaveBeenCalledWith('issue');

        await user.click(screen.getByText('2 KB'));
        await user.click(screen.getByRole('button', { name: /^rename$/i }));
        const renameInput = screen.getByRole('textbox', { name: /new name/i });
        await user.clear(renameInput);
        await user.type(renameInput, 'issue-02.epub');
        await user.click(screen.getByRole('button', { name: /^save$/i }));

        await waitFor(() => {
            expect(updateItemMock).toHaveBeenCalledWith('acc-1', 'file-1', { name: 'issue-02.epub' });
        });
        expect(showToastMock).toHaveBeenCalledWith('Renamed successfully', 'success');

        const clearButton = searchInput.parentElement.querySelector('button');
        await user.click(clearButton);

        expect(setSearchQuery).toHaveBeenCalledWith('');

        await user.click(screen.getByText('2 KB'));
        await user.click(screen.getByRole('button', { name: /download/i }));

        await waitFor(() => {
            expect(getDownloadUrlMock).toHaveBeenCalledWith('acc-1', 'file-1');
        });
        expect(windowOpenMock).toHaveBeenCalledWith('https://example.test/download', '_blank');

        await user.click(screen.getByRole('button', { name: /delete/i }));
        await user.click(screen.getAllByRole('button', { name: /delete/i }).at(-1));

        await waitFor(() => {
            expect(handleBatchDelete).toHaveBeenCalledWith(['file-1']);
        });

        const navShell = screen.getByRole('link', { name: /root/i }).closest('div');
        const droppedFile = new File(['hello'], 'new-issue.cbz', { type: 'application/x-cbz' });
        fireEvent.dragEnter(navShell, {
            dataTransfer: { types: ['Files'], files: [droppedFile], dropEffect: 'copy' },
        });
        fireEvent.dragOver(navShell, {
            dataTransfer: { types: ['Files'], files: [droppedFile], dropEffect: 'copy' },
        });
        fireEvent.drop(navShell, {
            dataTransfer: { types: ['Files'], files: [droppedFile], dropEffect: 'copy' },
        });

        expect(uploadMock).toHaveBeenCalledWith([droppedFile]);
        windowOpenMock.mockRestore();
    });

    it('creates image and book analysis jobs for compatible selections', async () => {
        const user = userEvent.setup();

        useMetadataLibrariesQueryMock.mockReturnValue({
            data: [
                { key: 'images_core', is_active: true },
                { key: 'books_core', is_active: true },
            ],
        });
        useDriveMock.mockReturnValue(
            makeDriveState({
                files: [
                    {
                        id: 'image-1',
                        name: 'cover.png',
                        item_type: 'file',
                        size: 1024,
                        modified_at: '2026-03-10T12:00:00Z',
                    },
                    {
                        id: 'book-1',
                        name: 'issue-01.epub',
                        item_type: 'file',
                        size: 2048,
                        modified_at: '2026-03-10T12:10:00Z',
                    },
                ],
            }),
        );

        renderWithProviders(<FileBrowser />);

        const metadataButton = screen.getByRole('button', { name: /^metadata$/i });

        await user.click(screen.getByText('1 KB'));
        fireEvent.mouseEnter(metadataButton.parentElement);
        await user.click(screen.getByRole('button', { name: /images/i }));

        await waitFor(() => {
            expect(createAnalyzeImageAssetsJobMock).toHaveBeenCalledWith('acc-1', ['image-1'], false, false);
        });

        await user.click(screen.getByText('1 KB'));
        await user.click(screen.getByText('2 KB'));
        fireEvent.mouseEnter(metadataButton.parentElement);
        await user.click(screen.getByRole('button', { name: /books/i }));

        await waitFor(() => {
            expect(createExtractBookAssetsJobMock).toHaveBeenCalledWith('acc-1', ['book-1']);
        });
    });

    it('enables ZIP extraction only for selected .zip files', async () => {
        const user = userEvent.setup();

        useDriveMock.mockReturnValue(
            makeDriveState({
                files: [
                    {
                        id: 'zip-1',
                        name: 'bundle.zip',
                        item_type: 'file',
                        size: 4096,
                        modified_at: '2026-03-10T12:10:00Z',
                    },
                    {
                        id: 'text-1',
                        name: 'notes.txt',
                        item_type: 'file',
                        size: 2048,
                        modified_at: '2026-03-10T12:12:00Z',
                    },
                ],
            }),
        );

        renderWithProviders(<FileBrowser />);

        const extractZipButton = screen.getByRole('button', { name: /extract zip/i });
        expect(extractZipButton).toBeDisabled();

        await user.click(screen.getByText('4 KB'));
        expect(extractZipButton).toBeEnabled();

        await user.click(screen.getByText('2 KB'));
        expect(extractZipButton).toBeDisabled();
        expect(createExtractZipJobMock).not.toHaveBeenCalled();
    });

    it('surfaces sync, rename, folder, delete and metadata action failures', async () => {
        const user = userEvent.setup();
        const handleCreateFolder = vi.fn().mockRejectedValue(new Error('folder boom'));
        const handleBatchDelete = vi.fn().mockRejectedValue(new Error('delete boom'));

        createSyncJobMock.mockRejectedValue(new Error('sync boom'));
        updateItemMock.mockRejectedValue(new Error('rename boom'));
        batchDeleteMetadataMock.mockRejectedValue(new Error('remove boom'));
        createExtractComicAssetsJobMock.mockRejectedValue(new Error('comics boom'));
        createAnalyzeImageAssetsJobMock.mockRejectedValue(new Error('images boom'));
        createExtractBookAssetsJobMock.mockRejectedValue(new Error('books boom'));

        useMetadataLibrariesQueryMock.mockReturnValue({
            data: [
                { key: 'comics_core', is_active: true },
                { key: 'images_core', is_active: true },
                { key: 'books_core', is_active: true },
            ],
        });
        useDriveMock.mockReturnValue(
            makeDriveState({
                handleCreateFolder,
                handleBatchDelete,
                files: [
                    {
                        id: 'folder-1',
                        name: 'Library',
                        item_type: 'folder',
                        size: 0,
                        modified_at: '2026-03-10T12:00:00Z',
                    },
                ],
            }),
        );

        renderWithProviders(<FileBrowser />);

        await user.click(screen.getByRole('button', { name: /sync/i }));
        await waitFor(() => expect(showToastMock).toHaveBeenCalledWith(expect.stringContaining('sync boom'), 'error'));

        await user.click(screen.getByText('0 B'));
        await user.click(screen.getByRole('button', { name: /^rename$/i }));
        const renameInput = screen.getByRole('textbox', { name: /new name/i });
        await user.clear(renameInput);
        await user.type(renameInput, 'Library Renamed');
        await user.click(screen.getByRole('button', { name: /^save$/i }));
        await waitFor(() => expect(showToastMock).toHaveBeenCalledWith(expect.stringContaining('rename boom'), 'error'));

        await user.click(screen.getByRole('button', { name: /new folder/i }));
        await user.type(screen.getAllByRole('textbox').at(-1), 'Broken');
        await user.click(screen.getByRole('button', { name: /^create$/i }));
        await waitFor(() => expect(showToastMock).toHaveBeenCalledWith('folder boom', 'error'));
        const metadataButton = screen.getByRole('button', { name: /^metadata$/i });

        await user.click(screen.getByRole('button', { name: /delete/i }));
        await user.click(screen.getAllByRole('button', { name: /delete/i }).at(-1));
        await waitFor(() => expect(showToastMock).toHaveBeenCalledWith('delete boom', 'error'));

        fireEvent.mouseEnter(metadataButton.parentElement);
        await user.click(screen.getByRole('button', { name: /remove metadata/i }));
        await user.click(screen.getByRole('button', { name: /^remove$/i }));
        await waitFor(() => expect(showToastMock).toHaveBeenCalledWith('remove boom', 'error'));

        fireEvent.mouseEnter(metadataButton.parentElement);
        await user.click(screen.getByRole('button', { name: /^comics$/i }));
        await waitFor(() => expect(showToastMock).toHaveBeenCalledWith(expect.stringContaining('comics boom'), 'error'));
    }, 15000);
});
