import {
    normalizeDriveListParams,
    normalizeItemsListParams,
    normalizeJobsListParams,
    queryKeys,
} from './queryKeys';

describe('queryKeys', () => {
    it('normalizes drive params', () => {
        expect(
            normalizeDriveListParams({
                accountId: ' 123 ',
                folderId: '',
                searchQuery: null,
                cursor: ' next ',
                pageSize: '15.9',
            }),
        ).toEqual({
            accountId: '123',
            folderId: null,
            searchQuery: '',
            cursor: 'next',
            pageSize: 15,
        });
    });

    it('normalizes items params with defaults', () => {
        expect(
            normalizeItemsListParams({
                page: 0,
                page_size: '20',
                sort_order: 'ascending',
                extensions: ['cbz', ' pdf ', '', 'cbz'],
                direct_children_only: 'x',
            }),
        ).toEqual(
            expect.objectContaining({
                page: 1,
                page_size: 20,
                sort_by: 'modified_at',
                sort_order: 'desc',
                direct_children_only: true,
                extensions: ['cbz', 'cbz', 'pdf'],
            }),
        );
    });

    it('normalizes jobs params and builds keys', () => {
        expect(normalizeJobsListParams({ pageSize: '7.8', statuses: [' queued ', ''], includeEstimates: false })).toEqual({
            page: 1,
            pageSize: 7,
            statuses: ['queued'],
            types: [],
            createdAfter: null,
            includeEstimates: false,
        });
        expect(queryKeys.drive.breadcrumb(' acc ', ' folder ')).toEqual(['drive', 'breadcrumb', 'acc', 'folder']);
        expect(queryKeys.jobs.list({ statuses: ['done'] })[0]).toBe('jobs');
    });
});
