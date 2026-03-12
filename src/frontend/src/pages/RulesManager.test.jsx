import userEvent from '@testing-library/user-event';
import { screen, waitFor } from '@testing-library/react';

const listRulesMock = vi.fn();
const listCategoriesMock = vi.fn();
const createRuleMock = vi.fn();
const previewRuleMock = vi.fn();
const deleteRuleMock = vi.fn();
const getAccountsMock = vi.fn();
const getFilesMock = vi.fn();
const getFolderFilesMock = vi.fn();
const createFolderMock = vi.fn();
const getPathMock = vi.fn();
const createApplyRuleJobMock = vi.fn();
const showToastMock = vi.fn();

vi.mock('../services/metadata', () => ({
    metadataService: {
        listRules: (...args) => listRulesMock(...args),
        listCategories: (...args) => listCategoriesMock(...args),
        createRule: (...args) => createRuleMock(...args),
        previewRule: (...args) => previewRuleMock(...args),
        deleteRule: (...args) => deleteRuleMock(...args),
    },
}));

vi.mock('../services/accounts', () => ({
    accountsService: {
        getAccounts: (...args) => getAccountsMock(...args),
    },
}));

vi.mock('../services/drive', () => ({
    getFiles: (...args) => getFilesMock(...args),
    getFolderFiles: (...args) => getFolderFilesMock(...args),
    createFolder: (...args) => createFolderMock(...args),
    getPath: (...args) => getPathMock(...args),
}));

vi.mock('../services/jobs', () => ({
    jobsService: {
        createApplyRuleJob: (...args) => createApplyRuleJobMock(...args),
    },
}));

vi.mock('../contexts/ToastContext', () => ({
    ToastProvider: ({ children }) => children,
    useToast: () => ({ showToast: showToastMock }),
}));

import { renderWithProviders } from '../test/render';
import RulesManager from './RulesManager';

const category = {
    id: 'cat-1',
    name: 'Comics',
    attributes: [
        {
            id: 'attr-1',
            name: 'Title',
            data_type: 'text',
            options: null,
            plugin_field_key: 'title',
        },
        {
            id: 'attr-2',
            name: 'Volume',
            data_type: 'number',
            options: null,
            plugin_field_key: 'volume',
        },
        {
            id: 'attr-3',
            name: 'Read',
            data_type: 'boolean',
            options: null,
            plugin_field_key: 'read',
        },
        {
            id: 'attr-4',
            name: 'Tags',
            data_type: 'tags',
            options: null,
            plugin_field_key: 'tags',
        },
        {
            id: 'attr-5',
            name: 'Language',
            data_type: 'select',
            options: ['en', 'pt-BR'],
            plugin_field_key: 'language',
        },
    ],
};

const account = {
    id: 'acc-1',
    email: 'reader@example.com',
};

const existingRule = {
    id: 'rule-1',
    name: 'Normalize series',
    description: 'Rename and move comics',
    account_id: 'acc-1',
    target_category_id: 'cat-1',
    target_values: { 'attr-1': 'Saga' },
    apply_metadata: true,
    apply_remove_metadata: false,
    apply_rename: true,
    rename_template: '{{TITLE}}',
    apply_move: true,
    destination_account_id: 'acc-1',
    destination_folder_id: 'folder-1',
    destination_path_template: '{{TITLE}}',
    metadata_filters: [],
    include_folders: false,
    path_prefix: null,
    path_contains: null,
};

describe('RulesManager page', () => {
    beforeEach(() => {
        showToastMock.mockReset();
        listRulesMock.mockReset();
        listCategoriesMock.mockReset();
        createRuleMock.mockReset();
        previewRuleMock.mockReset();
        deleteRuleMock.mockReset();
        getAccountsMock.mockReset();
        getFilesMock.mockReset();
        getFolderFilesMock.mockReset();
        createFolderMock.mockReset();
        getPathMock.mockReset();
        createApplyRuleJobMock.mockReset();

        listRulesMock.mockResolvedValue([]);
        listCategoriesMock.mockResolvedValue([category]);
        createRuleMock.mockResolvedValue({ id: 'rule-created' });
        previewRuleMock.mockResolvedValue({
            total_matches: 4,
            to_change: 2,
            already_compliant: 2,
        });
        deleteRuleMock.mockResolvedValue(undefined);
        getAccountsMock.mockResolvedValue([account]);
        getFilesMock.mockResolvedValue({
            items: [{ id: 'folder-1', name: 'Series', item_type: 'folder' }],
        });
        getFolderFilesMock.mockResolvedValue({ items: [] });
        createFolderMock.mockResolvedValue({ id: 'folder-2', name: 'New Folder' });
        getPathMock.mockResolvedValue({
            breadcrumb: [
                { id: 'root', name: 'root' },
                { id: 'folder-1', name: 'Series' },
            ],
        });
        createApplyRuleJobMock.mockResolvedValue({ id: 'job-1' });
    });

    it('renders the empty state after loading rules data', async () => {
        renderWithProviders(<RulesManager />);

        expect(await screen.findByText(/rules/i)).toBeInTheDocument();
        expect(await screen.findByText(/no rules yet/i)).toBeInTheDocument();
        expect(screen.getByText(/create your first rule above/i)).toBeInTheDocument();
    });

    it('previews and creates a new rule from the form', async () => {
        const user = userEvent.setup();
        renderWithProviders(<RulesManager />);

        await screen.findByText(/no rules yet/i);

        await user.type(screen.getByPlaceholderText(/rule name/i), 'Match Saga');
        await user.selectOptions(screen.getAllByRole('combobox')[1], 'cat-1');
        await user.type(screen.getByPlaceholderText(/set title \(optional\)/i), 'Saga');

        await user.click(screen.getByRole('button', { name: /^preview$/i }));

        await waitFor(() => {
            expect(previewRuleMock).toHaveBeenCalledWith(
                expect.objectContaining({
                    target_category_id: 'cat-1',
                    target_values: { 'attr-1': 'Saga' },
                    apply_metadata: true,
                }),
            );
        });
        expect(screen.getByText(/4 matches, 2 to change, 2 already compliant/i)).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /create rule/i }));

        await waitFor(() => {
            expect(createRuleMock).toHaveBeenCalledWith(
                expect.objectContaining({
                    name: 'Match Saga',
                    target_category_id: 'cat-1',
                    target_values: { 'attr-1': 'Saga' },
                    apply_metadata: true,
                }),
            );
        });
        expect(showToastMock).toHaveBeenCalledWith('Rule created successfully', 'success');
    });

    it('previews, applies and deletes an existing rule', async () => {
        const user = userEvent.setup();
        listRulesMock.mockResolvedValue([existingRule]);

        const { container } = renderWithProviders(<RulesManager />);

        expect(await screen.findByText('Normalize series')).toBeInTheDocument();
        expect(await screen.findByText(/move item: \/series \/ \{\{title\}\}/i)).toBeInTheDocument();

        await user.click(container.querySelector('button[title="Preview"]'));

        await waitFor(() => {
            expect(previewRuleMock).toHaveBeenCalledWith(
                expect.objectContaining({
                    target_category_id: 'cat-1',
                    rename_template: '{{TITLE}}',
                    destination_folder_id: 'folder-1',
                }),
            );
        });
        expect(screen.getByText(/4 matches, 2 to change, 2 already compliant/i)).toBeInTheDocument();

        await user.click(container.querySelector('button[title="Apply rule"]'));
        await waitFor(() => expect(createApplyRuleJobMock).toHaveBeenCalledWith('rule-1'));

        await user.click(container.querySelector('button[title="Delete rule"]'));
        await waitFor(() => expect(deleteRuleMock).toHaveBeenCalledWith('rule-1'));
    });

    it('normalizes metadata filters and typed values when creating a rule', async () => {
        const user = userEvent.setup();
        renderWithProviders(<RulesManager />);

        await screen.findByText(/no rules yet/i);

        await user.type(screen.getByPlaceholderText(/rule name/i), 'Rich rule');
        await user.selectOptions(screen.getAllByRole('combobox')[1], 'cat-1');

        await user.click(screen.getByRole('button', { name: /add filter/i }));
        const filterSelects = screen.getAllByRole('combobox');
        await user.selectOptions(filterSelects[2], 'attr-3');
        await user.selectOptions(filterSelects[3], 'equals');
        await user.selectOptions(screen.getByDisplayValue(/yes/i), 'false');

        await user.type(screen.getByPlaceholderText(/set title \(optional\)/i), 'Saga');
        await user.type(screen.getByPlaceholderText(/set volume \(optional\)/i), '12');
        await user.selectOptions(screen.getAllByDisplayValue(/ignore/i)[0], 'true');
        await user.type(screen.getByPlaceholderText(/set tags/i), 'heroic, remaster');

        await user.click(screen.getByRole('button', { name: /create rule/i }));

        await waitFor(() => {
            expect(createRuleMock).toHaveBeenCalledWith(
                expect.objectContaining({
                    name: 'Rich rule',
                    apply_move: false,
                    target_values: {
                        'attr-1': 'Saga',
                        'attr-2': 12,
                        'attr-3': true,
                        'attr-4': ['heroicremaster'],
                    },
                    metadata_filters: [
                        {
                            source: 'metadata',
                            attribute_id: 'attr-3',
                            operator: 'equals',
                            value: false,
                        },
                    ],
                }),
            );
        });
    }, 15000);
});
