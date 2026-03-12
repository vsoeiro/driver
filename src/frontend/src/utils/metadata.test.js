import {
    READ_ONLY_LIBRARY_ASSET_FIELD_KEYS,
    formLayoutToPayload,
    getSelectOptions,
    normalizeFormLayoutForCategory,
    normalizeTagsValue,
    parseTagsInput,
    resolveLayoutItemsForRender,
    sortAttributesForCategory,
    tagsToInputValue,
} from './metadata';

describe('metadata utils', () => {
    it('extracts select options from mixed values', () => {
        expect(getSelectOptions({ options: [' A ', { value: 'B' }, { label: 'C ' }, null] })).toEqual(['A', 'B', 'C']);
        expect(getSelectOptions({ options: 'invalid' })).toEqual([]);
    });

    it('sorts attributes by explicit order and comic plugin order', () => {
        const attrs = [
            { id: '3', name: 'Writer', plugin_field_key: 'writer' },
            { id: '2', name: 'Title', plugin_field_key: 'title' },
            { id: '1', name: 'Series', plugin_field_key: 'series' },
        ];

        expect(sortAttributesForCategory({ attributes: attrs }, ['2', '1'])).toEqual([
            attrs[1],
            attrs[0].id === '1' ? attrs[0] : attrs[2],
            attrs[0].id === '3' ? attrs[0] : attrs[2],
        ]);
        expect(sortAttributesForCategory({ attributes: attrs, plugin_key: 'comics_core' }).map((item) => item.id)).toEqual(['1', '2', '3']);
        expect(READ_ONLY_LIBRARY_ASSET_FIELD_KEYS.has('cover_item_id')).toBe(true);
    });

    it('normalizes tags consistently', () => {
        expect(parseTagsInput(' Horror, horror, Mystery ,, Drama ')).toEqual(['Horror', 'Mystery', 'Drama']);
        expect(normalizeTagsValue([' Horror ', 'horror', '', 'Drama'])).toEqual(['Horror', 'Drama']);
        expect(normalizeTagsValue('Sci-Fi, Fantasy')).toEqual(['Sci-Fi', 'Fantasy']);
        expect(tagsToInputValue(['Sci-Fi', 'Fantasy'])).toBe('Sci-Fi, Fantasy');
    });

    it('normalizes form layout using legacy fields and fills missing attributes', () => {
        const category = {
            plugin_key: 'comics_core',
            attributes: [
                { id: 'series', name: 'Series', plugin_field_key: 'series' },
                { id: 'title', name: 'Title', plugin_field_key: 'title' },
                { id: 'writer', name: 'Writer', plugin_field_key: 'writer' },
            ],
        };

        const normalized = normalizeFormLayoutForCategory(category, {
            columns: 2,
            row_height: 5,
            ordered_attribute_ids: ['title'],
            half_width_attribute_ids: ['title'],
            items: [
                { item_type: 'section', item_id: 'overview', title: 'Overview', y: 0 },
                { attribute_id: 'title', x: 0, y: 1, w: 1 },
                { attribute_id: 'title', x: 1, y: 1, w: 1 },
            ],
        });

        expect(normalized.columns).toBe(2);
        expect(normalized.row_height).toBe(4);
        expect(normalized.items[0]).toEqual(expect.objectContaining({ item_type: 'section', item_id: 'overview', w: 2 }));
        expect(normalized.ordered_attribute_ids).toEqual(['title', 'series', 'writer']);
        expect(normalized.half_width_attribute_ids).toEqual(['title']);
    });

    it('resolves render collisions and serializes layout payload', () => {
        const resolved = resolveLayoutItemsForRender(
            [
                { item_type: 'section', item_id: 'intro', title: 'Intro', y: 0 },
                { attribute_id: 'series', x: 0, y: 0, w: 2 },
                { attribute_id: 'title', x: 0, y: 0, w: 2 },
                { attribute_id: 'title', x: 0, y: 1, w: 2 },
            ],
            2,
        );

        expect(resolved[0]).toEqual(expect.objectContaining({ item_type: 'section', x: 0, y: 0, w: 2 }));
        expect(resolved[1]).toEqual(expect.objectContaining({ attribute_id: 'series', y: 1 }));
        expect(resolved[2]).toEqual(expect.objectContaining({ attribute_id: 'title', y: 2 }));

        expect(
            formLayoutToPayload({
                columns: 2,
                row_height: 2,
                hide_read_only_fields: true,
                items: [
                    { item_type: 'section', item_id: 'intro', title: ' Intro ', y: 0 },
                    { attribute_id: 'series', x: 1, y: 1, w: 1 },
                ],
            }),
        ).toEqual({
            columns: 2,
            row_height: 2,
            hide_read_only_fields: true,
            items: [
                { item_type: 'section', item_id: 'intro', attribute_id: null, title: 'Intro', x: 0, y: 0, w: 2, h: 1 },
                { item_type: 'attribute', item_id: 'series', attribute_id: 'series', title: null, x: 1, y: 1, w: 1, h: 1 },
            ],
            ordered_attribute_ids: ['series'],
            half_width_attribute_ids: ['series'],
        });
    });
});
