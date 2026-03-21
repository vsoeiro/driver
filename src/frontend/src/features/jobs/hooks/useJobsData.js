import { useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { normalizeJobsListParams, queryKeys } from '../../../lib/queryKeys';
import { jobsService } from '../../../services/jobs';

export function useJobsListQuery(params = {}, options = {}) {
    const normalizedParams = normalizeJobsListParams(params);
    const { page, pageSize, statuses, types, createdAfter, includeEstimates } = normalizedParams;
    const offset = (page - 1) * pageSize;
    const queryKey = queryKeys.jobs.list(normalizedParams);
    const queryClient = useQueryClient();

    const query = useQuery({
        queryKey,
        queryFn: ({ signal }) => jobsService.getJobs(
            pageSize,
            offset,
            statuses,
            { types, createdAfter },
            { includeEstimates, signal },
        ),
        ...options,
    });

    const setJobsData = useCallback((updater) => {
        queryClient.setQueryData(queryKey, (prev = []) => updater(Array.isArray(prev) ? prev : []));
    }, [queryClient, queryKey]);

    const patchJobs = useCallback((jobIds, patch) => {
        const targetIds = new Set(Array.isArray(jobIds) ? jobIds : [jobIds]);
        setJobsData((prev) => prev.map((job) => {
            if (!targetIds.has(job.id)) return job;
            const resolvedPatch = typeof patch === 'function' ? patch(job) : patch;
            return { ...job, ...resolvedPatch };
        }));
    }, [setJobsData]);

    const removeJobs = useCallback((jobIds) => {
        const targetIds = new Set(Array.isArray(jobIds) ? jobIds : [jobIds]);
        setJobsData((prev) => prev.filter((job) => !targetIds.has(job.id)));
    }, [setJobsData]);

    return useMemo(() => ({
        ...query,
        queryKey,
        setJobsData,
        patchJobs,
        removeJobs,
    }), [patchJobs, query, queryKey, removeJobs, setJobsData]);
}

export function useJobActivityQuery(options = {}) {
    return useQuery({
        queryKey: queryKeys.jobs.activity(),
        queryFn: ({ signal }) => jobsService.getJobs(50, 0, [], {}, { includeEstimates: false, signal }),
        staleTime: 5000,
        ...options,
    });
}

export function useJobsActions() {
    const createMoveJob = useCallback((sourceAccountId, sourceItemId, destinationAccountId, destinationFolderId = 'root') => (
        jobsService.createMoveJob(sourceAccountId, sourceItemId, destinationAccountId, destinationFolderId)
    ), []);
    const createExtractZipJob = useCallback(
        (sourceAccountId, sourceItemId, destinationAccountId, destinationFolderId = 'root', deleteSourceAfterExtract = false) => (
            jobsService.createExtractZipJob(
                sourceAccountId,
                sourceItemId,
                destinationAccountId,
                destinationFolderId,
                deleteSourceAfterExtract,
            )
        ),
        [],
    );
    const getJobs = useCallback((limit = 50, offset = 0, statuses = [], filters = {}, options = {}) => (
        jobsService.getJobs(limit, offset, statuses, filters, options)
    ), []);
    const deleteJob = useCallback((jobId) => jobsService.deleteJob(jobId), []);
    const cancelJob = useCallback((jobId) => jobsService.cancelJob(jobId), []);
    const reprocessJob = useCallback((jobId) => jobsService.reprocessJob(jobId), []);
    const getJobAttempts = useCallback((jobId, limit = 20) => jobsService.getJobAttempts(jobId, limit), []);
    const uploadFileBackground = useCallback((accountId, folderId, file, onProgress) => (
        jobsService.uploadFileBackground(accountId, folderId, file, onProgress)
    ), []);
    const createMetadataUpdateJob = useCallback(
        (accountId, rootItemId, metadata, categoryName) => jobsService.createMetadataUpdateJob(accountId, rootItemId, metadata, categoryName),
        [],
    );
    const applyMetadataRecursive = useCallback(
        (accountId, pathPrefix, categoryId, values = {}, includeFolders = false) => (
            jobsService.applyMetadataRecursive(accountId, pathPrefix, categoryId, values, includeFolders)
        ),
        [],
    );
    const removeMetadataRecursive = useCallback((accountId, pathPrefix) => jobsService.removeMetadataRecursive(accountId, pathPrefix), []);
    const createSyncJob = useCallback((accountId) => jobsService.createSyncJob(accountId), []);
    const createMetadataUndoJob = useCallback((batchId) => jobsService.createMetadataUndoJob(batchId), []);
    const createApplyRuleJob = useCallback((ruleId) => jobsService.createApplyRuleJob(ruleId), []);
    const createExtractComicAssetsJob = useCallback((accountId, itemIds) => jobsService.createExtractComicAssetsJob(accountId, itemIds), []);
    const createExtractBookAssetsJob = useCallback((accountId, itemIds) => jobsService.createExtractBookAssetsJob(accountId, itemIds), []);
    const createAnalyzeImageAssetsJob = useCallback(
        (accountId, itemIds, useIndexedItems = true, reprocess = false) => jobsService.createAnalyzeImageAssetsJob(accountId, itemIds, useIndexedItems, reprocess),
        [],
    );
    const createAnalyzeLibraryImageAssetsJob = useCallback(
        (accountIds = null, chunkSize = 500, reprocess = false) => jobsService.createAnalyzeLibraryImageAssetsJob(accountIds, chunkSize, reprocess),
        [],
    );
    const createReindexComicCoversJob = useCallback(
        (libraryKey = 'comics_core', chunkSize = 250) => jobsService.createReindexComicCoversJob(libraryKey, chunkSize),
        [],
    );
    const createExtractLibraryComicAssetsJob = useCallback(
        (accountIds = null, chunkSize = 1000) => jobsService.createExtractLibraryComicAssetsJob(accountIds, chunkSize),
        [],
    );
    const createMapLibraryBooksJob = useCallback(
        (accountIds = null, chunkSize = 500) => jobsService.createMapLibraryBooksJob(accountIds, chunkSize),
        [],
    );
    const createExtractLibraryBookAssetsJob = useCallback(
        (accountIds = null, chunkSize = 500) => jobsService.createExtractLibraryBookAssetsJob(accountIds, chunkSize),
        [],
    );
    const createRemoveDuplicatesJob = useCallback((payload) => jobsService.createRemoveDuplicatesJob(payload), []);

    return useMemo(() => ({
        createMoveJob,
        createExtractZipJob,
        getJobs,
        deleteJob,
        cancelJob,
        reprocessJob,
        getJobAttempts,
        uploadFileBackground,
        createMetadataUpdateJob,
        applyMetadataRecursive,
        removeMetadataRecursive,
        createSyncJob,
        createMetadataUndoJob,
        createApplyRuleJob,
        createExtractComicAssetsJob,
        createExtractBookAssetsJob,
        createAnalyzeImageAssetsJob,
        createAnalyzeLibraryImageAssetsJob,
        createReindexComicCoversJob,
        createExtractLibraryComicAssetsJob,
        createMapLibraryBooksJob,
        createExtractLibraryBookAssetsJob,
        createRemoveDuplicatesJob,
    }), [
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
        createReindexComicCoversJob,
        createRemoveDuplicatesJob,
        createSyncJob,
        deleteJob,
        getJobAttempts,
        getJobs,
        removeMetadataRecursive,
        reprocessJob,
        uploadFileBackground,
    ]);
}

export default useJobsListQuery;
