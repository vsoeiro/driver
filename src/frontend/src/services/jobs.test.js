vi.mock('./api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        delete: vi.fn(),
    },
}));

import api from './api';
import {
    applyMetadataRecursive,
    cancelJob,
    createAnalyzeImageAssetsJob,
    createAnalyzeLibraryImageAssetsJob,
    createApplyRuleJob,
    createExtractBookAssetsJob,
    createExtractComicAssetsJob,
    createExtractLibraryBookAssetsJob,
    createExtractLibraryComicAssetsJob,
    createExtractZipJob,
    createMapLibraryBooksJob,
    createMetadataUndoJob,
    createMetadataUpdateJob,
    createMoveJob,
    createRemoveDuplicatesJob,
    createReindexComicCoversJob,
    createSyncJob,
    deleteJob,
    getJobAttempts,
    getJobs,
    reprocessJob,
    removeMetadataRecursive,
} from './jobs';

describe('jobs service', () => {
    it('creates jobs and normalizes job filters', async () => {
        api.post.mockResolvedValue({ data: { id: 'job-1' } });
        api.get.mockResolvedValue({ data: { jobs: [] } });

        await createMoveJob('src', 'item', 'dest');
        await createExtractZipJob('src', 'zip-1', 'dest', 'folder-9', true);
        await getJobs('7.9', '-1', [' queued ', 'done'], { types: ['SYNC_ITEMS ', ''], createdAfter: ' 2026-03-10 ' }, { includeEstimates: false, signal: 'signal' });

        expect(api.post).toHaveBeenNthCalledWith(1, '/jobs/move', {
            source_account_id: 'src',
            source_item_id: 'item',
            destination_account_id: 'dest',
            destination_folder_id: 'root',
        });
        expect(api.post).toHaveBeenNthCalledWith(2, '/jobs/zip/extract', {
            source_account_id: 'src',
            source_item_id: 'zip-1',
            destination_account_id: 'dest',
            destination_folder_id: 'folder-9',
            delete_source_after_extract: true,
        });
        expect(api.get).toHaveBeenCalledWith('/jobs/', {
            params: {
                limit: 7,
                offset: 0,
                include_estimates: false,
                status: 'QUEUED,DONE',
                type: 'sync_items',
                created_after: '2026-03-10',
            },
            signal: 'signal',
        });
    });

    it('calls simple job actions', async () => {
        api.post.mockResolvedValue({ data: { ok: true } });
        api.delete.mockResolvedValue({});
        api.get.mockResolvedValue({ data: { attempts: [] } });

        await cancelJob('job-1');
        await reprocessJob('job-1');
        await getJobAttempts('job-1', '8.5');
        await deleteJob('job-1');
        await createMetadataUpdateJob('acc-1', 'root-1', { title: 'Dylan' }, 'Comics');
        await applyMetadataRecursive('acc-1', '/Comics', 'cat-1', { series: 'Dylan' }, true);
        await removeMetadataRecursive('acc-1', '/Comics');
        await createSyncJob('acc-1');
        await createMetadataUndoJob('batch-1');
        await createApplyRuleJob('rule-1');
        await createExtractComicAssetsJob('acc-1', ['i1']);
        await createExtractBookAssetsJob('acc-1', ['i1']);
        await createAnalyzeImageAssetsJob('acc-1', ['i1'], false, true);
        await createAnalyzeLibraryImageAssetsJob(['acc-1'], 100, true);
        await createReindexComicCoversJob();
        await createReindexComicCoversJob('books_core', 100);
        await createExtractLibraryComicAssetsJob(['acc-1'], 10);
        await createMapLibraryBooksJob(['acc-1'], 11);
        await createExtractLibraryBookAssetsJob(null, 12);
        await createRemoveDuplicatesJob({ account_id: 'acc-1' });

        expect(api.get).toHaveBeenCalledWith('/jobs/job-1/attempts', { params: { limit: 8 } });
        expect(api.delete).toHaveBeenCalledWith('/jobs/job-1');
        expect(api.post).toHaveBeenCalledWith('/jobs/images/analyze-library', {
            account_ids: ['acc-1'],
            chunk_size: 100,
            reprocess: true,
        });
        expect(api.post).toHaveBeenCalledWith('/jobs/books/extract-library', { chunk_size: 12 });
        expect(api.post).toHaveBeenCalledWith('/jobs/comics/reindex-covers', { library_key: 'comics_core', chunk_size: 250 });
        expect(api.post).toHaveBeenCalledWith('/jobs/comics/reindex-covers', { library_key: 'books_core', chunk_size: 100 });
        expect(api.post).toHaveBeenCalledWith('/jobs/remove-duplicates', { account_id: 'acc-1' });
    });
});
