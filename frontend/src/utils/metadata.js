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

export function sortAttributesForCategory(category, orderedAttributeIds = null) {
    const attrs = Array.isArray(category?.attributes) ? [...category.attributes] : [];
    if (Array.isArray(orderedAttributeIds) && orderedAttributeIds.length > 0) {
        const indexById = new Map(orderedAttributeIds.map((id, index) => [String(id), index]));
        return attrs.sort((a, b) => {
            const aIndex = indexById.has(String(a?.id)) ? indexById.get(String(a?.id)) : Number.MAX_SAFE_INTEGER;
            const bIndex = indexById.has(String(b?.id)) ? indexById.get(String(b?.id)) : Number.MAX_SAFE_INTEGER;
            if (aIndex !== bIndex) return aIndex - bIndex;
            return String(a?.name || '').localeCompare(String(b?.name || ''));
        });
    }
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

function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(value, maximum));
}

function toInt(value, fallback = 0) {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function regionIsFree(occupied, x, y, w) {
    for (let col = x; col < x + w; col += 1) {
        if (occupied.has(`${col}:${y}`)) return false;
    }
    return true;
}

function occupyRegion(occupied, x, y, w) {
    for (let col = x; col < x + w; col += 1) {
        occupied.add(`${col}:${y}`);
    }
}

function findFirstFreeSlot(occupied, columns, width, startY = 0) {
    const startRow = Math.max(0, startY);
    for (let y = startRow; y <= 5000; y += 1) {
        for (let x = 0; x <= Math.max(0, columns - width); x += 1) {
            if (regionIsFree(occupied, x, y, width)) {
                return { x, y };
            }
        }
    }
    return { x: 0, y: 0 };
}

function buildLegacyItems(layout, columns) {
    const ordered = Array.isArray(layout?.ordered_attribute_ids) ? layout.ordered_attribute_ids.map(String) : [];
    const halfSet = new Set(
        Array.isArray(layout?.half_width_attribute_ids)
            ? layout.half_width_attribute_ids.map(String)
            : [],
    );

    const items = [];
    const halfWidth = Math.max(1, Math.floor(columns / 2));
    let x = 0;
    let y = 0;

    ordered.forEach((attributeId) => {
        const w = halfSet.has(attributeId) ? halfWidth : columns;
        if (x + w > columns) {
            y += 1;
            x = 0;
        }
        items.push({
            item_type: 'attribute',
            item_id: attributeId,
            attribute_id: attributeId,
            title: null,
            x,
            y,
            w,
            h: 1,
        });
        if (w >= columns) {
            y += 1;
            x = 0;
        } else {
            x += w;
            if (x >= columns) {
                y += 1;
                x = 0;
            }
        }
    });
    return items;
}

function getLayoutItemType(item) {
    const raw = String(item?.item_type || '').trim().toLowerCase();
    if (raw === 'section') return 'section';
    return item?.attribute_id ? 'attribute' : 'section';
}

function normalizeSectionId(rawValue, index = 0) {
    const raw = String(rawValue || '').trim();
    if (!raw) return `section_${index + 1}`;
    return raw.slice(0, 120);
}

function getLayoutItemKey(item) {
    const itemType = getLayoutItemType(item);
    if (itemType === 'section') {
        return `section:${normalizeSectionId(item?.item_id)}`;
    }
    return `attribute:${String(item?.attribute_id || '')}`;
}

function sanitizeLayoutItems(rawItems, columns, validIds) {
    if (!Array.isArray(rawItems)) return [];

    const seen = new Set();
    const parsed = rawItems
        .map((item, index) => {
            const itemType = getLayoutItemType(item);
            if (itemType === 'section') {
                const item_id = normalizeSectionId(item?.item_id, index);
                const key = `section:${item_id}`;
                if (seen.has(key)) return null;
                seen.add(key);
                const y = Math.max(0, toInt(item?.y, 0));
                const title = String(item?.title || '').trim();
                return {
                    item_type: 'section',
                    item_id,
                    attribute_id: null,
                    title: title ? title.slice(0, 80) : null,
                    x: 0,
                    y,
                    w: columns,
                    h: 1,
                };
            }

            const attributeId = String(item?.attribute_id ?? '');
            const key = `attribute:${attributeId}`;
            if (!attributeId || seen.has(key) || !validIds.has(attributeId)) return null;
            seen.add(key);
            const w = clamp(toInt(item?.w, columns), 1, columns);
            const xRaw = clamp(toInt(item?.x, 0), 0, columns - 1);
            const x = xRaw + w > columns ? Math.max(0, columns - w) : xRaw;
            const y = Math.max(0, toInt(item?.y, 0));
            return {
                item_type: 'attribute',
                item_id: attributeId,
                attribute_id: attributeId,
                title: null,
                x,
                y,
                w,
                h: 1,
            };
        })
        .filter(Boolean);

    parsed.sort((a, b) => (a.y - b.y) || (a.x - b.x));
    return parsed;
}

export function normalizeFormLayoutForCategory(category, layout) {
    const attributes = Array.isArray(category?.attributes) ? category.attributes : [];
    const columns = clamp(toInt(layout?.columns, 12), 1, 24);
    const row_height = clamp(toInt(layout?.row_height, 1), 1, 4);
    const validIds = new Set(attributes.map((attr) => String(attr.id)));
    const defaultOrder = sortAttributesForCategory(category).map((attr) => String(attr.id));

    let candidateItems = sanitizeLayoutItems(layout?.items, columns, validIds);
    if (candidateItems.length === 0) {
        candidateItems = sanitizeLayoutItems(buildLegacyItems(layout, columns), columns, validIds);
    }
    if (candidateItems.length === 0) {
        candidateItems = defaultOrder.map((attributeId, index) => ({
            item_type: 'attribute',
            item_id: attributeId,
            attribute_id: attributeId,
            title: null,
            x: 0,
            y: index,
            w: columns,
            h: 1,
        }));
    }

    const occupied = new Set();
    const normalizedItems = [];
    const seenAttributes = new Set();
    const seenItems = new Set();

    candidateItems.forEach((item) => {
        const itemType = getLayoutItemType(item);
        const itemKey = getLayoutItemKey(item);
        if (seenItems.has(itemKey)) return;
        seenItems.add(itemKey);

        if (itemType === 'section') {
            const item_id = normalizeSectionId(item?.item_id, normalizedItems.length);
            const title = String(item?.title || '').trim();
            let y = Math.max(0, toInt(item.y, 0));
            const width = columns;
            let x = 0;
            if (!regionIsFree(occupied, x, y, width)) {
                const freeSlot = findFirstFreeSlot(occupied, columns, width, y);
                x = freeSlot.x;
                y = freeSlot.y;
            }
            occupyRegion(occupied, x, y, width);
            normalizedItems.push({
                item_type: 'section',
                item_id,
                attribute_id: null,
                title: title ? title.slice(0, 80) : null,
                x,
                y,
                w: width,
                h: 1,
            });
            return;
        }

        const attributeId = String(item.attribute_id);
        if (seenAttributes.has(attributeId) || !validIds.has(attributeId)) return;
        const width = clamp(toInt(item.w, columns), 1, columns);
        let x = clamp(toInt(item.x, 0), 0, columns - 1);
        if (x + width > columns) x = Math.max(0, columns - width);
        let y = Math.max(0, toInt(item.y, 0));
        if (!regionIsFree(occupied, x, y, width)) {
            const freeSlot = findFirstFreeSlot(occupied, columns, width, y);
            x = freeSlot.x;
            y = freeSlot.y;
        }
        occupyRegion(occupied, x, y, width);
        normalizedItems.push({
            item_type: 'attribute',
            item_id: attributeId,
            attribute_id: attributeId,
            title: null,
            x,
            y,
            w: width,
            h: 1,
        });
        seenAttributes.add(attributeId);
    });

    defaultOrder.forEach((attributeId) => {
        if (seenAttributes.has(attributeId)) return;
        const freeSlot = findFirstFreeSlot(occupied, columns, columns, 0);
        occupyRegion(occupied, freeSlot.x, freeSlot.y, columns);
        normalizedItems.push({
            item_type: 'attribute',
            item_id: attributeId,
            attribute_id: attributeId,
            title: null,
            x: freeSlot.x,
            y: freeSlot.y,
            w: columns,
            h: 1,
        });
        seenAttributes.add(attributeId);
    });

    normalizedItems.sort((a, b) => (a.y - b.y) || (a.x - b.x));
    const ordered_attribute_ids = normalizedItems
        .filter((item) => item.item_type === 'attribute')
        .map((item) => item.attribute_id);
    const half_width_attribute_ids = normalizedItems
        .filter((item) => item.item_type === 'attribute' && item.w <= Math.max(1, Math.floor(columns / 2)))
        .map((item) => item.attribute_id);

    return {
        columns,
        row_height,
        items: normalizedItems,
        ordered_attribute_ids,
        half_width_attribute_ids,
    };
}

export function resolveLayoutItemsForRender(items, columnsInput = 12) {
    const columns = clamp(toInt(columnsInput, 12), 1, 24);
    const sourceItems = Array.isArray(items) ? items : [];
    const sorted = sourceItems
        .map((item, index) => ({
            item_type: getLayoutItemType(item),
            item_id: String(item?.item_id || item?.attribute_id || `item_${index + 1}`),
            attribute_id: item?.attribute_id ? String(item.attribute_id) : null,
            title: item?.title || null,
            x: toInt(item?.x, 0),
            y: toInt(item?.y, 0),
            w: toInt(item?.w, columns),
            h: 1,
        }))
        .sort((a, b) => (a.y - b.y) || (a.x - b.x));

    const occupied = new Set();
    const resolved = [];
    const seenKeys = new Set();

    sorted.forEach((item, index) => {
        const itemType = item.item_type;
        const itemKey = itemType === 'section'
            ? `section:${String(item.item_id || `section_${index + 1}`)}`
            : `attribute:${String(item.attribute_id || '')}`;
        if (seenKeys.has(itemKey)) return;
        seenKeys.add(itemKey);

        const width = itemType === 'section'
            ? columns
            : clamp(toInt(item.w, columns), 1, columns);
        let x = itemType === 'section'
            ? 0
            : clamp(toInt(item.x, 0), 0, columns - width);
        let y = Math.max(0, toInt(item.y, 0));

        if (!regionIsFree(occupied, x, y, width)) {
            const freeSlot = findFirstFreeSlot(occupied, columns, width, y);
            x = freeSlot.x;
            y = freeSlot.y;
        }
        occupyRegion(occupied, x, y, width);

        resolved.push({
            ...item,
            x,
            y,
            w: width,
            h: 1,
        });
    });

    return resolved.sort((a, b) => (a.y - b.y) || (a.x - b.x));
}

export function formLayoutToPayload(layout) {
    const columns = clamp(toInt(layout?.columns, 12), 1, 24);
    const row_height = clamp(toInt(layout?.row_height, 1), 1, 4);
    const items = Array.isArray(layout?.items)
        ? layout.items
            .map((item, index) => {
                const itemType = getLayoutItemType(item);
                if (itemType === 'section') {
                    const item_id = normalizeSectionId(item?.item_id, index);
                    const title = String(item?.title || '').trim();
                    return {
                        item_type: 'section',
                        item_id,
                        attribute_id: null,
                        title: title ? title.slice(0, 80) : null,
                        x: 0,
                        y: Math.max(0, toInt(item.y, 0)),
                        w: columns,
                        h: 1,
                    };
                }
                const attribute_id = String(item?.attribute_id || '').trim();
                if (!attribute_id) return null;
                return {
                    item_type: 'attribute',
                    item_id: attribute_id,
                    attribute_id,
                    title: null,
                    x: Math.max(0, toInt(item.x, 0)),
                    y: Math.max(0, toInt(item.y, 0)),
                    w: clamp(toInt(item.w, columns), 1, columns),
                    h: 1,
                };
            })
            .filter(Boolean)
        : [];
    const ordered_attribute_ids = items
        .slice()
        .sort((a, b) => (a.y - b.y) || (a.x - b.x))
        .filter((item) => item.item_type === 'attribute')
        .map((item) => item.attribute_id);
    const half_width_attribute_ids = items
        .filter((item) => item.item_type === 'attribute' && item.w <= Math.max(1, Math.floor(columns / 2)))
        .map((item) => item.attribute_id);

    return {
        columns,
        row_height,
        items,
        ordered_attribute_ids,
        half_width_attribute_ids,
    };
}
