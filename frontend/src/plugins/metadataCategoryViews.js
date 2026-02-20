export const metadataCategoryViews = {
    comicrack_core: {
        key: 'comicrack_core',
        modes: ['table', 'gallery', 'series_tracker'],
        gallery: {
            coverField: 'cover_item_id',
            coverAccountField: 'cover_account_id',
            titleField: 'title',
            pageCountField: 'page_count',
            subtitleField: 'series',
            volumeField: 'volume',
            issueNumberField: 'issue_number',
        },
        seriesTracker: {
            seriesField: 'series',
            volumeField: 'volume',
            issueNumberField: 'issue_number',
            maxVolumesField: 'max_volumes',
            maxIssuesField: 'max_issues',
            statusField: 'series_status',
        },
    },
};

export const getCategoryPluginView = (category) => {
    if (!category?.plugin_key) return null;
    return metadataCategoryViews[category.plugin_key] || null;
};
