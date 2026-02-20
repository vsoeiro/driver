export function getSelectOptions(attrOptions) {
    const options = attrOptions?.options;
    if (!Array.isArray(options)) return [];

    return options
        .map((opt) => {
            if (typeof opt === 'string') return opt.trim();
            if (opt && typeof opt === 'object') {
                return String(opt.value ?? opt.label ?? '').trim();
            }
            return String(opt ?? '').trim();
        })
        .filter(Boolean);
}

export const READ_ONLY_COMIC_FIELD_KEYS = new Set([
    'cover_item_id',
    'cover_filename',
    'cover_account_id',
    'page_count',
    'file_format',
]);

const COMIC_FIELD_ORDER = [
    'series',
    'volume',
    'issue_number',
    'max_volumes',
    'max_issues',
    'series_status',
    'title',
    'year',
    'month',
    'publisher',
    'imprint',
    'writer',
    'penciller',
    'colorist',
    'letterer',
    'genre',
    'language',
    'original_language',
    'tags',
    'summary',
    // Read-only fields should always stay at the end.
    'cover_item_id',
    'cover_account_id',
    'cover_filename',
    'page_count',
    'file_format',
];

const COMIC_ORDER_INDEX = new Map(COMIC_FIELD_ORDER.map((key, index) => [key, index]));

export function sortAttributesForCategory(category) {
    const attrs = Array.isArray(category?.attributes) ? [...category.attributes] : [];
    const isComic = category?.plugin_key === 'comicrack_core';
    if (!isComic) {
        return attrs.sort((a, b) => String(a?.name || '').localeCompare(String(b?.name || '')));
    }

    return attrs.sort((a, b) => {
        const aKey = a?.plugin_field_key || '';
        const bKey = b?.plugin_field_key || '';
        const aIndex = COMIC_ORDER_INDEX.has(aKey) ? COMIC_ORDER_INDEX.get(aKey) : Number.MAX_SAFE_INTEGER;
        const bIndex = COMIC_ORDER_INDEX.has(bKey) ? COMIC_ORDER_INDEX.get(bKey) : Number.MAX_SAFE_INTEGER;
        if (aIndex !== bIndex) return aIndex - bIndex;
        return String(a?.name || '').localeCompare(String(b?.name || ''));
    });
}

export function normalizeTagsValue(value) {
    if (value === null || value === undefined || value === '') return [];
    if (Array.isArray(value)) {
        const seen = new Set();
        const tags = [];
        value.forEach((entry) => {
            const tag = String(entry ?? '').trim();
            if (!tag) return;
            const key = tag.toLowerCase();
            if (seen.has(key)) return;
            seen.add(key);
            tags.push(tag);
        });
        return tags;
    }
    return parseTagsInput(String(value));
}

export function parseTagsInput(input) {
    const text = String(input || '');
    if (!text.trim()) return [];
    const seen = new Set();
    const tags = [];
    text
        .split(',')
        .map((entry) => entry.trim())
        .filter(Boolean)
        .forEach((tag) => {
            const key = tag.toLowerCase();
            if (seen.has(key)) return;
            seen.add(key);
            tags.push(tag);
        });
    return tags;
}

export function tagsToInputValue(value) {
    return normalizeTagsValue(value).join(', ');
}
