import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const listCategoriesMock = vi.fn();
const listFormLayoutsMock = vi.fn();
const batchUpdateMetadataMock = vi.fn();
const applyMetadataRecursiveMock = vi.fn();
const getDownloadContentUrlMock = vi.fn();

vi.mock('../services/metadata', () => ({
    metadataService: {
        listCategories: (...args) => listCategoriesMock(...args),
        listFormLayouts: (...args) => listFormLayoutsMock(...args),
    },
}));

vi.mock('../services/items', () => ({
    itemsService: {
        batchUpdateMetadata: (...args) => batchUpdateMetadataMock(...args),
    },
}));

vi.mock('../services/jobs', () => ({
    jobsService: {
        applyMetadataRecursive: (...args) => applyMetadataRecursiveMock(...args),
    },
}));

vi.mock('../services/drive', () => ({
    driveService: {
        getDownloadContentUrl: (...args) => getDownloadContentUrlMock(...args),
    },
}));

import { renderWithProviders } from '../test/render';
import BatchMetadataModal from './BatchMetadataModal';

const CATEGORY = {
    id: 'cat-1',
    name: 'Comics',
    plugin_key: 'comics_core',
    attributes: [
        { id: 'attr-title', name: 'Title', data_type: 'text', is_required: false },
        { id: 'attr-state', name: 'Status', data_type: 'select', is_required: false, options: { options: ['Draft', 'Published'] } },
        { id: 'attr-cover', name: 'Cover item', data_type: 'text', is_required: false, plugin_field_key: 'cover_item_id' },
        { id: 'attr-cover-account', name: 'Cover account', data_type: 'text', is_required: false, plugin_field_key: 'cover_account_id' },
    ],
};

function renderModal(props) {
    return renderWithProviders(
        <BatchMetadataModal
            isOpen
            onClose={vi.fn()}
            onSuccess={vi.fn()}
            showToast={vi.fn()}
            selectedItems={[]}
            {...props}
        />,
    );
}

describe('BatchMetadataModal', () => {
    beforeEach(() => {
        listCategoriesMock.mockReset();
        listFormLayoutsMock.mockReset();
        batchUpdateMetadataMock.mockReset();
        applyMetadataRecursiveMock.mockReset();
        getDownloadContentUrlMock.mockReset();

        listCategoriesMock.mockResolvedValue([CATEGORY]);
        listFormLayoutsMock.mockResolvedValue([
            {
                category_id: 'cat-1',
                columns: 12,
                row_height: 1,
                hide_read_only_fields: false,
                items: [
                    { item_type: 'section', item_id: 'hero', title: 'Main fields', x: 0, y: 0, w: 12, h: 1 },
                    { item_type: 'attribute', attribute_id: 'attr-title', x: 0, y: 1, w: 6, h: 1 },
                    { item_type: 'attribute', attribute_id: 'attr-state', x: 6, y: 1, w: 6, h: 1 },
                ],
                ordered_attribute_ids: ['attr-title', 'attr-state'],
                half_width_attribute_ids: ['attr-title', 'attr-state'],
            },
        ]);
        batchUpdateMetadataMock.mockResolvedValue(undefined);
        applyMetadataRecursiveMock.mockResolvedValue(undefined);
        getDownloadContentUrlMock.mockReturnValue('https://cdn.example.test/cover.jpg');
    });

    it('prefills a single item selection, renders the cover preview, and saves updated metadata', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        const onSuccess = vi.fn();
        const showToast = vi.fn();

        renderModal({
            onClose,
            onSuccess,
            showToast,
            selectedItems: [
                {
                    account_id: 'acc-1',
                    item_id: 'item-1',
                    item_type: 'file',
                    name: 'Issue 001.cbz',
                    metadata: {
                        category_id: 'cat-1',
                        values: {
                            'attr-title': 'Issue 001',
                            'attr-state': 'Draft',
                            'attr-cover': 'cover-42',
                            'attr-cover-account': 'acc-1',
                        },
                    },
                },
            ],
        });

        const textInputs = await screen.findAllByRole('textbox');
        expect(screen.getByText('Main fields')).toBeInTheDocument();
        expect(await screen.findByAltText('Issue 001.cbz')).toHaveAttribute('src', 'https://cdn.example.test/cover.jpg');

        await user.clear(textInputs[0]);
        await user.type(textInputs[0], 'Issue 001 Deluxe');
        await user.selectOptions(screen.getAllByRole('combobox')[1], 'Published');
        await user.click(screen.getByRole('button', { name: /save changes/i }));

        await waitFor(() => {
            expect(batchUpdateMetadataMock).toHaveBeenCalledWith(
                'acc-1',
                ['item-1'],
                'cat-1',
                expect.objectContaining({
                    'attr-title': 'Issue 001 Deluxe',
                    'attr-state': 'Published',
                    'attr-cover': 'cover-42',
                    'attr-cover-account': 'acc-1',
                }),
            );
        });
        expect(applyMetadataRecursiveMock).not.toHaveBeenCalled();
        expect(showToast).toHaveBeenCalledWith('Metadata updated', 'success');
        expect(onSuccess).toHaveBeenCalledTimes(1);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('groups files by account, queues recursive folder jobs, and reports the recursive job count', async () => {
        const user = userEvent.setup();
        const showToast = vi.fn();

        renderModal({
            showToast,
            selectedItems: [
                { account_id: 'acc-1', item_id: 'file-1', item_type: 'file', name: 'Issue 002.cbz' },
                { account_id: 'acc-1', item_id: 'folder-1', item_type: 'folder', path: '/Series' },
                { account_id: 'acc-2', item_id: 'folder-2', item_type: 'folder', path: '/Archive' },
            ],
        });

        expect(await screen.findByText(/select category/i)).toBeInTheDocument();
        await user.selectOptions(screen.getAllByRole('combobox')[0], 'cat-1');
        await user.type((await screen.findAllByRole('textbox'))[0], 'Batch title');
        await user.click(screen.getByRole('checkbox', { name: /apply recursively to folders/i }));
        await user.click(screen.getByRole('button', { name: /save changes/i }));

        await waitFor(() => expect(batchUpdateMetadataMock).toHaveBeenCalledTimes(1));
        expect(batchUpdateMetadataMock).toHaveBeenCalledWith(
            'acc-1',
            ['file-1'],
            'cat-1',
            expect.objectContaining({ 'attr-title': 'Batch title' }),
        );
        expect(applyMetadataRecursiveMock).toHaveBeenCalledTimes(2);
        expect(applyMetadataRecursiveMock).toHaveBeenNthCalledWith(
            1,
            'acc-1',
            '/Series',
            'cat-1',
            expect.objectContaining({ 'attr-title': 'Batch title' }),
        );
        expect(applyMetadataRecursiveMock).toHaveBeenNthCalledWith(
            2,
            'acc-2',
            '/Archive',
            'cat-1',
            expect.objectContaining({ 'attr-title': 'Batch title' }),
        );
        expect(showToast).toHaveBeenCalledWith('Created 2 recursive metadata job(s)', 'success');
    });

    it('surfaces save failures from the metadata update requests', async () => {
        const user = userEvent.setup();
        const showToast = vi.fn();
        batchUpdateMetadataMock.mockRejectedValueOnce(new Error('backend exploded'));

        renderModal({
            showToast,
            selectedItems: [
                { account_id: 'acc-1', item_id: 'file-1', item_type: 'file', name: 'Issue 003.cbz' },
            ],
        });

        expect(await screen.findByText(/select category/i)).toBeInTheDocument();
        await user.selectOptions(screen.getAllByRole('combobox')[0], 'cat-1');
        await user.type((await screen.findAllByRole('textbox'))[0], 'Broken save');
        await user.click(screen.getByRole('button', { name: /save changes/i }));

        await waitFor(() => {
            expect(showToast).toHaveBeenCalledWith(
                'Failed to update metadata: backend exploded',
                'error',
            );
        });
    });
});
