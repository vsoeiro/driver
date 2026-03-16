import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const getCategoryStatsMock = vi.fn();
const listMetadataLibrariesMock = vi.fn();
const activateMetadataLibraryMock = vi.fn();
const deactivateMetadataLibraryMock = vi.fn();
const createCategoryMock = vi.fn();
const deleteCategoryMock = vi.fn();
const createAttributeMock = vi.fn();
const updateAttributeMock = vi.fn();
const deleteAttributeMock = vi.fn();
const getSeriesSummaryMock = vi.fn();
const getCategoryDashboardMock = vi.fn();
const updateItemMetadataFieldMock = vi.fn();
const listItemsMock = vi.fn();
const getAccountsMock = vi.fn();
const getDownloadContentUrlMock = vi.fn();
const getDownloadUrlMock = vi.fn();
const batchDeleteItemsMock = vi.fn();
const updateItemMock = vi.fn();
const showToastMock = vi.fn();

let categoriesState = [];
let librariesState = [];
let itemsState = [];
let seriesRowsState = [];
let dashboardState = null;
let accountsState = [];

function clone(value) {
    return JSON.parse(JSON.stringify(value));
}

function buildCategory(overrides = {}) {
    return {
        id: 'cat-1',
        name: 'Comics',
        description: 'Comic metadata',
        item_count: 4,
        is_locked: false,
        managed_by_plugin: false,
        plugin_key: null,
        attributes: [],
        ...overrides,
    };
}

function buildAttribute(overrides = {}) {
    return {
        id: 'attr-1',
        name: 'Genre',
        data_type: 'select',
        is_required: false,
        is_locked: false,
        managed_by_plugin: false,
        plugin_key: null,
        plugin_field_key: null,
        options: { options: ['Sci-Fi', 'Fantasy'] },
        ...overrides,
    };
}

function buildItem(overrides = {}) {
    return {
        id: 'row-1',
        item_id: 'item-1',
        account_id: 'acc-1',
        name: 'Comic One.cbz',
        item_type: 'file',
        size: 1024,
        path: '/Comics/Comic One.cbz',
        modified_at: '2026-03-10T12:00:00Z',
        metadata: {
            version: 1,
            values: {},
        },
        ...overrides,
    };
}

vi.mock('../services/metadata', () => ({
    metadataService: {
        getCategoryStats: (...args) => getCategoryStatsMock(...args),
        listMetadataLibraries: (...args) => listMetadataLibrariesMock(...args),
        activateMetadataLibrary: (...args) => activateMetadataLibraryMock(...args),
        deactivateMetadataLibrary: (...args) => deactivateMetadataLibraryMock(...args),
        createCategory: (...args) => createCategoryMock(...args),
        deleteCategory: (...args) => deleteCategoryMock(...args),
        createAttribute: (...args) => createAttributeMock(...args),
        updateAttribute: (...args) => updateAttributeMock(...args),
        deleteAttribute: (...args) => deleteAttributeMock(...args),
        getSeriesSummary: (...args) => getSeriesSummaryMock(...args),
        getCategoryDashboard: (...args) => getCategoryDashboardMock(...args),
        updateItemMetadataField: (...args) => updateItemMetadataFieldMock(...args),
    },
}));

vi.mock('../services/items', () => ({
    itemsService: {
        listItems: (...args) => listItemsMock(...args),
    },
}));

vi.mock('../services/accounts', () => ({
    accountsService: {
        getAccounts: (...args) => getAccountsMock(...args),
    },
}));

vi.mock('../services/drive', () => ({
    driveService: {
        getDownloadContentUrl: (...args) => getDownloadContentUrlMock(...args),
        getDownloadUrl: (...args) => getDownloadUrlMock(...args),
        batchDeleteItems: (...args) => batchDeleteItemsMock(...args),
        updateItem: (...args) => updateItemMock(...args),
    },
}));

vi.mock('../contexts/ToastContext', () => ({
    ToastProvider: ({ children }) => children,
    useToast: () => ({ showToast: showToastMock }),
}));

vi.mock('../components/MetadataLayoutBuilderModal', () => ({
    default: ({ isOpen, onClose, categories }) => (
        isOpen ? (
            <div role="dialog" aria-label="Layout Builder">
                <div>Layout Builder</div>
                <div>{categories.length} categories loaded</div>
                <button type="button" onClick={onClose}>Close layout builder</button>
            </div>
        ) : null
    ),
}));

vi.mock('../components/BatchMetadataModal', () => ({ default: () => null }));
vi.mock('../components/RemoveMetadataModal', () => ({ default: () => null }));
vi.mock('../components/MetadataModal', () => ({ default: () => null }));
vi.mock('../components/MoveModal', () => ({ default: () => null }));

import { renderWithProviders } from '../test/render';
import MetadataManager from './MetadataManager';

describe('MetadataManager page', () => {
    beforeEach(() => {
        categoriesState = [];
        librariesState = [
            { key: 'comics_core', name: 'Comics', description: 'Comic metadata', is_active: false },
            { key: 'images_core', name: 'Images', description: 'Image metadata', is_active: true },
        ];
        itemsState = [];
        seriesRowsState = [];
        dashboardState = {
            total_items: 0,
            average_coverage: 0,
            fields_with_gaps: 0,
            cards: [],
        };
        accountsState = [
            { id: 'acc-1', email: 'reader@example.com', display_name: 'Reader' },
            { id: 'acc-2', email: 'second@example.com', display_name: 'Second' },
        ];

        getCategoryStatsMock.mockReset();
        listMetadataLibrariesMock.mockReset();
        activateMetadataLibraryMock.mockReset();
        deactivateMetadataLibraryMock.mockReset();
        createCategoryMock.mockReset();
        deleteCategoryMock.mockReset();
        createAttributeMock.mockReset();
        updateAttributeMock.mockReset();
        deleteAttributeMock.mockReset();
        getSeriesSummaryMock.mockReset();
        getCategoryDashboardMock.mockReset();
        updateItemMetadataFieldMock.mockReset();
        listItemsMock.mockReset();
        getAccountsMock.mockReset();
        getDownloadContentUrlMock.mockReset();
        getDownloadUrlMock.mockReset();
        batchDeleteItemsMock.mockReset();
        updateItemMock.mockReset();
        showToastMock.mockReset();

        getCategoryStatsMock.mockImplementation(async () => clone(categoriesState));
        listMetadataLibrariesMock.mockImplementation(async () => clone(librariesState));
        activateMetadataLibraryMock.mockImplementation(async (libraryKey) => {
            librariesState = librariesState.map((library) => (
                library.key === libraryKey ? { ...library, is_active: true } : library
            ));
            return { key: libraryKey };
        });
        deactivateMetadataLibraryMock.mockImplementation(async (libraryKey) => {
            librariesState = librariesState.map((library) => (
                library.key === libraryKey ? { ...library, is_active: false } : library
            ));
            return { key: libraryKey };
        });
        createCategoryMock.mockImplementation(async (name, description) => {
            const created = buildCategory({
                id: `cat-${categoriesState.length + 1}`,
                name,
                description,
                item_count: 0,
            });
            categoriesState = [...categoriesState, created];
            return created;
        });
        deleteCategoryMock.mockImplementation(async (categoryId) => {
            categoriesState = categoriesState.filter((category) => category.id !== categoryId);
        });
        createAttributeMock.mockImplementation(async (categoryId, payload) => {
            const created = buildAttribute({
                id: `attr-${Date.now()}`,
                name: payload.name,
                data_type: payload.data_type,
                is_required: payload.is_required,
                options: payload.options,
            });
            categoriesState = categoriesState.map((category) => (
                category.id === categoryId
                    ? { ...category, attributes: [...category.attributes, created] }
                    : category
            ));
            return created;
        });
        updateAttributeMock.mockImplementation(async (attributeId, payload) => {
            categoriesState = categoriesState.map((category) => ({
                ...category,
                attributes: category.attributes.map((attribute) => (
                    attribute.id === attributeId
                        ? { ...attribute, name: payload.name, data_type: payload.data_type, is_required: payload.is_required, options: payload.options }
                        : attribute
                )),
            }));
            return { id: attributeId };
        });
        deleteAttributeMock.mockImplementation(async (attributeId) => {
            categoriesState = categoriesState.map((category) => ({
                ...category,
                attributes: category.attributes.filter((attribute) => attribute.id !== attributeId),
            }));
        });
        getSeriesSummaryMock.mockImplementation(async () => ({
            rows: clone(seriesRowsState),
            total: seriesRowsState.length,
            total_pages: 1,
        }));
        getCategoryDashboardMock.mockImplementation(async () => clone(dashboardState));
        updateItemMetadataFieldMock.mockImplementation(async (accountId, itemId, attributeId, payload) => {
            let nextMetadata = null;
            itemsState = itemsState.map((item) => {
                if (item.account_id !== accountId || item.item_id !== itemId) return item;
                nextMetadata = {
                    version: (item.metadata?.version || 0) + 1,
                    values: {
                        ...(item.metadata?.values || {}),
                        [attributeId]: payload.value,
                    },
                };
                return { ...item, metadata: nextMetadata };
            });
            return clone(nextMetadata);
        });
        listItemsMock.mockImplementation(async (params = {}) => {
            let filtered = [...itemsState];
            if (params.account_id) filtered = filtered.filter((item) => item.account_id === params.account_id);
            if (params.metadata) {
                Object.entries(params.metadata).forEach(([attrId, config]) => {
                    if (config && typeof config === 'object' && config.value) {
                        filtered = filtered.filter((item) => item.metadata?.values?.[attrId] === config.value);
                    }
                });
            }
            return clone({ items: filtered, total: filtered.length, total_pages: 1 });
        });
        getAccountsMock.mockImplementation(async () => clone(accountsState));
        getDownloadContentUrlMock.mockImplementation((accountId, itemId) => `https://cdn.example/${accountId}/${itemId}`);
        getDownloadUrlMock.mockResolvedValue('https://download.example/file.cbz');
        batchDeleteItemsMock.mockImplementation(async (accountId, itemIds) => {
            itemsState = itemsState.filter((item) => !(item.account_id === accountId && itemIds.includes(item.item_id)));
        });
        updateItemMock.mockImplementation(async (accountId, itemId, payload) => {
            itemsState = itemsState.map((item) => (
                item.account_id === accountId && item.item_id === itemId
                    ? { ...item, name: payload.name }
                    : item
            ));
            return { id: itemId };
        });
    });

    it('renders the empty metadata state with the layout builder action disabled', async () => {
        renderWithProviders(<MetadataManager />);

        expect(await screen.findByText(/no categories defined/i)).toBeInTheDocument();
        expect(screen.getByText(/create a category to start organizing your file metadata/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /form layout/i })).toBeDisabled();
    });

    it('creates and deletes categories through the page actions', async () => {
        const user = userEvent.setup();

        renderWithProviders(<MetadataManager />);

        await screen.findByText(/no categories defined/i);
        await user.click(screen.getByRole('button', { name: /new category/i }));
        await user.type(screen.getByPlaceholderText(/contracts/i), 'Contracts');
        await user.type(screen.getByPlaceholderText(/optional description/i), 'Business files');
        await user.click(screen.getByRole('button', { name: /^create$/i }));

        await waitFor(() => expect(createCategoryMock).toHaveBeenCalledWith('Contracts', 'Business files'));
        expect(showToastMock).toHaveBeenCalledWith('Category created successfully', 'success');
        expect(await screen.findByText('Contracts')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /form layout/i }));
        expect(screen.getByRole('dialog', { name: /layout builder/i })).toBeInTheDocument();
        expect(screen.getByText(/1 categories loaded/i)).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /close layout builder/i }));

        await user.click(screen.getByTitle(/delete category/i));
        expect(screen.getByText(/are you sure you want to delete/i)).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /^delete$/i }));

        await waitFor(() => expect(deleteCategoryMock).toHaveBeenCalledWith('cat-1'));
        expect(showToastMock).toHaveBeenCalledWith('Category deleted', 'success');
        expect(await screen.findByText(/no categories defined/i)).toBeInTheDocument();
    }, 15000);

    it('enables and disables metadata libraries', async () => {
        const user = userEvent.setup();
        categoriesState = [buildCategory()];

        renderWithProviders(<MetadataManager />);

        await screen.findByText('Comics');
        await user.click(screen.getByRole('button', { name: /libraries/i }));

        expect(await screen.findByText(/metadata libraries/i)).toBeInTheDocument();
        const comicsCard = screen.getByText('Comics').closest('div.rounded-xl');
        const imagesCard = screen.getByText('Images').closest('div.rounded-xl');

        await user.click(within(comicsCard).getByRole('button', { name: /enable/i }));
        await waitFor(() => expect(activateMetadataLibraryMock).toHaveBeenCalledWith('comics_core'));
        expect(showToastMock).toHaveBeenCalledWith('Comics enabled', 'success');

        await user.click(within(imagesCard).getByRole('button', { name: /disable/i }));
        await waitFor(() => expect(deactivateMetadataLibraryMock).toHaveBeenCalledWith('images_core'));
        expect(showToastMock).toHaveBeenCalledWith('Images disabled', 'success');
    });

    it('adds, edits and deletes attributes inside an expanded category', async () => {
        const user = userEvent.setup();
        categoriesState = [buildCategory()];

        renderWithProviders(<MetadataManager />);

        await screen.findByText('Comics');
        await user.click(screen.getByText('Comics'));
        expect(await screen.findByText(/no attributes defined yet/i)).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /add attribute/i }));
        await user.type(screen.getByPlaceholderText(/contract number/i), 'Genre');
        await user.selectOptions(screen.getByRole('combobox'), 'select');
        await user.type(screen.getByPlaceholderText(/option a, option b, option c/i), 'Sci-Fi, Fantasy');
        await user.click(screen.getAllByRole('button', { name: /add attribute/i })[1]);

        await waitFor(() => {
            expect(createAttributeMock).toHaveBeenCalledWith('cat-1', {
                name: 'Genre',
                data_type: 'select',
                is_required: false,
                options: { options: ['Sci-Fi', 'Fantasy'] },
            });
        });
        expect(showToastMock).toHaveBeenCalledWith('Attribute added', 'success');
        expect(await screen.findByText('Genre')).toBeInTheDocument();
        expect(screen.getByText(/options: sci-fi, fantasy/i)).toBeInTheDocument();

        await user.click(screen.getByTitle(/edit attribute/i));
        const nameInputs = screen.getAllByDisplayValue('Genre');
        await user.clear(nameInputs[nameInputs.length - 1]);
        await user.type(nameInputs[nameInputs.length - 1], 'Series');
        await user.click(screen.getByRole('button', { name: /save changes/i }));

        await waitFor(() => {
            expect(updateAttributeMock).toHaveBeenCalledWith(expect.any(String), {
                name: 'Series',
                data_type: 'select',
                is_required: false,
                options: { options: ['Sci-Fi', 'Fantasy'] },
            });
        });
        expect(showToastMock).toHaveBeenCalledWith('Attribute updated', 'success');
        expect(await screen.findByText('Series')).toBeInTheDocument();

        await user.click(screen.getByTitle(/delete attribute/i));
        expect(screen.getByText(/delete this attribute/i)).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /^delete$/i }));

        await waitFor(() => expect(deleteAttributeMock).toHaveBeenCalled());
        expect(showToastMock).toHaveBeenCalledWith('Attribute deleted', 'success');
        expect(await screen.findByText(/no attributes defined yet/i)).toBeInTheDocument();
    }, 15000);

    it('renders category items in gallery and series tracker modes', async () => {
        const user = userEvent.setup();
        categoriesState = [buildCategory({
            plugin_key: 'comics_core',
            attributes: [
                buildAttribute({ id: 'attr-title', name: 'Title', data_type: 'text', plugin_key: 'comics_core', plugin_field_key: 'title', options: null }),
                buildAttribute({ id: 'attr-series', name: 'Series', data_type: 'text', plugin_key: 'comics_core', plugin_field_key: 'series', options: null }),
                buildAttribute({ id: 'attr-page-count', name: 'Pages', data_type: 'number', plugin_key: 'comics_core', plugin_field_key: 'page_count', options: null }),
                buildAttribute({ id: 'attr-volume', name: 'Volume', data_type: 'number', plugin_key: 'comics_core', plugin_field_key: 'volume', options: null }),
                buildAttribute({ id: 'attr-issue', name: 'Issue', data_type: 'number', plugin_key: 'comics_core', plugin_field_key: 'issue_number', options: null }),
                buildAttribute({ id: 'attr-cover-item', name: 'Cover Item', data_type: 'text', plugin_key: 'comics_core', plugin_field_key: 'cover_item_id', options: null }),
                buildAttribute({ id: 'attr-cover-account', name: 'Cover Account', data_type: 'text', plugin_key: 'comics_core', plugin_field_key: 'cover_account_id', options: null }),
                buildAttribute({ id: 'attr-genre', name: 'Genre', data_type: 'select', options: { options: ['Sci-Fi', 'Drama'] } }),
            ],
        })];
        itemsState = [
            buildItem({
                metadata: {
                    version: 1,
                    values: {
                        'attr-title': 'Comic One',
                        'attr-series': 'Saga',
                        'attr-page-count': 24,
                        'attr-volume': 1,
                        'attr-issue': 2,
                        'attr-cover-item': 'cover-1',
                        'attr-cover-account': 'acc-1',
                        'attr-genre': 'Sci-Fi',
                    },
                },
            }),
            buildItem({
                id: 'row-2',
                item_id: 'item-2',
                name: 'Comic Two.cbz',
                metadata: {
                    version: 2,
                    values: {
                        'attr-title': 'Comic Two',
                        'attr-series': 'Saga',
                        'attr-page-count': 22,
                        'attr-volume': 1,
                        'attr-issue': 3,
                        'attr-cover-item': 'cover-2',
                        'attr-cover-account': 'acc-1',
                        'attr-genre': 'Drama',
                    },
                },
            }),
        ];
        seriesRowsState = [{
            series_name: 'Saga',
            total_items: 2,
            owned_volumes: [1],
            issues_by_volume: { '1': [2, 3] },
            max_volumes: 3,
            max_issues: 5,
            duplicate_items_count: 1,
            duplicate_issue_entries: [{ volume: 1, issue: 2, copies: 2 }],
            owned_issues_count: 2,
            series_status: 'ongoing',
        }];

        renderWithProviders(<MetadataManager />);

        await screen.findByText('Comics');
        await user.click(screen.getByTitle(/view items in this category/i));

        expect(await screen.findByText('Comic One.cbz')).toBeInTheDocument();
        await waitFor(() => {
            expect(listItemsMock).toHaveBeenCalledWith(expect.objectContaining({
                category_id: 'cat-1',
                has_metadata: true,
                page: 1,
                page_size: 50,
            }));
        });

        await user.click(screen.getByRole('button', { name: /gallery/i }));
        expect(await screen.findByAltText('Comic One')).toBeInTheDocument();
        await waitFor(() => {
            expect(getDownloadContentUrlMock).toHaveBeenCalledWith('acc-1', 'cover-1', { autoResolveAccount: true });
        });

        await user.click(screen.getByRole('button', { name: /series/i }));
        expect((await within(screen.getByRole('main')).findAllByText('Saga')).length).toBeGreaterThan(0);
        expect(await screen.findByText(/duplicate/i)).toBeInTheDocument();
        await waitFor(() => {
            expect(getSeriesSummaryMock).toHaveBeenCalledWith('cat-1', expect.objectContaining({
                page: 1,
                page_size: 50,
                sort_by: 'series',
            }));
        });
    }, 15000);

    it('renders a metadata dashboard with smart summaries for the current category', async () => {
        const user = userEvent.setup();
        categoriesState = [buildCategory({
            attributes: [
                buildAttribute({ id: 'attr-title', name: 'Title', data_type: 'text', options: null }),
                buildAttribute({ id: 'attr-genre', name: 'Genre', data_type: 'select', options: { options: ['Sci-Fi', 'Drama', 'Fantasy'] } }),
                buildAttribute({ id: 'attr-pages', name: 'Pages', data_type: 'number', options: null }),
                buildAttribute({ id: 'attr-read', name: 'Read', data_type: 'boolean', options: null }),
                buildAttribute({ id: 'attr-tags', name: 'Tags', data_type: 'tags', options: null }),
                buildAttribute({ id: 'attr-release', name: 'Release Date', data_type: 'date', options: null }),
                buildAttribute({ id: 'attr-cover-item', name: 'Cover Item ID', data_type: 'text', plugin_key: 'comics_core', plugin_field_key: 'cover_item_id', options: null }),
            ],
        })];
        itemsState = [
            buildItem({
                metadata: {
                    version: 1,
                    values: {
                        'attr-genre': 'Sci-Fi',
                        'attr-pages': 24,
                        'attr-read': true,
                        'attr-tags': ['space', 'award'],
                        'attr-release': '2026-01-02',
                    },
                },
            }),
            buildItem({
                id: 'row-2',
                item_id: 'item-2',
                name: 'Comic Two.cbz',
                metadata: {
                    version: 1,
                    values: {
                        'attr-genre': 'Drama',
                        'attr-pages': 30,
                        'attr-read': false,
                        'attr-tags': ['space'],
                        'attr-release': '2026-02-10',
                    },
                },
            }),
            buildItem({
                id: 'row-3',
                item_id: 'item-3',
                name: 'Comic Three.cbz',
                metadata: {
                    version: 1,
                    values: {
                        'attr-genre': 'Sci-Fi',
                        'attr-pages': 30,
                        'attr-read': true,
                        'attr-tags': ['award'],
                        'attr-release': '2026-02-18',
                    },
                },
            }),
        ];
        dashboardState = {
            total_items: 3,
            average_coverage: 100,
            fields_with_gaps: 0,
            cards: [
                {
                    attribute_id: 'attr-title',
                    name: 'Title',
                    data_type: 'text',
                    chart_type: 'count',
                    filled_count: 18,
                    fill_rate: 100,
                    distinct_count: 18,
                    stats: [],
                    points: Array.from({ length: 10 }, (_, index) => ({
                        key: `title-${index + 1}`,
                        label: `Title ${String(index + 1).padStart(2, '0')}`,
                        count: 18 - index,
                        value: `Title ${String(index + 1).padStart(2, '0')}`,
                    })),
                },
                {
                    attribute_id: 'attr-genre',
                    name: 'Genre',
                    data_type: 'select',
                    chart_type: 'count',
                    filled_count: 3,
                    fill_rate: 100,
                    distinct_count: 2,
                    stats: [],
                    points: [
                        { key: 'Sci-Fi', label: 'Sci-Fi', count: 2, value: 'Sci-Fi' },
                        { key: 'Drama', label: 'Drama', count: 1, value: 'Drama' },
                    ],
                },
                {
                    attribute_id: 'attr-pages',
                    name: 'Pages',
                    data_type: 'number',
                    chart_type: 'histogram',
                    filled_count: 3,
                    fill_rate: 100,
                    distinct_count: 2,
                    stats: [
                        { key: 'min', value: '24' },
                        { key: 'max', value: '30' },
                        { key: 'average', value: '28' },
                    ],
                    points: [
                        { key: '0', label: '24 to 27', count: 1, range_start: 24, range_end: 27 },
                        { key: '1', label: '27 to 30', count: 2, range_start: 27, range_end: 30 },
                    ],
                },
                {
                    attribute_id: 'attr-read',
                    name: 'Read',
                    data_type: 'boolean',
                    chart_type: 'pie',
                    filled_count: 3,
                    fill_rate: 100,
                    distinct_count: 2,
                    stats: [],
                    points: [
                        { key: 'true', label: 'true', count: 2, value: 'true' },
                        { key: 'false', label: 'false', count: 1, value: 'false' },
                    ],
                },
                {
                    attribute_id: 'attr-tags',
                    name: 'Tags',
                    data_type: 'tags',
                    chart_type: 'count',
                    filled_count: 3,
                    fill_rate: 100,
                    distinct_count: 2,
                    stats: [],
                    points: [
                        { key: 'space', label: 'space', count: 2, value: 'space' },
                        { key: 'award', label: 'award', count: 2, value: 'award' },
                    ],
                },
                {
                    attribute_id: 'attr-release',
                    name: 'Release Date',
                    data_type: 'date',
                    chart_type: 'count',
                    filled_count: 3,
                    fill_rate: 100,
                    distinct_count: 3,
                    stats: [
                        { key: 'earliest', value: '2026-01-02T00:00:00+00:00' },
                        { key: 'latest', value: '2026-02-18T00:00:00+00:00' },
                    ],
                    points: [
                        { key: '2026-01', label: '2026-01', count: 1, value: '2026-01' },
                        { key: '2026-02', label: '2026-02', count: 2, value: '2026-02' },
                    ],
                },
            ],
        };

        renderWithProviders(<MetadataManager />);

        await screen.findByText('Comics');
        await user.click(screen.getByRole('button', { name: /view metadata dashboard/i }));

        const dashboard = await screen.findByRole('region', { name: /metadata dashboard/i });
        expect(within(dashboard).getByText('Items in scope')).toBeInTheDocument();
        expect(within(dashboard).getByText('Average coverage')).toBeInTheDocument();
        expect(within(dashboard).getByText('6 field(s) tracked')).toBeInTheDocument();
        expect(within(dashboard).getByText('Title')).toBeInTheDocument();
        expect(within(dashboard).getByText('Genre')).toBeInTheDocument();
        expect(within(dashboard).getByText('Pages')).toBeInTheDocument();
        expect(within(dashboard).getByText('Release Date')).toBeInTheDocument();
        expect(within(dashboard).getByText('Sci-Fi')).toBeInTheDocument();
        expect(within(dashboard).getByText('space')).toBeInTheDocument();
        expect(within(dashboard).getByText('Showing top 10 values.')).toBeInTheDocument();
        expect(within(dashboard).getByLabelText(/boolean value distribution/i)).toBeInTheDocument();
        expect(within(dashboard).getAllByLabelText(/horizontal value distribution bar chart/i).length).toBeGreaterThan(0);
        expect(within(dashboard).getAllByLabelText(/value distribution bar chart/i).length).toBeGreaterThan(0);
        expect(within(dashboard).getByText('24 to 27')).toBeInTheDocument();
        expect(within(dashboard).queryByText('Cover Item ID')).not.toBeInTheDocument();
        await waitFor(() => expect(getCategoryDashboardMock).toHaveBeenCalledWith('cat-1'));
        expect(listItemsMock).not.toHaveBeenCalled();

        await user.click(screen.getByRole('button', { name: /view items in this category/i }));
        expect(await screen.findByText('Comic One.cbz')).toBeInTheDocument();
        expect(screen.queryByRole('region', { name: /metadata dashboard/i })).not.toBeInTheDocument();
    }, 15000);

    it('filters, renames, downloads, deletes and edits metadata from the category table', async () => {
        const user = userEvent.setup();
        const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
        categoriesState = [buildCategory({
            plugin_key: 'comics_core',
            attributes: [
                buildAttribute({ id: 'attr-title', name: 'Title', data_type: 'text', plugin_key: 'comics_core', plugin_field_key: 'title', options: null }),
                buildAttribute({ id: 'attr-genre', name: 'Genre', data_type: 'select', options: { options: ['Sci-Fi', 'Drama'] } }),
            ],
        })];
        itemsState = [
            buildItem({ metadata: { version: 1, values: { 'attr-title': 'Comic One', 'attr-genre': 'Sci-Fi' } } }),
            buildItem({
                id: 'row-2',
                item_id: 'item-2',
                name: 'Comic Two.cbz',
                metadata: { version: 1, values: { 'attr-title': 'Comic Two', 'attr-genre': 'Drama' } },
            }),
        ];

        renderWithProviders(<MetadataManager />);

        await screen.findByText('Comics');
        await user.click(screen.getByTitle(/view items in this category/i));
        expect(await screen.findByText('Comic One.cbz')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /filters/i }));
        const filterPanel = screen.getByRole('button', { name: /apply/i }).closest('div.menu-popover');
        const filterCombos = within(filterPanel).getAllByRole('combobox');
        const accountSelect = filterCombos.find((select) => Array.from(select.options).some((option) => option.value === 'acc-1'));
        const valueSelect = filterCombos.find((select) => Array.from(select.options).some((option) => option.value === 'Sci-Fi'));
        await user.selectOptions(accountSelect, 'acc-1');
        await user.selectOptions(valueSelect, 'Sci-Fi');
        await user.click(within(filterPanel).getByRole('button', { name: /apply/i }));
        await waitFor(() => {
            expect(listItemsMock).toHaveBeenLastCalledWith(expect.objectContaining({
                account_id: 'acc-1',
                metadata: expect.objectContaining({
                    'attr-genre': expect.objectContaining({ value: 'Sci-Fi' }),
                }),
            }));
        });

        fireEvent.click(screen.getByText('Comic One.cbz'));
        await user.click(screen.getByTitle(/download/i));
        await waitFor(() => expect(getDownloadUrlMock).toHaveBeenCalledWith('acc-1', 'item-1'));
        expect(openSpy).toHaveBeenCalledWith('https://download.example/file.cbz', '_blank');

        const metadataMenuTrigger = screen.getByTitle(/metadata actions/i);
        fireEvent.mouseEnter(metadataMenuTrigger.parentElement);
        await user.click(await screen.findByRole('button', { name: /^rename$/i }));
        const renameInput = screen.getAllByRole('textbox').find((input) => input.value === 'Comic One.cbz');
        await user.clear(renameInput);
        await user.type(renameInput, 'Renamed Comic.cbz');
        await user.click(screen.getAllByRole('button', { name: /^rename$/i }).at(-1));
        await waitFor(() => expect(updateItemMock).toHaveBeenCalledWith('acc-1', 'item-1', { name: 'Renamed Comic.cbz' }));
        expect(showToastMock).toHaveBeenCalledWith('Renamed successfully', 'success');
        expect(await screen.findByText('Renamed Comic.cbz')).toBeInTheDocument();

        await user.click(within(screen.getByRole('main')).getByText('Sci-Fi'));
        const genreEditors = screen.getAllByRole('combobox');
        const inlineEditor = genreEditors[genreEditors.length - 1];
        await user.selectOptions(inlineEditor, 'Drama');
        fireEvent.blur(inlineEditor);
        await waitFor(() => {
            expect(updateItemMetadataFieldMock).toHaveBeenCalledWith(
                'acc-1',
                'item-1',
                'attr-genre',
                { value: 'Drama', category_id: 'cat-1', expected_version: 1 },
            );
        });
        expect(await screen.findByText('Drama')).toBeInTheDocument();

        fireEvent.click(screen.getByText('Renamed Comic.cbz'));
        await user.click(screen.getByTitle(/delete/i));
        await user.click(screen.getAllByRole('button', { name: /^delete$/i })[1]);
        await waitFor(() => expect(batchDeleteItemsMock).toHaveBeenCalledWith('acc-1', ['item-1']));
        expect(showToastMock).toHaveBeenCalledWith('Selected items deleted', 'success');
        openSpy.mockRestore();
    }, 20000);
});
