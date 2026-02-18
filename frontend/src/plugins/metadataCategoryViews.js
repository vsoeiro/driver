export const metadataCategoryViews = {
    comicrack_core: {
        key: 'comicrack_core',
        modes: ['table', 'gallery'],
        gallery: {
            coverField: 'cover_item_id',
            coverAccountField: 'cover_account_id',
            titleField: 'title',
            pageCountField: 'page_count',
            subtitleField: 'series',
            volumeField: 'volume',
            issueNumberField: 'issue_number',
        },
    },
};

export const getCategoryPluginView = (category) => {
    if (!category?.plugin_key) return null;
    return metadataCategoryViews[category.plugin_key] || null;
};
