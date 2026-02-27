import { useEffect, useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCw, CheckCircle, XCircle, Clock, PlayCircle, Eye, AlertTriangle, Undo2, Trash2, Square, RotateCcw, ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cancelJob, createMetadataUndoJob, deleteJob, getJobAttempts, getJobs, reprocessJob } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';
import Modal from '../components/Modal';
import { formatJobStatus, formatJobType } from '../utils/jobLabels';
import { usePolling } from '../hooks/usePolling';

const DATE_RANGE_MS = {
    '24h': 24 * 60 * 60 * 1000,
    '3d': 3 * 24 * 60 * 60 * 1000,
    '7d': 7 * 24 * 60 * 60 * 1000,
    '30d': 30 * 24 * 60 * 60 * 1000,
    '90d': 90 * 24 * 60 * 60 * 1000,
};

export default function Jobs() {
    const { t, i18n } = useTranslation();
    const [page, setPage] = useState(1);
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
    const { showToast } = useToast();
    const queryClient = useQueryClient();
    const PAGE_SIZE = 20;

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
        { value: 'update_metadata', label: t('jobs.typeOptions.update_metadata') },
        { value: 'apply_metadata_recursive', label: t('jobs.typeOptions.apply_metadata_recursive') },
        { value: 'remove_metadata_recursive', label: t('jobs.typeOptions.remove_metadata_recursive') },
        { value: 'undo_metadata_batch', label: t('jobs.typeOptions.undo_metadata_batch') },
        { value: 'apply_metadata_rule', label: t('jobs.typeOptions.apply_metadata_rule') },
        { value: 'extract_comic_assets', label: t('jobs.typeOptions.extract_comic_assets') },
        { value: 'extract_library_comic_assets', label: t('jobs.typeOptions.extract_library_comic_assets') },
        { value: 'reindex_comic_covers', label: t('jobs.typeOptions.reindex_comic_covers') },
        { value: 'remove_duplicate_files', label: t('jobs.typeOptions.remove_duplicate_files') },
    ];

    const queryKey = useMemo(
        () => ['jobs', page, statusFilter, typeFilter, dateRangeFilter],
        [dateRangeFilter, page, statusFilter, typeFilter],
    );
    const {
        data: jobs = [],
        isLoading,
        isFetching,
        error,
        refetch,
    } = useQuery({
        queryKey,
        queryFn: async () => {
            const offset = (page - 1) * PAGE_SIZE;
            const statuses = statusFilter === 'ALL' ? [] : [statusFilter];
            const types = typeFilter === 'ALL' ? [] : [typeFilter];
            const deltaMs = DATE_RANGE_MS[dateRangeFilter] || 0;
            const createdAfter = deltaMs > 0 ? new Date(Date.now() - deltaMs).toISOString() : null;
            return getJobs(PAGE_SIZE, offset, statuses, { types, createdAfter });
        },
        staleTime: 5000,
    });
    const loading = isLoading;
    const refreshing = isFetching && !isLoading;
    const hasNextPage = jobs.length === PAGE_SIZE;

    useEffect(() => {
        if (error) {
            showToast(t('jobs.failedLoad'), 'error');
        }
    }, [error, showToast, t]);

    usePolling({
        callback: () => refetch(),
        intervalMs: 10000,
        enabled: true,
        pauseWhenHidden: true,
        runImmediately: false,
    });

    const goToPreviousPage = () => {
        if (page <= 1) return;
        setPage((current) => current - 1);
    };

    const goToNextPage = () => {
        if (!hasNextPage) return;
        setPage((current) => current + 1);
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

    const formatDate = (dateString) => {
        if (!dateString) return '-';
        return new Date(dateString).toLocaleDateString(i18n.language, {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
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

    const pickMetricNumber = (source, keys) => {
        if (!source || typeof source !== 'object') return 0;
        for (const key of keys) {
            const value = source[key];
            if (typeof value === 'number' && Number.isFinite(value)) {
                return Math.trunc(value);
            }
        }
        return 0;
    };

    const getMetricSummary = (job) => {
        const metrics = job?.metrics && typeof job.metrics === 'object' ? job.metrics : {};
        const result = job?.result && typeof job.result === 'object' ? job.result : {};
        const success = pickMetricNumber(metrics, ['success', 'mapped', 'updated', 'changed']) || pickMetricNumber(result, ['success', 'mapped', 'updated', 'changed']);
        const failed = pickMetricNumber(metrics, ['failed', 'errors']) || pickMetricNumber(result, ['failed', 'errors']);
        const skipped = pickMetricNumber(metrics, ['skipped', 'unchanged']) || pickMetricNumber(result, ['skipped', 'unchanged']);
        const explicitTotal = pickMetricNumber(metrics, ['total']) || pickMetricNumber(result, ['total']);
        const derivedTotal = success + failed + skipped;
        return {
            total: explicitTotal > 0 ? explicitTotal : derivedTotal,
            success,
            failed,
            skipped,
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

    const selectedMetricSummary = selectedJob ? getMetricSummary(selectedJob) : null;
    const selectedErrorText = selectedJob ? getJobErrorText(selectedJob, attempts) : null;
    const selectedErrorItems = selectedJob ? normalizeErrorItems(selectedJob) : [];
    const selectedErrorItemsTruncated = selectedJob ? getErrorItemsTruncated(selectedJob) : 0;

    return (
        <div className="app-page">
            <div className="page-header flex flex-wrap items-start justify-between gap-3">
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
                    <div className="surface-card overflow-x-auto">
                        <div className="min-w-[1380px]">
                            <div className="grid grid-cols-[112px_110px_1fr_132px_132px_132px_95px_130px_110px_68px_68px_68px_68px_78px] gap-3 p-3 border-b border-border/70 bg-muted/45 text-xs font-medium text-muted-foreground uppercase tracking-wider items-center">
                                <div>{t('jobs.status')}</div>
                                <div>{t('jobs.jobId')}</div>
                                <div>{t('jobs.type')}</div>
                                <div className="text-right">{t('jobs.created')}</div>
                                <div className="text-right">{t('jobs.started')}</div>
                                <div className="text-right">{t('jobs.finished')}</div>
                                <div className="text-right">{t('jobs.duration')}</div>
                                <div>{t('jobs.eta')}</div>
                                <div>{t('jobs.progress')}</div>
                                <div className="text-right">{t('jobs.total')}</div>
                                <div className="text-right">{t('jobs.success')}</div>
                                <div className="text-right">{t('jobs.failed')}</div>
                                <div className="text-right">{t('jobs.skipped')}</div>
                                <div className="text-center"></div>
                            </div>

                            <div className="divide-y text-sm">
                                {jobs.map((job) => {
                                const started = job.started_at ? new Date(job.started_at) : null;
                                const completed = job.completed_at ? new Date(job.completed_at) : null;
                                const duration = started && completed
                                    ? ((completed - started) / 1000).toFixed(1) + 's'
                                    : '-';
                                const finishedAt = job.completed_at || job.dead_lettered_at || null;
                                const progressPercent = job.progress_percent ?? 0;
                                const metricSummary = getMetricSummary(job);
                                const isQueued = ['PENDING', 'RETRY_SCHEDULED'].includes(job.status);
                                const etaText = isQueued
                                    ? `~${formatDuration(job.estimated_wait_seconds)} (${job.queue_position ? `#${job.queue_position}` : '-'})`
                                    : '-';
                                const canUndo = job.status === 'COMPLETED' && job.result?.batch_id;
                                const canDelete = ['COMPLETED', 'FAILED', 'DEAD_LETTER', 'CANCELLED'].includes(job.status);
                                const canCancel = ['PENDING', 'RUNNING', 'RETRY_SCHEDULED', 'CANCEL_REQUESTED'].includes(job.status);

                                    return (
                                        <div
                                            key={job.id}
                                            className="grid grid-cols-[112px_110px_1fr_132px_132px_132px_95px_130px_110px_68px_68px_68px_68px_78px] gap-3 p-3 items-center hover:bg-accent/35 transition-colors pointer-events-none"
                                        >
                                        <div className="pointer-events-auto">
                                            <div className={`inline-flex items-center gap-2 font-medium ${job.status === 'COMPLETED' ? 'text-green-600' :
                                                job.status === 'FAILED' || job.status === 'DEAD_LETTER' ? 'text-red-500' :
                                                    job.status === 'RUNNING' ? 'text-blue-500' :
                                                        job.status === 'CANCEL_REQUESTED' ? 'text-amber-600' :
                                                            job.status === 'CANCELLED' ? 'text-zinc-500' : 'text-zinc-500'
                                                }`}>
                                                {getStatusIcon(job.status)}
                                                <span>{formatJobStatus(job.status, t)}</span>
                                            </div>
                                        </div>
                                        <div className="pointer-events-auto font-mono text-xs text-muted-foreground truncate" title={job.id}>
                                            {String(job.id).slice(0, 8)}...
                                        </div>
                                        <div className="font-medium text-foreground truncate pointer-events-auto">
                                            {formatJobType(job.type, t)}
                                        </div>
                                        <div className="text-right text-muted-foreground tabular-nums pointer-events-auto">
                                            {formatDate(job.created_at)}
                                        </div>
                                        <div className="text-right text-muted-foreground tabular-nums pointer-events-auto">
                                            {formatDate(job.started_at)}
                                        </div>
                                        <div className="text-right text-muted-foreground tabular-nums pointer-events-auto">
                                            {formatDate(finishedAt)}
                                        </div>
                                        <div className="text-right text-muted-foreground tabular-nums font-mono pointer-events-auto">
                                            {duration}
                                        </div>
                                        <div className="text-xs text-muted-foreground pointer-events-auto tabular-nums leading-5">
                                            <div>{etaText}</div>
                                            {isQueued && (
                                                <div>
                                                    {t('jobs.started')}: {formatDate(job.estimated_start_at)}
                                                </div>
                                            )}
                                        </div>
                                        <div className="pointer-events-auto">
                                            <div className="h-2 w-full bg-muted rounded overflow-hidden">
                                                <div
                                                    className={`h-full ${job.status === 'FAILED' || job.status === 'DEAD_LETTER' ? 'bg-red-500' : 'bg-primary'}`}
                                                    style={{ width: `${Math.max(0, Math.min(100, progressPercent))}%` }}
                                                />
                                            </div>
                                            <div className="text-xs text-muted-foreground mt-1">
                                                {progressPercent}%
                                            </div>
                                        </div>
                                        <div className="text-right text-xs tabular-nums text-foreground pointer-events-auto">
                                            {metricSummary.total}
                                        </div>
                                        <div className="text-right text-xs tabular-nums text-emerald-600 pointer-events-auto">
                                            {metricSummary.success}
                                        </div>
                                        <div className={`text-right text-xs tabular-nums pointer-events-auto ${metricSummary.failed > 0 ? 'text-red-600 font-semibold' : 'text-muted-foreground'}`}>
                                            {metricSummary.failed}
                                        </div>
                                        <div className="text-right text-xs tabular-nums text-amber-600 pointer-events-auto">
                                            {metricSummary.skipped}
                                        </div>
                                        <div className="text-right pointer-events-auto">
                                            <div className="flex items-center justify-end gap-1">
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
                                <div className={`flex items-center gap-2 font-medium ${selectedJob.status === 'COMPLETED' ? 'text-green-600' :
                                    selectedJob.status === 'FAILED' || selectedJob.status === 'DEAD_LETTER' ? 'text-red-500' :
                                        selectedJob.status === 'RUNNING' ? 'text-blue-500' :
                                            selectedJob.status === 'CANCEL_REQUESTED' ? 'text-amber-600' :
                                                selectedJob.status === 'CANCELLED' ? 'text-zinc-500' : 'text-zinc-500'
                                    }`}>
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
                            <div className="h-2 w-full bg-muted rounded overflow-hidden">
                                <div
                                    className={`h-full ${selectedJob.status === 'FAILED' || selectedJob.status === 'DEAD_LETTER' ? 'bg-red-500' : 'bg-primary'}`}
                                    style={{ width: `${Math.max(0, Math.min(100, selectedJob.progress_percent ?? 0))}%` }}
                                />
                            </div>
                            <div className="text-xs text-muted-foreground">
                                {selectedJob.progress_percent ?? 0}%
                            </div>
                            <div className="text-xs text-muted-foreground">
                                {t('jobs.retry', { current: selectedJob.retry_count, max: selectedJob.max_retries })}
                            </div>
                            {selectedJob.next_retry_at && (
                                <div className="text-xs text-amber-600">
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
                                <div className="text-xs text-red-600">
                                    {t('jobs.deadLetter', { value: formatDate(selectedJob.dead_lettered_at) })}
                                </div>
                            )}
                            {selectedMetricSummary && (
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-2">
                                    <div className="rounded border bg-muted/30 px-2 py-1 text-xs">
                                        <div className="text-muted-foreground">{t('jobs.total')}</div>
                                        <div className="font-semibold tabular-nums">{selectedMetricSummary.total}</div>
                                    </div>
                                    <div className="rounded border border-emerald-500/30 bg-emerald-500/5 px-2 py-1 text-xs">
                                        <div className="text-emerald-700">{t('jobs.success')}</div>
                                        <div className="font-semibold tabular-nums text-emerald-700">{selectedMetricSummary.success}</div>
                                    </div>
                                    <div className={`rounded border px-2 py-1 text-xs ${selectedMetricSummary.failed > 0 ? 'border-red-500/30 bg-red-500/5' : 'border-muted bg-muted/20'}`}>
                                        <div className={selectedMetricSummary.failed > 0 ? 'text-red-700' : 'text-muted-foreground'}>{t('jobs.failed')}</div>
                                        <div className={`font-semibold tabular-nums ${selectedMetricSummary.failed > 0 ? 'text-red-700' : 'text-muted-foreground'}`}>{selectedMetricSummary.failed}</div>
                                    </div>
                                    <div className="rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1 text-xs">
                                        <div className="text-amber-700">{t('jobs.skipped')}</div>
                                        <div className="font-semibold tabular-nums text-amber-700">{selectedMetricSummary.skipped}</div>
                                    </div>
                                </div>
                            )}
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
                                    {t('jobs.failedItems', {
                                        details: selectedErrorItemsTruncated > 0
                                            ? t('jobs.failedItemsShowing', {
                                                shown: selectedErrorItems.length,
                                                hidden: selectedErrorItemsTruncated,
                                            })
                                            : t('jobs.failedItemsCount', { count: selectedErrorItems.length }),
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

                        {selectedMetricSummary && selectedMetricSummary.failed > 0 && selectedErrorItems.length === 0 && !selectedErrorText && (
                            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700">
                                {t('jobs.failedItemsNoDetails')}
                            </div>
                        )}

                        {selectedJob.status === 'COMPLETED' && selectedJob.result && (
                            <div>
                                <span className="text-sm font-medium text-green-600 mb-2 block">{t('jobs.result')}</span>
                                <div className="bg-green-500/5 p-3 rounded-md border border-green-500/20 text-xs font-mono overflow-auto max-h-60 text-green-600">
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
