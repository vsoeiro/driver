function normalizeString(value, fallback = '') {
    if (value === undefined || value === null) return fallback;
    return String(value).trim();
}

function normalizeNullableString(value) {
    const normalized = normalizeString(value);
    return normalized || null;
}

function normalizeNumber(value, fallback) {
    const candidate = Number(value);
    return Number.isFinite(candidate) ? candidate : fallback;
}

function normalizeBoolean(value) {
    return Boolean(value);
}

function normalizeStringArray(values = []) {
    if (!Array.isArray(values)) return [];
    return values
        .map((value) => normalizeString(value))
        .filter(Boolean)
        .sort((left, right) => left.localeCompare(right));
}

export function normalizeDriveListParams(params = {}) {
    return {
        accountId: normalizeString(params.accountId),
        folderId: normalizeNullableString(params.folderId),
        searchQuery: normalizeString(params.searchQuery),
        cursor: normalizeNullableString(params.cursor),
        pageSize: Math.max(1, Math.floor(normalizeNumber(params.pageSize, 50))),
    };
}

export function normalizeItemsListParams(params = {}) {
    return {
        page: Math.max(1, Math.floor(normalizeNumber(params.page, 1))),
        page_size: Math.max(1, Math.floor(normalizeNumber(params.page_size, 50))),
        sort_by: normalizeString(params.sort_by, 'modified_at'),
        sort_order: normalizeString(params.sort_order, 'desc') === 'asc' ? 'asc' : 'desc',
        q: normalizeString(params.q),
        search_fields: normalizeString(params.search_fields, 'both'),
        path_prefix: normalizeString(params.path_prefix),
        direct_children_only: normalizeBoolean(params.direct_children_only),
        extensions: normalizeStringArray(params.extensions),
        size_min: normalizeString(params.size_min),
        size_max: normalizeString(params.size_max),
        item_type: normalizeString(params.item_type),
        account_id: normalizeString(params.account_id),
        category_id: normalizeString(params.category_id),
        has_metadata: normalizeString(params.has_metadata),
    };
}

export function normalizeJobsListParams(params = {}) {
    return {
        page: Math.max(1, Math.floor(normalizeNumber(params.page, 1))),
        pageSize: Math.max(1, Math.floor(normalizeNumber(params.pageSize, 20))),
        statuses: normalizeStringArray(params.statuses),
        types: normalizeStringArray(params.types),
        createdAfter: normalizeNullableString(params.createdAfter),
        includeEstimates: params.includeEstimates !== false,
    };
}

export const queryKeys = {
    accounts: {
        all: () => ['accounts'],
    },
    metadata: {
        categories: () => ['metadata-categories'],
        libraries: () => ['metadata-libraries'],
    },
    observability: {
        detail: (period = '24h') => ['observability', normalizeString(period, '24h')],
    },
    quota: {
        detail: (accountId) => ['quota', normalizeString(accountId)],
    },
    jobs: {
        activity: () => ['jobs', 'activity'],
        list: (params = {}) => ['jobs', 'list', normalizeJobsListParams(params)],
    },
    drive: {
        listRoot: () => ['drive', 'list'],
        list: (params = {}) => ['drive', 'list', normalizeDriveListParams(params)],
        breadcrumbRoot: () => ['drive', 'breadcrumb'],
        breadcrumb: (accountId, folderId) => ['drive', 'breadcrumb', normalizeString(accountId), normalizeNullableString(folderId)],
    },
    items: {
        listRoot: () => ['items', 'list'],
        list: (params = {}) => ['items', 'list', normalizeItemsListParams(params)],
    },
};

export default queryKeys;
