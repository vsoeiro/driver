import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCw, CheckCircle, XCircle, Clock, PlayCircle, Eye, AlertTriangle, Undo2, Trash2, Square, RotateCcw, ChevronLeft, ChevronRight, GripVertical } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import { cancelJob, createMetadataUndoJob, deleteJob, getJobAttempts, getJobs, reprocessJob } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';
import { useWorkspacePage } from '../contexts/WorkspaceContext';
import Modal from '../components/Modal';
import { getJobCrossLinkTarget } from '../lib/workspace';
import { formatJobStatus, formatJobType } from '../utils/jobLabels';
import { queryKeys } from '../lib/queryKeys';
import { formatDateTime } from '../utils/dateTime';

const DATE_RANGE_MS = {
    '24h': 24 * 60 * 60 * 1000,
    '3d': 3 * 24 * 60 * 60 * 1000,
    '7d': 7 * 24 * 60 * 60 * 1000,
    '30d': 30 * 24 * 60 * 60 * 1000,
    '90d': 90 * 24 * 60 * 60 * 1000,
};
const LIVE_JOB_STATUSES = new Set(['PENDING', 'RUNNING', 'RETRY_SCHEDULED', 'CANCEL_REQUESTED']);
const JOB_TABLE_COLUMNS = [
    { id: 'status', width: 104, minWidth: 96, align: 'left' },
    { id: 'jobId', width: 96, minWidth: 90, align: 'left' },
    { id: 'type', width: 280, minWidth: 220, align: 'left' },
    { id: 'created', width: 116, minWidth: 110, align: 'left' },
    { id: 'started', width: 116, minWidth: 110, align: 'left' },
    { id: 'finished', width: 116, minWidth: 110, align: 'left' },
    { id: 'duration', width: 82, minWidth: 80, align: 'right' },
    { id: 'eta', width: 112, minWidth: 104, align: 'left' },
    { id: 'progress', width: 420, minWidth: 320, align: 'left' },
    { id: 'actions', width: 106, minWidth: 88, align: 'center' },
];
const JOB_TABLE_COLUMN_WIDTHS_STORAGE_KEY = 'driver-jobs-table-widths-v1';
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200];

const getColumnAlignmentClasses = (align) => {
    if (align === 'right') return 'justify-end text-right';
    if (align === 'center') return 'justify-center text-center';
    return 'justify-start text-left';
};

export default function Jobs() {
    const { t, i18n } = useTranslation();
    const navigate = useNavigate();
    const location = useLocation();
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(50);
    const [selectedJob, setSelectedJob] = useState(null);
    const [undoingBatchId, setUndoingBatchId] = useState(null);
    const [deletingJobId, setDeletingJobId] = useState(null);
    const [cancellingJobId, setCancellingJobId] = useState(null);
    const [reprocessingJobId, setReprocessingJobId] = useState(null);
    const [attempts, setAttempts] = useState([]);
    const [loadingAttempts, setLoadingAttempts] = useState(false);
    const [statusFilter, setStatusFilter] = useState('ALL');
    const [typeFilter, setTypeFilter] = useState('ALL');
    const [dateRangeFilter, setDateRangeFilter] = useState('ALL');
    const [selectedJobIds, setSelectedJobIds] = useState(new Set());
    const [bulkCancelling, setBulkCancelling] = useState(false);
    const [bulkDeleting, setBulkDeleting] = useState(false);
    const resizeStateRef = useRef(null);
    const [columnWidths, setColumnWidths] = useState(() => {
        const defaults = JOB_TABLE_COLUMNS.reduce((acc, column) => ({ ...acc, [column.id]: column.width }), {});
        if (typeof window === 'undefined') return defaults;
        try {
            const raw = window.localStorage.getItem(JOB_TABLE_COLUMN_WIDTHS_STORAGE_KEY);
            if (!raw) return defaults;
            const parsed = JSON.parse(raw);
            return JOB_TABLE_COLUMNS.reduce((acc, column) => {
                const candidate = Number(parsed?.[column.id]);
                acc[column.id] = Number.isFinite(candidate)
                    ? Math.max(column.minWidth, candidate)
                    : column.width;
                return acc;
            }, {});
        } catch {
            return defaults;
        }
    });
    const { showToast } = useToast();
    const queryClient = useQueryClient();
    const DATE_RANGE_OPTIONS = [
        { value: 'ALL', label: t('jobs.allTime') },
        { value: '24h', label: t('adminDashboard.last24h'), hours: 24 },
        { value: '3d', label: t('adminDashboard.last3d'), days: 3 },
        { value: '7d', label: t('adminDashboard.last7d'), days: 7 },
        { value: '30d', label: t('adminDashboard.last30d'), days: 30 },
        { value: '90d', label: t('adminDashboard.last90d'), days: 90 },
    ];

    const JOB_TYPE_OPTIONS = [
        { value: 'ALL', label: t('jobs.allTypes') },
        { value: 'sync_items', label: t('jobs.typeOptions.sync_items') },
        { value: 'move_items', label: t('jobs.typeOptions.move_items') },
        { value: 'upload_file', label: t('jobs.typeOptions.upload_file') },
        { value: 'extract_zip_contents', label: t('jobs.typeOptions.extract_zip_contents') },
        { value: 'update_metadata', label: t('jobs.typeOptions.update_metadata') },
        { value: 'apply_metadata_recursive', label: t('jobs.typeOptions.apply_metadata_recursive') },
        { value: 'remove_metadata_recursive', label: t('jobs.typeOptions.remove_metadata_recursive') },
        { value: 'undo_metadata_batch', label: t('jobs.typeOptions.undo_metadata_batch') },
        { value: 'apply_metadata_rule', label: t('jobs.typeOptions.apply_metadata_rule') },
        { value: 'extract_comic_assets', label: t('jobs.typeOptions.extract_comic_assets') },
        { value: 'extract_book_assets', label: t('jobs.typeOptions.extract_book_assets') },
        { value: 'extract_library_comic_assets', label: t('jobs.typeOptions.extract_library_comic_assets') },
        { value: 'reindex_comic_covers', label: t('jobs.typeOptions.reindex_comic_covers') },
        { value: 'reindex_book_covers', label: t('jobs.typeOptions.reindex_book_covers') },
        { value: 'analyze_image_assets', label: t('jobs.typeOptions.analyze_image_assets') },
        { value: 'analyze_library_image_assets', label: t('jobs.typeOptions.analyze_library_image_assets') },
        { value: 'remove_duplicate_files', label: t('jobs.typeOptions.remove_duplicate_files') },
    ];
    const autoRefreshEnabled = page === 1 && (statusFilter === 'ALL' || LIVE_JOB_STATUSES.has(statusFilter));

    const queryKey = useMemo(
        () => queryKeys.jobs.list({
            page,
            pageSize,
            statuses: statusFilter === 'ALL' ? [] : [statusFilter],
            types: typeFilter === 'ALL' ? [] : [typeFilter],
            createdAfter: (() => {
                const deltaMs = DATE_RANGE_MS[dateRangeFilter] || 0;
                return deltaMs > 0 ? new Date(Date.now() - deltaMs).toISOString() : null;
            })(),
            includeEstimates: true,
        }),
        [dateRangeFilter, page, pageSize, statusFilter, typeFilter],
    );
    const {
        data: jobs = [],
        isLoading,
        isFetching,
        error,
        refetch,
    } = useQuery({
        queryKey,
        queryFn: async ({ signal }) => {
            const offset = (page - 1) * pageSize;
            const statuses = statusFilter === 'ALL' ? [] : [statusFilter];
            const types = typeFilter === 'ALL' ? [] : [typeFilter];
            const deltaMs = DATE_RANGE_MS[dateRangeFilter] || 0;
            const createdAfter = deltaMs > 0 ? new Date(Date.now() - deltaMs).toISOString() : null;
            return getJobs(pageSize, offset, statuses, { types, createdAfter }, { signal });
        },
        staleTime: 5000,
        refetchInterval: autoRefreshEnabled ? 10000 : false,
        refetchIntervalInBackground: false,
    });
    const loading = isLoading;
    const refreshing = isFetching && !isLoading;
    const hasNextPage = jobs.length === pageSize;

    useEffect(() => {
        if (error) {
            showToast(t('jobs.failedLoad'), 'error');
        }
    }, [error, showToast, t]);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        window.localStorage.setItem(JOB_TABLE_COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify(columnWidths));
    }, [columnWidths]);

    const jobsTableTemplate = useMemo(() => {
        const dynamicColumns = JOB_TABLE_COLUMNS.map(
            (column) => `${Math.max(column.minWidth, columnWidths[column.id] ?? column.width)}px`
        );
        return `38px ${dynamicColumns.join(' ')}`;
    }, [columnWidths]);

    const jobsTableMinWidth = useMemo(() => {
        const selectWidth = 38;
        const totalColumns = 1 + JOB_TABLE_COLUMNS.length;
        const gapPx = Math.max(0, totalColumns - 1) * 12; // gap-3
        const dynamicWidth = JOB_TABLE_COLUMNS.reduce(
            (sum, column) => sum + Math.max(column.minWidth, columnWidths[column.id] ?? column.width),
            0
        );
        return selectWidth + dynamicWidth + gapPx;
    }, [columnWidths]);

    const beginResize = (event, column) => {
        event.preventDefault();
        event.stopPropagation();
        const startX = event.clientX;
        const initialWidth = Math.max(column.minWidth, columnWidths[column.id] ?? column.width);
        resizeStateRef.current = { columnId: column.id, startX, initialWidth, minWidth: column.minWidth };

        const onMouseMove = (moveEvent) => {
            if (!resizeStateRef.current) return;
            const nextWidth = resizeStateRef.current.initialWidth + (moveEvent.clientX - resizeStateRef.current.startX);
            setColumnWidths((prev) => ({
                ...prev,
                [resizeStateRef.current.columnId]: Math.max(resizeStateRef.current.minWidth, nextWidth),
            }));
        };
        const onMouseUp = () => {
            resizeStateRef.current = null;
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
    };

    const goToPreviousPage = () => {
        if (page <= 1) return;
        setPage((current) => current - 1);
    };

    const goToNextPage = () => {
        if (!hasNextPage) return;
        setPage((current) => current + 1);
    };

    const canDeleteJobStatus = (status) => ['COMPLETED', 'FAILED', 'DEAD_LETTER', 'CANCELLED'].includes(status);
    const canCancelJobStatus = (status) => ['PENDING', 'RUNNING', 'RETRY_SCHEDULED', 'CANCEL_REQUESTED'].includes(status);
    const canTriggerCancelJobStatus = (status) => ['PENDING', 'RUNNING', 'RETRY_SCHEDULED'].includes(status);

    const selectedJobs = useMemo(
        () => jobs.filter((job) => selectedJobIds.has(job.id)),
        [jobs, selectedJobIds],
    );
    const allJobsSelectedOnPage = jobs.length > 0 && jobs.every((job) => selectedJobIds.has(job.id));
    const canBulkDelete = selectedJobs.length > 0 && selectedJobs.every((job) => canDeleteJobStatus(job.status));
    const canBulkStop = selectedJobs.length > 0 && selectedJobs.every((job) => canTriggerCancelJobStatus(job.status));

    useEffect(() => {
        setSelectedJobIds(new Set());
    }, [page, pageSize, statusFilter, typeFilter, dateRangeFilter]);

    const toggleJobSelection = (jobId) => {
        setSelectedJobIds((prev) => {
            const next = new Set(prev);
            if (next.has(jobId)) next.delete(jobId);
            else next.add(jobId);
            return next;
        });
    };

    const toggleSelectAllOnPage = () => {
        setSelectedJobIds((prev) => {
            const next = new Set(prev);
            if (allJobsSelectedOnPage) {
                jobs.forEach((job) => next.delete(job.id));
            } else {
                jobs.forEach((job) => next.add(job.id));
            }
            return next;
        });
    };

    const getStatusIcon = (status) => {
        switch (status) {
            case 'COMPLETED':
                return <CheckCircle className="w-4 h-4" />;
            case 'FAILED':
                return <XCircle className="w-4 h-4" />;
            case 'DEAD_LETTER':
                return <AlertTriangle className="w-4 h-4" />;
            case 'RUNNING':
                return <PlayCircle className="w-4 h-4" />;
            case 'CANCEL_REQUESTED':
                return <Square className="w-4 h-4" />;
            case 'CANCELLED':
                return <Square className="w-4 h-4" />;
            default:
                return <Clock className="w-4 h-4" />;
        }
    };

    const getStatusTone = (status) => {
        if (status === 'COMPLETED') return 'status-badge-success';
        if (status === 'FAILED' || status === 'DEAD_LETTER') return 'status-badge-danger';
        if (status === 'RUNNING') return 'status-badge-info';
        if (status === 'CANCEL_REQUESTED') return 'status-badge-warning';
        return 'status-badge';
    };

    const triggerUndo = async (batchId) => {
        if (!batchId) return;
        setUndoingBatchId(batchId);
        try {
            await createMetadataUndoJob(batchId);
            showToast(t('jobs.undoCreated', { batch: batchId.slice(0, 8) }), 'success');
            refetch();
        } catch {
            showToast(t('jobs.failedUndo'), 'error');
        } finally {
            setUndoingBatchId(null);
        }
    };

    const removeJob = async (jobId) => {
        setDeletingJobId(jobId);
        try {
            await deleteJob(jobId);
            queryClient.setQueryData(queryKey, (prev = []) => prev.filter((job) => job.id !== jobId));
            if (selectedJob?.id === jobId) setSelectedJob(null);
            showToast(t('jobs.jobRemoved'), 'success');
        } catch {
            showToast(t('jobs.failedRemove'), 'error');
        } finally {
            setDeletingJobId(null);
        }
    };

    const requestCancel = async (jobId) => {
        setCancellingJobId(jobId);
        try {
            await cancelJob(jobId);
            queryClient.setQueryData(queryKey, (prev = []) =>
                prev.map((job) =>
                    job.id === jobId
                        ? {
                            ...job,
                            status: 'CANCELLED',
                        }
                        : job
                )
            );
            showToast(t('jobs.cancelRequested'), 'success');
            refetch();
        } catch (error) {
            const message = error?.response?.data?.detail || t('jobs.failedCancel');
            showToast(message, 'error');
        } finally {
            setCancellingJobId(null);
        }
    };

    const triggerReprocess = async (jobId) => {
        setReprocessingJobId(jobId);
        try {
            const cloned = await reprocessJob(jobId);
            showToast(t('jobs.reprocessQueued', { id: cloned.id }), 'success');
            refetch();
        } catch (error) {
            const message = error?.response?.data?.detail || t('jobs.failedReprocess');
            showToast(message, 'error');
        } finally {
            setReprocessingJobId(null);
        }
    };

    const requestBulkCancel = async () => {
        if (!canBulkStop || bulkCancelling) return;
        setBulkCancelling(true);
        const targetIds = selectedJobs.map((job) => job.id);
        try {
            const results = await Promise.allSettled(targetIds.map((jobId) => cancelJob(jobId)));
            const successIds = targetIds.filter((_, index) => results[index].status === 'fulfilled');
            const successSet = new Set(successIds);

            if (successSet.size > 0) {
                queryClient.setQueryData(queryKey, (prev = []) =>
                    prev.map((job) =>
                        successSet.has(job.id)
                            ? {
                                ...job,
                                status: 'CANCELLED',
                            }
                            : job
                    )
                );
                setSelectedJobIds((prev) => {
                    const next = new Set(prev);
                    successIds.forEach((jobId) => next.delete(jobId));
                    return next;
                });
            }

            if (successIds.length === targetIds.length) {
                showToast(t('jobs.bulkStopRequested', { count: successIds.length }), 'success');
            } else if (successIds.length > 0) {
                showToast(
                    t('jobs.bulkStopPartial', { success: successIds.length, total: targetIds.length }),
                    'warning',
                );
            } else {
                showToast(t('jobs.bulkStopFailed'), 'error');
            }
            refetch();
        } catch {
            showToast(t('jobs.bulkStopFailed'), 'error');
        } finally {
            setBulkCancelling(false);
        }
    };

    const removeBulkJobs = async () => {
        if (!canBulkDelete || bulkDeleting) return;
        setBulkDeleting(true);
        const targetIds = selectedJobs.map((job) => job.id);
        try {
            const results = await Promise.allSettled(targetIds.map((jobId) => deleteJob(jobId)));
            const successIds = targetIds.filter((_, index) => results[index].status === 'fulfilled');
            const successSet = new Set(successIds);

            if (successSet.size > 0) {
                queryClient.setQueryData(queryKey, (prev = []) =>
                    prev.filter((job) => !successSet.has(job.id))
                );
                if (selectedJob?.id && successSet.has(selectedJob.id)) {
                    setSelectedJob(null);
                }
                setSelectedJobIds((prev) => {
                    const next = new Set(prev);
                    successIds.forEach((jobId) => next.delete(jobId));
                    return next;
                });
            }

            if (successIds.length === targetIds.length) {
                showToast(t('jobs.bulkDeleteSuccess', { count: successIds.length }), 'success');
            } else if (successIds.length > 0) {
                showToast(
                    t('jobs.bulkDeletePartial', { success: successIds.length, total: targetIds.length }),
                    'warning',
                );
            } else {
                showToast(t('jobs.bulkDeleteFailed'), 'error');
            }
        } catch {
            showToast(t('jobs.bulkDeleteFailed'), 'error');
        } finally {
            setBulkDeleting(false);
        }
    };

    const formatDate = (dateString) => {
        return formatDateTime(dateString, i18n.language);
    };

    const formatDuration = (seconds) => {
        if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) return '-';
        const safe = Math.max(0, Math.floor(Number(seconds)));
        const hours = Math.floor(safe / 3600);
        const minutes = Math.floor((safe % 3600) / 60);
        const secs = safe % 60;
        if (hours > 0) return `${hours}h ${minutes}m`;
        if (minutes > 0) return `${minutes}m ${secs}s`;
        return `${secs}s`;
    };

    const statusSummary = useMemo(() => ({
        active: jobs.filter((job) => LIVE_JOB_STATUSES.has(job.status)).length,
        failed: jobs.filter((job) => ['FAILED', 'DEAD_LETTER'].includes(job.status)).length,
        completed: jobs.filter((job) => job.status === 'COMPLETED').length,
    }), [jobs]);

    const pickMetricNumber = (source, keys) => {
        if (!source || typeof source !== 'object') return null;
        for (const key of keys) {
            const value = source[key];
            if (typeof value === 'number' && Number.isFinite(value)) {
                return Math.max(0, Math.trunc(value));
            }
        }
        return null;
    };

    useWorkspacePage(useMemo(() => ({
        title: t('jobs.title'),
        subtitle: t('workspace.jobsSubtitle'),
        entityType: 'jobs',
        entityId: 'queue',
        sourceRoute: location.pathname,
        selectedIds: Array.from(selectedJobIds),
        activeFilters: [
            statusFilter !== 'ALL' ? t('workspace.filterStatus', { value: statusFilter }) : '',
            typeFilter !== 'ALL' ? t('workspace.filterType', { value: typeFilter }) : '',
            dateRangeFilter !== 'ALL' ? t('workspace.filterWindow', { value: dateRangeFilter }) : '',
        ].filter(Boolean),
        metrics: [
            t('jobs.selectedCount', { count: selectedJobIds.size }),
            t('workspace.jobMetricActive', { count: statusSummary.active }),
            t('workspace.jobMetricFailed', { count: statusSummary.failed }),
        ],
        suggestedPrompts: [
            t('workspace.aiPrompts.jobReview'),
            t('workspace.aiPrompts.recommend'),
            t('workspace.aiPrompts.summarize'),
        ],
    }), [dateRangeFilter, location.pathname, selectedJobIds, statusFilter, statusSummary.active, statusSummary.failed, t, typeFilter]));

    const getMetricSummary = (job) => {
        const metrics = job?.metrics && typeof job.metrics === 'object' ? job.metrics : {};
        const result = job?.result && typeof job.result === 'object' ? job.result : {};
        const success = pickMetricNumber(metrics, ['success', 'mapped', 'updated', 'changed', 'deleted']) ?? pickMetricNumber(result, ['success', 'mapped', 'updated', 'changed', 'deleted']) ?? 0;
        const failed = pickMetricNumber(metrics, ['failed', 'errors']) ?? pickMetricNumber(result, ['failed', 'errors']) ?? 0;
        const skipped = pickMetricNumber(metrics, ['skipped', 'unchanged']) ?? pickMetricNumber(result, ['skipped', 'unchanged']) ?? 0;
        const explicitTotal = pickMetricNumber(metrics, ['total']) ?? pickMetricNumber(result, ['total']);
        return {
            total: explicitTotal,
            success,
            failed,
            skipped,
        };
    };

    const getJobProgressSummary = (job) => {
        const metricSummary = getMetricSummary(job);
        const rawProgressPercent = Number.isFinite(Number(job?.progress_percent))
            ? Math.trunc(Number(job.progress_percent))
            : 0;
        const normalizedProgressPercent = Math.max(0, Math.min(100, rawProgressPercent));
        const progressTotal = Number.isFinite(Number(job?.progress_total))
            ? Math.max(0, Math.trunc(Number(job.progress_total)))
            : null;
        const totalItems = progressTotal ?? metricSummary.total;
        const hasKnownTotal = totalItems !== null;
        const processedItems = Math.max(0, metricSummary.success + metricSummary.failed + metricSummary.skipped);
        const processedDisplay = hasKnownTotal && totalItems > 0
            ? Math.min(processedItems, totalItems)
            : processedItems;
        const breakdownTotal = hasKnownTotal && totalItems > 0 ? totalItems : processedItems;
        const breakdownDenominator = breakdownTotal > 0 ? breakdownTotal : 1;
        const successWidth = (Math.max(0, metricSummary.success) / breakdownDenominator) * 100;
        const failedWidth = (Math.max(0, metricSummary.failed) / breakdownDenominator) * 100;
        const skippedWidth = (Math.max(0, metricSummary.skipped) / breakdownDenominator) * 100;
        const completionPercent = hasKnownTotal && totalItems > 0
            ? Math.min(100, Math.round((processedDisplay / totalItems) * 100))
            : normalizedProgressPercent;
        return {
            metricSummary,
            totalItems,
            hasKnownTotal,
            processedDisplay,
            breakdownTotal,
            successWidth,
            failedWidth,
            skippedWidth,
            normalizedProgressPercent,
            completionPercent,
        };
    };

    const normalizeErrorItems = (job) => {
        const candidateSources = [];
        if (job?.result && typeof job.result === 'object') candidateSources.push(job.result);
        if (job?.metrics && typeof job.metrics === 'object') candidateSources.push(job.metrics);

        const normalized = [];
        const pushNormalized = (item, indexHint = 0) => {
            if (typeof item === 'string') {
                normalized.push({
                    key: `error-${indexHint}`,
                    reason: item,
                    itemId: null,
                    itemName: null,
                    stage: null,
                });
                return;
            }
            if (!item || typeof item !== 'object') return;

            const reasonRaw = item.reason ?? item.error ?? item.message ?? item.detail;
            const reason = typeof reasonRaw === 'string' ? reasonRaw : reasonRaw ? String(reasonRaw) : '';
            if (!reason) return;

            const itemIdRaw = item.item_id ?? item.itemId ?? item.id ?? null;
            const itemNameRaw = item.item_name ?? item.itemName ?? item.name ?? item.path ?? null;
            const stageRaw = item.stage ?? null;
            const itemId = itemIdRaw ? String(itemIdRaw) : null;
            const itemName = itemNameRaw ? String(itemNameRaw) : null;
            const stage = stageRaw ? String(stageRaw) : null;
            const key = `${itemId || itemName || 'error'}-${reason}-${stage || ''}`;
            normalized.push({
                key,
                reason,
                itemId,
                itemName,
                stage,
            });
        };

        candidateSources.forEach((source) => {
            const errorItems = source.error_items ?? source.failed_items ?? source.errors_by_item ?? null;
            if (Array.isArray(errorItems)) {
                errorItems.forEach((item, index) => pushNormalized(item, index));
            } else if (errorItems && typeof errorItems === 'object') {
                Object.entries(errorItems).forEach(([itemId, reason], index) => {
                    pushNormalized({ item_id: itemId, reason }, index);
                });
            }
        });

        const deduped = [];
        const seen = new Set();
        normalized.forEach((entry) => {
            if (seen.has(entry.key)) return;
            seen.add(entry.key);
            deduped.push(entry);
        });
        return deduped;
    };

    const getErrorItemsTruncated = (job) => {
        const resultTruncated = job?.result?.error_items_truncated;
        const metricsTruncated = job?.metrics?.error_items_truncated;
        const fromResult = Number.isFinite(Number(resultTruncated)) ? Math.max(0, Math.trunc(Number(resultTruncated))) : 0;
        const fromMetrics = Number.isFinite(Number(metricsTruncated)) ? Math.max(0, Math.trunc(Number(metricsTruncated))) : 0;
        return Math.max(fromResult, fromMetrics);
    };

    const getJobErrorText = (job, attemptRows = []) => {
        if (!job || typeof job !== 'object') return null;
        if (typeof job?.result?.error === 'string' && job.result.error.trim()) return job.result.error;
        if (typeof job?.dead_letter_reason === 'string' && job.dead_letter_reason.trim()) return job.dead_letter_reason;
        if (typeof job?.last_error === 'string' && job.last_error.trim()) return job.last_error;
        const attemptError = Array.isArray(attemptRows) ? attemptRows.find((attempt) => typeof attempt?.error === 'string' && attempt.error.trim())?.error : null;
        if (typeof attemptError === 'string' && attemptError.trim()) return attemptError;
        return null;
    };

    const selectedProgressSummary = selectedJob ? getJobProgressSummary(selectedJob) : null;
    const selectedMetricSummary = selectedProgressSummary ? selectedProgressSummary.metricSummary : null;
    const selectedErrorText = selectedJob ? getJobErrorText(selectedJob, attempts) : null;
    const selectedErrorItems = selectedJob ? normalizeErrorItems(selectedJob) : [];
    const selectedErrorItemsTruncated = selectedJob ? getErrorItemsTruncated(selectedJob) : 0;
    const selectedHasItemDetails = selectedMetricSummary
        ? selectedMetricSummary.failed > 0 || selectedMetricSummary.skipped > 0
        : false;

    return (
        <div className="app-page">
            <div className="page-header">
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <h1 className="page-title">{t('jobs.title')}</h1>
                        <p className="page-subtitle">{t('jobs.subtitle')}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <select
                            className="input-shell px-2 py-1.5 text-sm"
                            value={statusFilter}
                            onChange={(event) => {
                                const nextStatus = event.target.value;
                                setStatusFilter(nextStatus);
                                setPage(1);
                            }}
                        >
                            <option value="ALL">{t('jobs.allStatus')}</option>
                            <option value="PENDING">{t('jobStatus.PENDING')}</option>
                            <option value="RUNNING">{t('jobStatus.RUNNING')}</option>
                            <option value="RETRY_SCHEDULED">{t('jobStatus.RETRY_SCHEDULED')}</option>
                            <option value="COMPLETED">{t('jobStatus.COMPLETED')}</option>
                            <option value="FAILED">{t('jobStatus.FAILED')}</option>
                            <option value="DEAD_LETTER">{t('jobStatus.DEAD_LETTER')}</option>
                            <option value="CANCELLED">{t('jobStatus.CANCELLED')}</option>
                        </select>
                        <select
                            className="input-shell px-2 py-1.5 text-sm"
                            value={typeFilter}
                            onChange={(event) => {
                                const nextType = event.target.value;
                                setTypeFilter(nextType);
                                setPage(1);
                            }}
                        >
                            {JOB_TYPE_OPTIONS.map((option) => (
                                <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                        </select>
                        <select
                            className="input-shell px-2 py-1.5 text-sm"
                            value={dateRangeFilter}
                            onChange={(event) => {
                                const nextRange = event.target.value;
                                setDateRangeFilter(nextRange);
                                setPage(1);
                            }}
                        >
                            {DATE_RANGE_OPTIONS.map((option) => (
                                <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                        </select>
                        <label className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                            <span>{t('jobs.resultsPerPage')}</span>
                            <select
                                className="input-shell px-2 py-1.5 text-sm text-foreground"
                                value={pageSize}
                                onChange={(event) => {
                                    setPageSize(Number(event.target.value));
                                    setPage(1);
                                }}
                            >
                                {PAGE_SIZE_OPTIONS.map((option) => (
                                    <option key={option} value={option}>{option}</option>
                                ))}
                            </select>
                        </label>
                        <span className="status-chip">{t('jobs.page', { page })}</span>
                        <div className="flex gap-1">
                            <button
                                onClick={goToPreviousPage}
                                disabled={page <= 1 || loading}
                                className="ghost-icon-button p-1 disabled:opacity-50"
                                title={t('jobs.previousPage')}
                            >
                                <ChevronLeft size={16} />
                            </button>
                            <button
                                onClick={goToNextPage}
                                disabled={!hasNextPage || loading}
                                className="ghost-icon-button p-1 disabled:opacity-50"
                                title={t('jobs.nextPage')}
                            >
                                <ChevronRight size={16} />
                            </button>
                        </div>
                        <button
                            onClick={() => refetch()}
                            className="btn-refresh px-2.5"
                            title={t('jobs.refresh')}
                        >
                            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                        </button>
                    </div>
                </div>
            </div>

            <div className="mb-4 grid gap-3 md:grid-cols-3 xl:grid-cols-4">
                <div className="surface-card p-4">
                    <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('workspace.jobMetricActive', { count: statusSummary.active })}</div>
                    <div className="mt-2 text-2xl font-semibold">{statusSummary.active}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{t('jobs.status')}</div>
                </div>
                <div className="surface-card p-4">
                    <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('workspace.jobMetricFailed', { count: statusSummary.failed })}</div>
                    <div className="mt-2 text-2xl font-semibold">{statusSummary.failed}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{t('jobs.failed')}</div>
                </div>
                <div className="surface-card p-4">
                    <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('jobs.selectedCount', { count: selectedJobIds.size })}</div>
                    <div className="mt-2 text-2xl font-semibold">{selectedJobIds.size}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{t('jobs.actions')}</div>
                </div>
                <div className="surface-card p-4">
                    <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('jobStatus.COMPLETED')}</div>
                    <div className="mt-2 text-2xl font-semibold">{statusSummary.completed}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{t('jobs.refresh')}</div>
                </div>
            </div>

            <div className="flex-1 overflow-auto">
                {loading && jobs.length === 0 ? (
                    <div className="surface-card p-4 space-y-3">
                        <div className="skeleton-block h-5 w-40" />
                        <div className="skeleton-block h-10 w-full" />
                        <div className="skeleton-block h-10 w-full" />
                        <div className="skeleton-block h-10 w-full" />
                        <div className="skeleton-block h-10 w-full" />
                    </div>
                ) : jobs.length === 0 ? (
                    <div className="empty-state">
                        <div className="empty-state-title">{t('jobs.noJobs')}</div>
                        <p className="empty-state-text">{t('jobs.noJobsHelp')}</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        <div className="surface-card px-4 py-2 flex flex-wrap items-center justify-between gap-3 text-sm">
                            <div className="flex items-center gap-2">
                                <span className="font-medium tabular-nums">{t('jobs.selectedCount', { count: selectedJobIds.size })}</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={requestBulkCancel}
                                    disabled={!canBulkStop || bulkCancelling}
                                    className="p-2 hover:bg-background rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                                    title={canBulkStop ? t('jobs.stopSelected') : t('jobs.stopSelectedBlocked')}
                                >
                                    <Square size={16} />
                                    <span>{t('jobs.stopSelected')}</span>
                                </button>
                                <button
                                    onClick={removeBulkJobs}
                                    disabled={!canBulkDelete || bulkDeleting}
                                    className="p-2 hover:bg-background rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                                    title={canBulkDelete ? t('jobs.deleteSelected') : t('jobs.deleteSelectedBlocked')}
                                >
                                    <Trash2 size={16} />
                                    <span>{t('jobs.deleteSelected')}</span>
                                </button>
                            </div>
                        </div>

                        <div className="surface-card overflow-x-auto">
                        <div style={{ minWidth: `${jobsTableMinWidth}px` }}>
                            <div
                                className="sticky top-0 z-20 grid items-center gap-3 border-b border-border/70 bg-muted/95 p-3 text-xs font-medium uppercase tracking-wider text-muted-foreground shadow-sm backdrop-blur supports-[backdrop-filter]:bg-muted/80"
                                style={{ gridTemplateColumns: jobsTableTemplate, minWidth: `${jobsTableMinWidth}px` }}
                            >
                                <div>
                                    <input
                                        type="checkbox"
                                        checked={allJobsSelectedOnPage}
                                        onChange={toggleSelectAllOnPage}
                                        aria-label={t('jobs.selectAllOnPage')}
                                    />
                                </div>
                                {JOB_TABLE_COLUMNS.map((column) => {
                                    const label = column.id === 'jobId'
                                        ? t('jobs.jobId')
                                        : column.id === 'actions'
                                            ? ''
                                            : t(`jobs.${column.id}`);
                                    return (
                                        <div
                                            key={column.id}
                                            className={`relative flex min-w-0 items-center gap-1 ${getColumnAlignmentClasses(column.align)}`}
                                        >
                                            {column.id !== 'actions' && <div className="pointer-events-none absolute bottom-0 right-0 top-0 w-px bg-border/80" />}
                                            <span className="inline-flex min-w-0 items-center gap-1">
                                                {column.id !== 'actions' && <GripVertical size={12} className="opacity-45" />}
                                                {label}
                                            </span>
                                            {column.id !== 'actions' && (
                                                <div
                                                    className="absolute right-[-8px] top-0 h-full w-3 cursor-col-resize"
                                                    onMouseDown={(event) => beginResize(event, column)}
                                                />
                                            )}
                                        </div>
                                    );
                                })}
                            </div>

                            <div className="divide-y text-sm">
                                {jobs.map((job) => {
                                const started = job.started_at ? new Date(job.started_at) : null;
                                const completed = job.completed_at ? new Date(job.completed_at) : null;
                                const duration = started && completed
                                    ? ((completed - started) / 1000).toFixed(1) + 's'
                                    : '-';
                                const finishedAt = job.completed_at || job.dead_lettered_at || null;
                                const {
                                    metricSummary,
                                    totalItems,
                                    hasKnownTotal,
                                    breakdownTotal,
                                    successWidth,
                                    failedWidth,
                                    skippedWidth,
                                    normalizedProgressPercent,
                                    completionPercent,
                                } = getJobProgressSummary(job);
                                const isQueued = ['PENDING', 'RETRY_SCHEDULED'].includes(job.status);
                                const etaText = isQueued
                                    ? `~${formatDuration(job.estimated_wait_seconds)} (${job.queue_position ? `#${job.queue_position}` : '-'})`
                                    : '-';
                                const canUndo = job.status === 'COMPLETED' && job.result?.batch_id;
                                const canDelete = canDeleteJobStatus(job.status);
                                const canCancel = canCancelJobStatus(job.status);

                                    return (
                                        <div
                                            key={job.id}
                                            className="grid gap-3 p-3 items-center hover:bg-accent/35 transition-colors pointer-events-none"
                                            style={{ gridTemplateColumns: jobsTableTemplate, minWidth: `${jobsTableMinWidth}px` }}
                                        >
                                        <div className="pointer-events-auto">
                                            <input
                                                type="checkbox"
                                                checked={selectedJobIds.has(job.id)}
                                                onChange={() => toggleJobSelection(job.id)}
                                                aria-label={`${t('jobs.jobId')} ${String(job.id).slice(0, 8)}`}
                                            />
                                        </div>
                                        <div className={`pointer-events-auto relative flex min-w-0 items-center ${getColumnAlignmentClasses('left')}`}>
                                            <div className="pointer-events-none absolute bottom-[-10px] right-[-6px] top-[-10px] w-px bg-border/50" />
                                            <div className={`status-badge ${getStatusTone(job.status)}`}>
                                                {getStatusIcon(job.status)}
                                                <span>{formatJobStatus(job.status, t)}</span>
                                            </div>
                                        </div>
                                        <div className={`pointer-events-auto relative flex min-w-0 items-center ${getColumnAlignmentClasses('left')}`}>
                                            <div className="pointer-events-none absolute bottom-[-10px] right-[-6px] top-[-10px] w-px bg-border/50" />
                                            <div className="min-w-0 truncate font-mono text-xs text-muted-foreground" title={job.id}>
                                                {String(job.id).slice(0, 8)}...
                                            </div>
                                        </div>
                                        <div className={`pointer-events-auto relative flex min-w-0 items-center ${getColumnAlignmentClasses('left')}`}>
                                            <div className="pointer-events-none absolute bottom-[-10px] right-[-6px] top-[-10px] w-px bg-border/50" />
                                            <div className="min-w-0 truncate font-medium text-foreground">
                                                {formatJobType(job.type, t)}
                                            </div>
                                        </div>
                                        <div className={`pointer-events-auto relative flex min-w-0 items-center ${getColumnAlignmentClasses(JOB_TABLE_COLUMNS.find((column) => column.id === 'created')?.align)}`}>
                                            <div className="pointer-events-none absolute bottom-[-10px] right-[-6px] top-[-10px] w-px bg-border/50" />
                                            <div className="text-muted-foreground tabular-nums">
                                                {formatDate(job.created_at)}
                                            </div>
                                        </div>
                                        <div className={`pointer-events-auto relative flex min-w-0 items-center ${getColumnAlignmentClasses(JOB_TABLE_COLUMNS.find((column) => column.id === 'started')?.align)}`}>
                                            <div className="pointer-events-none absolute bottom-[-10px] right-[-6px] top-[-10px] w-px bg-border/50" />
                                            <div className="text-muted-foreground tabular-nums">
                                                {formatDate(job.started_at)}
                                            </div>
                                        </div>
                                        <div className={`pointer-events-auto relative flex min-w-0 items-center ${getColumnAlignmentClasses(JOB_TABLE_COLUMNS.find((column) => column.id === 'finished')?.align)}`}>
                                            <div className="pointer-events-none absolute bottom-[-10px] right-[-6px] top-[-10px] w-px bg-border/50" />
                                            <div className="text-muted-foreground tabular-nums">
                                                {formatDate(finishedAt)}
                                            </div>
                                        </div>
                                        <div className={`pointer-events-auto relative flex min-w-0 items-center ${getColumnAlignmentClasses(JOB_TABLE_COLUMNS.find((column) => column.id === 'duration')?.align)}`}>
                                            <div className="pointer-events-none absolute bottom-[-10px] right-[-6px] top-[-10px] w-px bg-border/50" />
                                            <div className="font-mono text-muted-foreground tabular-nums">
                                                {duration}
                                            </div>
                                        </div>
                                        <div className={`pointer-events-auto relative flex min-w-0 items-center ${getColumnAlignmentClasses(JOB_TABLE_COLUMNS.find((column) => column.id === 'eta')?.align)}`}>
                                            <div className="pointer-events-none absolute bottom-[-10px] right-[-6px] top-[-10px] w-px bg-border/50" />
                                            <div className="min-w-0 text-xs text-muted-foreground tabular-nums leading-5">
                                                <div>{etaText}</div>
                                                {isQueued && (
                                                    <div>
                                                        {t('jobs.started')}: {formatDate(job.estimated_start_at)}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                        <div className={`pointer-events-auto relative flex min-w-0 items-center ${getColumnAlignmentClasses(JOB_TABLE_COLUMNS.find((column) => column.id === 'progress')?.align)}`}>
                                            <div className="pointer-events-none absolute bottom-[-10px] right-[-6px] top-[-10px] w-px bg-border/50" />
                                            <div className="min-w-0 w-full">
                                                <div className="flex w-full items-center gap-3">
                                                    <div className="h-4 flex-1 overflow-hidden rounded-md border border-border/60 bg-muted/60">
                                                        <div className="flex h-full">
                                                            {breakdownTotal > 0 ? (
                                                                <>
                                                                    <div className="h-full bg-emerald-500" style={{ width: `${successWidth}%` }} />
                                                                    <div className="h-full bg-destructive" style={{ width: `${failedWidth}%` }} />
                                                                    <div className="h-full bg-amber-400" style={{ width: `${skippedWidth}%` }} />
                                                                </>
                                                            ) : (
                                                                <div
                                                                    className={`h-full ${job.status === 'FAILED' || job.status === 'DEAD_LETTER' ? 'bg-destructive' : 'bg-primary'}`}
                                                                    style={{ width: `${normalizedProgressPercent}%` }}
                                                                />
                                                            )}
                                                        </div>
                                                    </div>
                                                    <span className="w-12 shrink-0 text-right text-[11px] tabular-nums text-muted-foreground">
                                                        {completionPercent}%
                                                    </span>
                                                </div>
                                                <div className="mt-1.5 flex items-center gap-3 overflow-hidden whitespace-nowrap text-[11px] tabular-nums text-muted-foreground">
                                                    <span className="inline-flex items-center gap-1" title={`${t('jobs.success')}: ${metricSummary.success}`}>
                                                        <span className="h-2 w-2 rounded-full bg-emerald-500" />
                                                        {metricSummary.success}
                                                    </span>
                                                    <span className="inline-flex items-center gap-1" title={`${t('jobs.failed')}: ${metricSummary.failed}`}>
                                                        <span className={`h-2 w-2 rounded-full ${metricSummary.failed > 0 ? 'bg-destructive' : 'bg-muted-foreground/35'}`} />
                                                        {metricSummary.failed}
                                                    </span>
                                                    <span className="inline-flex items-center gap-1" title={`${t('jobs.skipped')}: ${metricSummary.skipped}`}>
                                                        <span className="h-2 w-2 rounded-full bg-amber-400" />
                                                        {metricSummary.skipped}
                                                    </span>
                                                    <span title={`${t('jobs.total')}: ${hasKnownTotal ? totalItems : '-'}`}>
                                                        {hasKnownTotal ? totalItems : '-'}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                        <div className={`pointer-events-auto relative flex min-w-0 items-center ${getColumnAlignmentClasses(JOB_TABLE_COLUMNS.find((column) => column.id === 'actions')?.align)}`}>
                                            <div className="flex items-center justify-center gap-1">
                                                {canUndo && (
                                                    <button
                                                        onClick={() => triggerUndo(job.result.batch_id)}
                                                        disabled={undoingBatchId === job.result.batch_id}
                                                        className="p-1 text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors disabled:opacity-50"
                                                        title={t('jobs.undoBatch')}
                                                    >
                                                        <Undo2 className="w-4 h-4" />
                                                    </button>
                                                )}
                                                {canCancel && (
                                                    <button
                                                        onClick={() => requestCancel(job.id)}
                                                        disabled={cancellingJobId === job.id || job.status === 'CANCEL_REQUESTED'}
                                                        className="p-1 text-muted-foreground hover:text-amber-600 hover:bg-amber-50 rounded-md transition-colors disabled:opacity-50"
                                                        title={job.status === 'CANCEL_REQUESTED' ? t('jobs.cancelRequestedTitle') : t('jobs.cancelJob')}
                                                    >
                                                        <Square className="w-4 h-4" />
                                                    </button>
                                                )}
                                                <button
                                                    onClick={async () => {
                                                        setSelectedJob(job);
                                                        setLoadingAttempts(true);
                                                        try {
                                                            const rows = await getJobAttempts(job.id, 20);
                                                            setAttempts(rows);
                                                        } catch {
                                                            setAttempts([]);
                                                        } finally {
                                                            setLoadingAttempts(false);
                                                        }
                                                    }}
                                                    className="p-1 text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors"
                                                    title={t('jobs.viewDetails')}
                                                >
                                                    <Eye className="w-4 h-4" />
                                                </button>
                                                {canDelete && (
                                                    <button
                                                        onClick={() => triggerReprocess(job.id)}
                                                        disabled={reprocessingJobId === job.id}
                                                        className="p-1 text-muted-foreground hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors disabled:opacity-50"
                                                        title={t('jobs.reprocess')}
                                                    >
                                                        <RotateCcw className="w-4 h-4" />
                                                    </button>
                                                )}
                                                {canDelete && (
                                                    <button
                                                        onClick={() => removeJob(job.id)}
                                                        disabled={deletingJobId === job.id}
                                                        className="p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors disabled:opacity-50"
                                                        title={t('jobs.deleteHistory')}
                                                    >
                                                        <Trash2 className="w-4 h-4" />
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                        </div>
                    </div>
                )}

            </div>

            {/* Details Modal */}
            <Modal
                isOpen={!!selectedJob}
                onClose={() => setSelectedJob(null)}
                title={t('jobs.detailsTitle')}
            >
                {selectedJob && (
                    <div className="space-y-6">
                        <div className="flex items-center justify-between pb-4 border-b">
                            <div>
                                <span className="text-sm text-muted-foreground block mb-1">{t('jobs.status')}</span>
                                <div className={`status-badge ${getStatusTone(selectedJob.status)}`}>
                                    {getStatusIcon(selectedJob.status)}
                                    <span>{formatJobStatus(selectedJob.status, t)}</span>
                                </div>
                            </div>
                            <div className="text-right">
                                <span className="text-sm text-muted-foreground block mb-1">{t('jobs.type')}</span>
                                <span className="font-medium text-foreground">
                                    {formatJobType(selectedJob.type, t)}
                                </span>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <span className="text-sm text-muted-foreground block">{t('jobs.progress')}</span>
                            <div className="h-2 w-full bg-muted rounded-sm overflow-hidden">
                                <div
                                    className={`h-full ${selectedJob.status === 'FAILED' || selectedJob.status === 'DEAD_LETTER' ? 'bg-destructive' : 'bg-primary'}`}
                                    style={{ width: `${selectedProgressSummary?.completionPercent ?? 0}%` }}
                                />
                            </div>
                            <div className="text-xs text-muted-foreground tabular-nums">
                                {selectedProgressSummary?.hasKnownTotal && selectedProgressSummary.totalItems > 0
                                    ? `${selectedProgressSummary.processedDisplay}/${selectedProgressSummary.totalItems} (${selectedProgressSummary.completionPercent}%)`
                                    : `${selectedProgressSummary?.completionPercent ?? 0}%`}
                            </div>
                            <div className="text-xs text-muted-foreground">
                                {t('jobs.retry', { current: selectedJob.retry_count, max: selectedJob.max_retries })}
                            </div>
                            {selectedJob.next_retry_at && (
                                <div className="text-xs text-muted-foreground">
                                    {t('jobs.nextRetry', { value: formatDate(selectedJob.next_retry_at) })}
                                </div>
                            )}
                            {['PENDING', 'RETRY_SCHEDULED'].includes(selectedJob.status) && (
                                <div className="text-xs text-muted-foreground">
                                    {t('jobs.queue', {
                                        queue: selectedJob.queue_position ? `#${selectedJob.queue_position}` : '-',
                                        eta: formatDate(selectedJob.estimated_start_at),
                                        wait: formatDuration(selectedJob.estimated_wait_seconds),
                                    })}
                                </div>
                            )}
                            {selectedJob.dead_lettered_at && (
                                <div className="text-xs text-destructive">
                                    {t('jobs.deadLetter', { value: formatDate(selectedJob.dead_lettered_at) })}
                                </div>
                            )}
                            {selectedMetricSummary && (
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-2">
                                    <div className="rounded border bg-muted/30 px-2 py-1 text-xs">
                                        <div className="text-muted-foreground">{t('jobs.total')}</div>
                                        <div className="font-semibold tabular-nums">{selectedProgressSummary?.hasKnownTotal ? selectedProgressSummary.totalItems : '-'}</div>
                                    </div>
                                    <div className="status-badge status-badge-success rounded-sm px-2 py-1 text-xs">
                                        <div>{t('jobs.success')}</div>
                                        <div className="font-semibold tabular-nums">{selectedMetricSummary.success}</div>
                                    </div>
                                    <div className={`rounded-sm border px-2 py-1 text-xs ${selectedMetricSummary.failed > 0 ? 'status-badge-danger' : 'status-badge'}`}>
                                        <div>{t('jobs.failed')}</div>
                                        <div className="font-semibold tabular-nums">{selectedMetricSummary.failed}</div>
                                    </div>
                                    <div className="status-badge status-badge-warning rounded-sm px-2 py-1 text-xs">
                                        <div>{t('jobs.skipped')}</div>
                                        <div className="font-semibold tabular-nums">{selectedMetricSummary.skipped}</div>
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="rounded-2xl border border-border/70 bg-background/80 p-3">
                            <div className="text-sm font-medium">{t('jobs.relatedWorkspace')}</div>
                            <p className="mt-1 text-sm text-muted-foreground">{t('jobs.relatedWorkspaceHelp')}</p>
                            <div className="mt-3 flex flex-wrap gap-2">
                                <button
                                    type="button"
                                    className="workspace-action-button"
                                    onClick={() => {
                                        const target = getJobCrossLinkTarget(selectedJob, t);
                                        navigate(target.to, { state: target.state || null });
                                        setSelectedJob(null);
                                    }}
                                >
                                    {getJobCrossLinkTarget(selectedJob, t).label}
                                </button>
                                <button
                                    type="button"
                                    className="workspace-action-button workspace-action-button-primary"
                                    onClick={() => {
                                        navigate('/ai', {
                                            state: {
                                                assistantContext: {
                                                    title: formatJobType(selectedJob.type, t),
                                                    description: t('jobs.relatedWorkspaceHelp'),
                                                    entityType: 'jobs',
                                                    entityId: selectedJob.id,
                                                    selectedIds: [selectedJob.id],
                                                    activeFilters: [formatJobStatus(selectedJob.status, t)],
                                                    suggestedPrompts: [t('workspace.aiPrompts.jobReview')],
                                                },
                                            },
                                        });
                                        setSelectedJob(null);
                                    }}
                                >
                                    {t('jobs.askAi')}
                                </button>
                            </div>
                        </div>

                        <div>
                            <span className="text-sm font-medium mb-2 block">{t('jobs.payload')}</span>
                            <div className="bg-muted/30 p-3 rounded-md border text-xs font-mono overflow-auto max-h-40">
                                <pre className="whitespace-pre-wrap break-all text-muted-foreground">
                                    {JSON.stringify(selectedJob.payload, null, 2)}
                                </pre>
                            </div>
                        </div>

                        {selectedErrorText && (
                            <div>
                                <span className="text-sm font-medium text-destructive mb-2 flex items-center gap-2">
                                    <AlertTriangle className="w-4 h-4" />
                                    {t('jobs.errorDetails')}
                                </span>
                                <div className="bg-destructive/5 p-3 rounded-md border border-destructive/20 text-xs font-mono overflow-auto max-h-60 text-destructive">
                                    <pre className="whitespace-pre-wrap break-all">
                                        {selectedErrorText}
                                    </pre>
                                </div>
                            </div>
                        )}

                        {selectedErrorItems.length > 0 && (
                            <div>
                                <span className="text-sm font-medium text-destructive mb-2 flex items-center gap-2">
                                    <AlertTriangle className="w-4 h-4" />
                                    {t('jobs.itemDetails', {
                                        details: selectedErrorItemsTruncated > 0
                                            ? t('jobs.itemDetailsShowing', {
                                                shown: selectedErrorItems.length,
                                                hidden: selectedErrorItemsTruncated,
                                            })
                                            : t('jobs.itemDetailsCount', { count: selectedErrorItems.length }),
                                    })}
                                </span>
                                <div className="bg-destructive/5 p-3 rounded-md border border-destructive/20 text-xs overflow-auto max-h-72">
                                    <div className="space-y-2">
                                        {selectedErrorItems.map((entry) => (
                                            <div key={entry.key} className="rounded border border-destructive/20 bg-background/70 p-2">
                                                <div className="font-mono text-[11px] text-muted-foreground">
                                                    {entry.itemId ? t('jobs.itemId', { id: entry.itemId }) : t('jobs.itemIdMissing')}
                                                    {entry.itemName ? t('jobs.itemName', { name: entry.itemName }) : ''}
                                                    {entry.stage ? t('jobs.itemStage', { stage: entry.stage }) : ''}
                                                </div>
                                                <div className="mt-1 text-destructive break-all">
                                                    {entry.reason}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}

                        {selectedHasItemDetails && selectedErrorItems.length === 0 && !selectedErrorText && (
                            <div className="status-badge status-badge-warning rounded-sm px-3 py-2 text-xs">
                                {t('jobs.itemDetailsNoDetails')}
                            </div>
                        )}

                        {selectedJob.status === 'COMPLETED' && selectedJob.result && (
                            <div>
                                <span className="text-sm font-medium text-foreground mb-2 block">{t('jobs.result')}</span>
                                <div className="status-badge status-badge-success block p-3 rounded-sm text-xs font-mono overflow-auto max-h-60">
                                    <pre className="whitespace-pre-wrap break-all">
                                        {JSON.stringify(selectedJob.result, null, 2)}
                                    </pre>
                                </div>
                            </div>
                        )}

                        {selectedJob.metrics && (
                            <div>
                                <span className="text-sm font-medium mb-2 block">{t('jobs.metrics')}</span>
                                <div className="bg-muted/30 p-3 rounded-md border text-xs font-mono overflow-auto max-h-60">
                                    <pre className="whitespace-pre-wrap break-all text-muted-foreground">
                                        {JSON.stringify(selectedJob.metrics, null, 2)}
                                    </pre>
                                </div>
                            </div>
                        )}

                        <div>
                            <span className="text-sm font-medium mb-2 block">{t('jobs.attemptHistory')}</span>
                            <div className="bg-muted/30 p-3 rounded-md border text-xs overflow-auto max-h-60">
                                {loadingAttempts ? (
                                    <div className="text-muted-foreground">{t('jobs.loadingAttempts')}</div>
                                ) : attempts.length === 0 ? (
                                    <div className="text-muted-foreground">{t('jobs.noAttempts')}</div>
                                ) : (
                                    <div className="space-y-2">
                                        {attempts.map((attempt) => (
                                            <div key={attempt.id} className="border rounded p-2 bg-background">
                                                <div className="font-medium text-foreground">
                                                    {t('jobs.attempt', { number: attempt.attempt_number, status: formatJobStatus(attempt.status, t) })}
                                                </div>
                                                <div className="text-muted-foreground">
                                                    {t('jobs.attemptLine', {
                                                        started: formatDate(attempt.started_at),
                                                        finished: formatDate(attempt.completed_at),
                                                        duration: attempt.duration_seconds ?? '-',
                                                    })}
                                                </div>
                                                {attempt.error && (
                                                    <pre className="whitespace-pre-wrap break-all text-destructive mt-1">{attempt.error}</pre>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </Modal>
        </div>
    );
}
