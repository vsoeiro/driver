import api from './api';

export const itemsService = {
    /**
     * List items with pagination and filters.
     * @param {Object} params - Query parameters.
     * @param {number} params.page - Page number.
     * @param {number} params.page_size - Items per page.
     * @param {string} params.sort_by - Sort column.
     * @param {string} params.sort_order - Sort order (asc/desc).
     * @param {string} params.q - Search query.
     * @param {string[]} params.extensions - List of extensions.
     * @param {string} params.item_type - file or folder.
     * @param {number} params.size_min - Min size in bytes.
     * @param {number} params.size_max - Max size in bytes.
     * @param {string} params.account_id - Filter by account.
     */
    listItems: async (params) => {
        const queryParams = new URLSearchParams();

        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                if (Array.isArray(value)) {
                    value.forEach(v => queryParams.append(key, v));
                } else if (typeof value === 'object') {
                    queryParams.append(key, JSON.stringify(value));
                } else {
                    queryParams.append(key, value);
                }
            }
        });

        const response = await api.get(`/items?${queryParams.toString()}`);
        return response.data;
    },

    /**
     * Batch update metadata.
     * @param {string} accountId - Account ID.
     * @param {string[]} itemIds - List of item IDs.
     * @param {string} categoryId - Metadata category ID.
     * @param {Object} values - Metadata values.
     */
    batchUpdateMetadata: async (accountId, itemIds, categoryId, values) => {
        const response = await api.post('/items/metadata/batch', {
            account_id: accountId,
            item_ids: itemIds,
            category_id: categoryId,
            values: values
        });
        return response.data;
    }
};
