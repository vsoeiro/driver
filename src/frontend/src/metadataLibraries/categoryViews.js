export const metadataCategoryViews = {
    comics_core: {
        key: 'comics_core',
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
        formLayout: {
            groups: [
                ['series', 'title'],
                ['volume', 'issue_number', 'year', 'month'],
                ['max_volumes', 'max_issues', 'series_status'],
                ['publisher', 'imprint'],
                ['writer', 'penciller', 'colorist', 'letterer'],
                ['genre', 'language', 'original_language'],
                ['tags'],
                ['summary'],
            ],
            compactFields: [
                'volume',
                'issue_number',
                'year',
                'month',
                'max_volumes',
                'max_issues',
            ],
        },
    },
    images_core: {
        key: 'images_core',
        modes: ['table', 'gallery'],
        gallery: {
            useItemAsCover: true,
            titleField: 'classification_label',
            subtitleField: 'ocr_text',
        },
    },
    books_core: {
        key: 'books_core',
        modes: ['table', 'gallery'],
        gallery: {
            coverField: 'cover_item_id',
            coverAccountField: 'cover_account_id',
            titleField: 'title',
            subtitleField: 'author',
            pageCountField: 'page_count',
        },
    },
};

export const getCategoryLibraryView = (category) => {
    if (!category?.plugin_key) return null;
    return metadataCategoryViews[category.plugin_key] || null;
};
