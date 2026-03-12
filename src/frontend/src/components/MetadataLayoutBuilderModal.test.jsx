import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const listFormLayoutsMock = vi.fn();
const saveFormLayoutMock = vi.fn();

vi.mock('../services/metadata', () => ({
    metadataService: {
        listFormLayouts: (...args) => listFormLayoutsMock(...args),
        saveFormLayout: (...args) => saveFormLayoutMock(...args),
    },
}));

import { renderWithProviders } from '../test/render';
import MetadataLayoutBuilderModal from './MetadataLayoutBuilderModal';

const CATEGORIES = [
    {
        id: 'cat-1',
        name: 'Comics',
        plugin_key: 'comics_core',
        attributes: [
            { id: 'attr-1', name: 'Title', data_type: 'text', is_required: false },
            { id: 'attr-2', name: 'Issue', data_type: 'text', is_required: false },
        ],
    },
    {
        id: 'cat-2',
        name: 'Books',
        plugin_key: 'books_core',
        attributes: [
            { id: 'attr-3', name: 'Author', data_type: 'text', is_required: false },
        ],
    },
];

function buildSavedLayout(categoryId, payload) {
    return {
        category_id: categoryId,
        columns: payload.columns,
        row_height: payload.row_height,
        hide_read_only_fields: payload.hide_read_only_fields,
        items: payload.items,
        ordered_attribute_ids: payload.ordered_attribute_ids,
        half_width_attribute_ids: payload.half_width_attribute_ids,
    };
}

describe('MetadataLayoutBuilderModal', () => {
    let rectSpy;

    beforeEach(() => {
        listFormLayoutsMock.mockReset();
        saveFormLayoutMock.mockReset();

        listFormLayoutsMock.mockResolvedValue([
            {
                category_id: 'cat-1',
                columns: 12,
                row_height: 1,
                hide_read_only_fields: false,
                items: [
                    { item_type: 'attribute', attribute_id: 'attr-1', x: 0, y: 0, w: 6, h: 1 },
                    { item_type: 'attribute', attribute_id: 'attr-2', x: 6, y: 0, w: 6, h: 1 },
                ],
                ordered_attribute_ids: ['attr-1', 'attr-2'],
                half_width_attribute_ids: ['attr-1', 'attr-2'],
            },
        ]);
        saveFormLayoutMock.mockImplementation(async (categoryId, payload) => buildSavedLayout(categoryId, payload));

        rectSpy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
            width: 960,
            height: 640,
            top: 0,
            left: 0,
            right: 960,
            bottom: 640,
            x: 0,
            y: 0,
            toJSON: () => ({}),
        });
    });

    afterEach(() => {
        rectSpy.mockRestore();
    });

    it('loads an existing layout, lets the user rearrange it, and saves the updated payload', async () => {
        const user = userEvent.setup();
        const onSaved = vi.fn();

        renderWithProviders(
            <MetadataLayoutBuilderModal
                isOpen
                onClose={vi.fn()}
                categories={CATEGORIES}
                onSaved={onSaved}
            />,
        );

        expect(await screen.findByText(/form layout builder/i)).toBeInTheDocument();
        await waitFor(() => expect(screen.getByRole('button', { name: /add section/i })).toBeEnabled());
        expect(screen.getByText('Title')).toBeInTheDocument();
        expect(screen.getByText('Issue')).toBeInTheDocument();

        const comboBoxes = screen.getAllByRole('combobox');
        await user.selectOptions(comboBoxes[1], '8');
        await user.click(screen.getByRole('checkbox', { name: /hide read-only fields in modal/i }));
        await user.click(screen.getByRole('button', { name: /add section/i }));
        await user.type(screen.getByPlaceholderText(/section title/i), 'Hero section');

        fireEvent.mouseDown(screen.getAllByTitle(/^move$/i)[0], { clientX: 40, clientY: 40 });
        fireEvent.mouseMove(window, { clientX: 280, clientY: 96 });
        fireEvent.mouseUp(window);

        fireEvent.mouseDown(screen.getAllByTitle(/resize width/i)[0], { clientX: 280, clientY: 96 });
        fireEvent.mouseMove(window, { clientX: 520, clientY: 96 });
        fireEvent.mouseUp(window);

        await user.click(screen.getByRole('button', { name: /save layout/i }));

        await waitFor(() => expect(saveFormLayoutMock).toHaveBeenCalledTimes(1));
        const [savedCategoryId, payload] = saveFormLayoutMock.mock.calls[0];
        expect(savedCategoryId).toBe('cat-1');
        expect(payload.columns).toBe(8);
        expect(payload.hide_read_only_fields).toBe(true);
        expect(payload.items.length).toBeGreaterThan(2);
        expect(await screen.findByText(/layout saved/i)).toBeInTheDocument();
        expect(onSaved).toHaveBeenCalledTimes(1);
    }, 15000);

    it('surfaces load failures when the layout data cannot be fetched', async () => {
        listFormLayoutsMock.mockRejectedValueOnce(new Error('load failed'));

        renderWithProviders(
            <MetadataLayoutBuilderModal
                isOpen
                onClose={vi.fn()}
                categories={CATEGORIES}
                onSaved={vi.fn()}
            />,
        );

        expect(await screen.findByText(/failed to load layouts/i)).toBeInTheDocument();
    });

    it('supports reset and section removal, and shows save errors', async () => {
        const user = userEvent.setup();
        saveFormLayoutMock.mockRejectedValueOnce({
            response: { data: { detail: 'save exploded' } },
        });

        renderWithProviders(
            <MetadataLayoutBuilderModal
                isOpen
                onClose={vi.fn()}
                categories={CATEGORIES}
                onSaved={vi.fn()}
            />,
        );

        expect(await screen.findByText(/drag to move, drag the right handle to resize width/i)).toBeInTheDocument();
        await waitFor(() => expect(screen.getByRole('button', { name: /add section/i })).toBeEnabled());

        await user.click(screen.getByRole('button', { name: /add section/i }));
        expect(screen.getByPlaceholderText(/section title/i)).toBeInTheDocument();
        await user.click(screen.getByTitle(/remove section/i));
        expect(screen.queryByPlaceholderText(/section title/i)).not.toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /reset/i }));
        await user.click(screen.getByRole('button', { name: /save layout/i }));

        expect(await screen.findByText('save exploded')).toBeInTheDocument();
    });
});
