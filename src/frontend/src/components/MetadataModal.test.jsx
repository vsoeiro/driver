import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const getCategoriesMock = vi.fn();
const getItemMetadataMock = vi.fn();
const listFormLayoutsMock = vi.fn();
const getItemMetadataHistoryMock = vi.fn();
const saveItemMetadataMock = vi.fn();
const createMetadataUpdateJobMock = vi.fn();
const getDownloadContentUrlMock = vi.fn();
const showToastMock = vi.fn();

let categoriesState = [];
let metadataState = null;
let layoutsState = [];
let historyState = [];

function clone(value) {
    if (value === null || value === undefined) return value;
    return JSON.parse(JSON.stringify(value));
}

vi.mock('./Modal', () => ({
    default: ({ isOpen, title, children }) => (
        isOpen ? (
            <div role="dialog" aria-label={title}>
                {children}
            </div>
        ) : null
    ),
}));

vi.mock('../services/metadata', () => ({
    metadataService: {
        getCategories: (...args) => getCategoriesMock(...args),
        getItemMetadata: (...args) => getItemMetadataMock(...args),
        listFormLayouts: (...args) => listFormLayoutsMock(...args),
        getItemMetadataHistory: (...args) => getItemMetadataHistoryMock(...args),
        saveItemMetadata: (...args) => saveItemMetadataMock(...args),
    },
}));

vi.mock('../services/jobs', () => ({
    jobsService: {
        createMetadataUpdateJob: (...args) => createMetadataUpdateJobMock(...args),
    },
}));

vi.mock('../services/drive', () => ({
    driveService: {
        getDownloadContentUrl: (...args) => getDownloadContentUrlMock(...args),
    },
}));

vi.mock('../contexts/ToastContext', () => ({
    ToastProvider: ({ children }) => children,
    useToast: () => ({ showToast: showToastMock }),
}));

import { renderWithProviders } from '../test/render';
import MetadataModal from './MetadataModal';

function buildComicCategory() {
    return {
        id: 'cat-comics',
        name: 'Comics',
        plugin_key: 'comics_core',
        attributes: [
            { id: 'attr-series', name: 'Series', data_type: 'text', is_required: true, plugin_field_key: 'series' },
            { id: 'attr-title', name: 'Title', data_type: 'text', is_required: false, plugin_field_key: 'title' },
            { id: 'attr-tags', name: 'Tags', data_type: 'tags', is_required: false, plugin_field_key: 'tags' },
            { id: 'attr-cover-item', name: 'Cover item', data_type: 'text', is_required: false, plugin_field_key: 'cover_item_id' },
            { id: 'attr-cover-account', name: 'Cover account', data_type: 'text', is_required: false, plugin_field_key: 'cover_account_id' },
        ],
    };
}

function buildFolderCategory() {
    return {
        id: 'cat-folders',
        name: 'Folders',
        plugin_key: null,
        attributes: [
            { id: 'attr-title', name: 'Title', data_type: 'text', is_required: true },
        ],
    };
}

function buildImageCategory() {
    return {
        id: 'cat-images',
        name: 'Images',
        plugin_key: 'images_core',
        attributes: [
            { id: 'attr-label', name: 'Label', data_type: 'text', is_required: false, plugin_field_key: 'classification_label' },
            { id: 'attr-lat', name: 'GPS latitude', data_type: 'number', is_required: false, plugin_field_key: 'gps_latitude' },
            { id: 'attr-lon', name: 'GPS longitude', data_type: 'number', is_required: false, plugin_field_key: 'gps_longitude' },
        ],
    };
}

describe('MetadataModal component', () => {
    beforeEach(() => {
        categoriesState = [];
        metadataState = null;
        layoutsState = [];
        historyState = [];

        getCategoriesMock.mockReset();
        getItemMetadataMock.mockReset();
        listFormLayoutsMock.mockReset();
        getItemMetadataHistoryMock.mockReset();
        saveItemMetadataMock.mockReset();
        createMetadataUpdateJobMock.mockReset();
        getDownloadContentUrlMock.mockReset();
        showToastMock.mockReset();

        getCategoriesMock.mockImplementation(async () => clone(categoriesState));
        getItemMetadataMock.mockImplementation(async () => clone(metadataState));
        listFormLayoutsMock.mockImplementation(async () => clone(layoutsState));
        getItemMetadataHistoryMock.mockImplementation(async () => clone(historyState));
        saveItemMetadataMock.mockImplementation(async (payload) => payload);
        createMetadataUpdateJobMock.mockImplementation(async () => ({ id: 'job-1' }));
        getDownloadContentUrlMock.mockImplementation(() => 'https://example.test/preview.png');
    });

    it('loads file metadata, renders layout/history, previews the cover and saves during navigation', async () => {
        const user = userEvent.setup();
        const onPrevious = vi.fn();
        const onNext = vi.fn();

        categoriesState = [buildComicCategory()];
        metadataState = {
            category_id: 'cat-comics',
            values: {
                'attr-series': 'Saga',
                'attr-title': 'Issue 1',
                'attr-tags': ['#abc', 'Hero'],
                'attr-cover-item': 'cover-item-1',
                'attr-cover-account': 'cover-acc',
            },
        };
        layoutsState = [
            {
                category_id: 'cat-comics',
                columns: 12,
                row_height: 1,
                hide_read_only_fields: false,
                items: [
                    { item_type: 'section', item_id: 'main', title: 'Overview', x: 0, y: 0, w: 12, h: 1 },
                    { item_type: 'attribute', item_id: 'attr-series', attribute_id: 'attr-series', x: 0, y: 1, w: 6, h: 1 },
                    { item_type: 'attribute', item_id: 'attr-title', attribute_id: 'attr-title', x: 6, y: 1, w: 6, h: 1 },
                    { item_type: 'attribute', item_id: 'attr-tags', attribute_id: 'attr-tags', x: 0, y: 2, w: 12, h: 1 },
                ],
                ordered_attribute_ids: ['attr-series', 'attr-title', 'attr-tags', 'attr-cover-item', 'attr-cover-account'],
                half_width_attribute_ids: ['attr-series', 'attr-title'],
            },
        ];
        historyState = [
            {
                id: 'hist-1',
                action: 'updated',
                batch_id: 'batch-42',
                created_at: '2026-03-10T12:00:00Z',
            },
        ];

        renderWithProviders(
            <MetadataModal
                isOpen
                onClose={vi.fn()}
                item={{ item_id: 'item-1', name: 'Saga #1', item_type: 'file' }}
                accountId="acc-1"
                hasPrevious
                hasNext
                onPrevious={onPrevious}
                onNext={onNext}
            />,
        );

        expect(await screen.findByText(/cover preview/i)).toBeInTheDocument();
        expect(screen.getByText('Overview')).toBeInTheDocument();
        expect(screen.getByText('Hero')).toBeInTheDocument();
        expect(screen.getByText(/Batch: batch-42/i)).toBeInTheDocument();
        await waitFor(() => {
            expect(getDownloadContentUrlMock).toHaveBeenCalledWith(
                'cover-acc',
                'cover-item-1',
                { autoResolveAccount: true },
            );
        });

        await user.click(screen.getByRole('button', { name: /previous/i }));
        expect(onPrevious).toHaveBeenCalledTimes(1);

        await user.click(screen.getByRole('button', { name: /zoom/i }));
        expect(screen.getByText('100%')).toBeInTheDocument();
        fireEvent.keyDown(window, { key: '+' });
        expect(await screen.findByText('125%')).toBeInTheDocument();
        fireEvent.keyDown(window, { key: 'Escape' });
        await waitFor(() => expect(screen.queryByText('125%')).not.toBeInTheDocument());

        const seriesInput = screen.getByDisplayValue('Saga');
        await user.clear(seriesInput);
        await user.type(seriesInput, 'Saga Deluxe');
        await user.click(screen.getByRole('button', { name: /next/i }));

        await waitFor(() => {
            expect(saveItemMetadataMock).toHaveBeenCalledWith({
                account_id: 'acc-1',
                item_id: 'item-1',
                category_id: 'cat-comics',
                values: {
                    'attr-series': 'Saga Deluxe',
                    'attr-title': 'Issue 1',
                    'attr-tags': ['#abc', 'Hero'],
                    'attr-cover-item': 'cover-item-1',
                    'attr-cover-account': 'cover-acc',
                },
            });
        });
        expect(onNext).toHaveBeenCalledTimes(1);
        expect(showToastMock).not.toHaveBeenCalledWith('Metadata saved', 'success');
    });

    it('validates required fields for folders and creates a background job when saving succeeds', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        const onSuccess = vi.fn();

        categoriesState = [buildFolderCategory()];

        renderWithProviders(
            <MetadataModal
                isOpen
                onClose={onClose}
                onSuccess={onSuccess}
                item={{ item_id: 'folder-1', name: 'Library', item_type: 'folder' }}
                accountId="acc-folder"
            />,
        );

        await screen.findByText(/use with care/i);

        await user.selectOptions(screen.getByRole('combobox'), 'cat-folders');
        await user.click(screen.getByRole('button', { name: /^save$/i }));

        expect(showToastMock).toHaveBeenCalledWith('Required fields: Title', 'error');
        expect(createMetadataUpdateJobMock).not.toHaveBeenCalled();

        await user.type(screen.getByRole('textbox'), 'Invoices');
        await user.click(screen.getByRole('button', { name: /^save$/i }));

        await waitFor(() => {
            expect(createMetadataUpdateJobMock).toHaveBeenCalledWith(
                'acc-folder',
                'folder-1',
                { Title: 'Invoices' },
                'Folders',
            );
        });
        expect(showToastMock).toHaveBeenCalledWith('Bulk metadata update job started', 'success');
        expect(onSuccess).toHaveBeenCalledTimes(1);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('renders image preview and location map for image library items', async () => {
        categoriesState = [buildImageCategory()];
        metadataState = {
            category_id: 'cat-images',
            values: {
                'attr-label': 'Sunset',
                'attr-lat': '-23.550520',
                'attr-lon': '-46.633308',
            },
        };

        renderWithProviders(
            <MetadataModal
                isOpen
                onClose={vi.fn()}
                item={{ item_id: 'image-1', name: 'photo.jpg', item_type: 'file' }}
                accountId="acc-image"
            />,
        );

        expect(await screen.findByText(/image preview/i)).toBeInTheDocument();
        expect(screen.getByAltText('photo.jpg')).toBeInTheDocument();
        expect(screen.getByTitle(/location map/i)).toHaveAttribute(
            'src',
            expect.stringContaining('openstreetmap.org/export/embed.html'),
        );
        expect(getDownloadContentUrlMock).toHaveBeenCalledWith(
            'acc-image',
            'image-1',
            { autoResolveAccount: true },
        );
    });

    it('supports wheel zoom and closes the image zoom overlay', async () => {
        const user = userEvent.setup();

        categoriesState = [buildImageCategory()];
        metadataState = {
            category_id: 'cat-images',
            values: {
                'attr-label': 'Sunset',
                'attr-lat': '-23.550520',
                'attr-lon': '-46.633308',
            },
        };

        const { container } = renderWithProviders(
            <MetadataModal
                isOpen
                onClose={vi.fn()}
                item={{ item_id: 'image-2', name: 'poster.jpg', item_type: 'file' }}
                accountId="acc-image"
            />,
        );

        await screen.findByText(/image preview/i);
        await user.click(screen.getByRole('button', { name: /zoom/i }));
        expect(screen.getByText('100%')).toBeInTheDocument();

        const overlay = Array.from(container.querySelectorAll('.layer-overlay')).at(-1);
        const zoomSurface = overlay.querySelector('.flex-1.overflow-auto');
        fireEvent.wheel(zoomSurface, { ctrlKey: true, deltaY: -120 });

        expect(await screen.findByText('110%')).toBeInTheDocument();

        fireEvent.click(overlay);
        await waitFor(() => {
            expect(screen.queryByText('110%')).not.toBeInTheDocument();
        });
    });

    it('shows an error toast when loading metadata fails', async () => {
        getCategoriesMock.mockRejectedValueOnce(new Error('boom'));

        renderWithProviders(
            <MetadataModal
                isOpen
                onClose={vi.fn()}
                item={{ item_id: 'broken-1', name: 'broken.txt', item_type: 'file' }}
                accountId="acc-broken"
            />,
        );

        await waitFor(() => expect(showToastMock).toHaveBeenCalledWith('Failed to load metadata', 'error'));
    });
});
