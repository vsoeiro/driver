import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, CheckCircle, XCircle, Clock, PlayCircle, Eye, AlertTriangle, Undo2, Trash2, Square, RotateCcw, ChevronLeft, ChevronRight } from 'lucide-react';
import { cancelJob, createMetadataUndoJob, deleteJob, getJobAttempts, getJobs, reprocessJob } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';
import Modal from '../components/Modal';
import { formatJobStatus, formatJobType } from '../utils/jobLabels';

const DATE_RANGE_MS = {
    '24h': 24 * 60 * 60 * 1000,
    '3d': 3 * 24 * 60 * 60 * 1000,
    '7d': 7 * 24 * 60 * 60 * 1000,
    '30d': 30 * 24 * 60 * 60 * 1000,
    '90d': 90 * 24 * 60 * 60 * 1000,
};

export default function Jobs() {
    const [jobs, setJobs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const [hasNextPage, setHasNextPage] = useState(false);
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
    const PAGE_SIZE = 20;

    const DATE_RANGE_OPTIONS = [
        { value: 'ALL', label: 'All time' },
        { value: '24h', label: 'Last 24h', hours: 24 },
        { value: '3d', label: 'Last 3 days', days: 3 },
        { value: '7d', label: 'Last 7 days', days: 7 },
        { value: '30d', label: 'Last 30 days', days: 30 },
        { value: '90d', label: 'Last 90 days', days: 90 },
    ];

    const JOB_TYPE_OPTIONS = [
        { value: 'ALL', label: 'All types' },
        { value: 'sync_items', label: 'Sync Items' },
        { value: 'move_items', label: 'Move Items' },
        { value: 'upload_file', label: 'Upload File' },
        { value: 'update_metadata', label: 'Update Metadata' },
        { value: 'apply_metadata_recursive', label: 'Apply Metadata Recursive' },
        { value: 'remove_metadata_recursive', label: 'Remove Metadata Recursive' },
        { value: 'undo_metadata_batch', label: 'Undo Metadata Batch' },
        { value: 'apply_metadata_rule', label: 'Apply Metadata Rule' },
        { value: 'extract_comic_assets', label: 'Extract Comic Assets' },
        { value: 'extract_library_comic_assets', label: 'Extract Library Comic Assets' },
        { value: 'reindex_comic_covers', label: 'Reindex Comic Covers' },
    ];

    const fetchJobs = useCallback(async (
        pageNumber = page,
        statusValue = statusFilter,
        typeValue = typeFilter,
        dateRangeValue = dateRangeFilter
    ) => {
        setLoading(true);
        try {
            const parsedPage = Number(pageNumber);
            const safePage = Number.isFinite(parsedPage) && parsedPage > 0 ? Math.floor(parsedPage) : page;
            const offset = (safePage - 1) * PAGE_SIZE;
            const statuses = statusValue === 'ALL' ? [] : [statusValue];
            const types = typeValue === 'ALL' ? [] : [typeValue];
            const deltaMs = DATE_RANGE_MS[dateRangeValue] || 0;
            const createdAfter = deltaMs > 0 ? new Date(Date.now() - deltaMs).toISOString() : null;
            const data = await getJobs(PAGE_SIZE, offset, statuses, { types, createdAfter });
            setJobs(data);
            setHasNextPage(data.length === PAGE_SIZE);
        } catch (error) {
            console.error('Failed to load jobs:', error);
            showToast('Failed to load jobs', 'error');
        } finally {
            setLoading(false);
        }
    }, [showToast, page, statusFilter, typeFilter, dateRangeFilter]);

    useEffect(() => {
        fetchJobs(page, statusFilter, typeFilter, dateRangeFilter);
        const interval = setInterval(() => fetchJobs(page, statusFilter, typeFilter, dateRangeFilter), 5000); // Poll every 5 seconds
        return () => clearInterval(interval);
    }, [fetchJobs, page, statusFilter, typeFilter, dateRangeFilter]);

    const goToPreviousPage = () => {
        if (page <= 1) return;
        const nextPage = page - 1;
        setPage(nextPage);
        fetchJobs(nextPage, statusFilter, typeFilter, dateRangeFilter);
    };

    const goToNextPage = () => {
        if (!hasNextPage) return;
        const nextPage = page + 1;
        setPage(nextPage);
        fetchJobs(nextPage, statusFilter, typeFilter, dateRangeFilter);
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
            showToast(`Undo job created for batch ${batchId.slice(0, 8)}...`, 'success');
            fetchJobs();
        } catch {
            showToast('Failed to create undo job', 'error');
        } finally {
            setUndoingBatchId(null);
        }
    };

    const removeJob = async (jobId) => {
        setDeletingJobId(jobId);
        try {
            await deleteJob(jobId);
            setJobs((prev) => prev.filter((job) => job.id !== jobId));
            if (selectedJob?.id === jobId) setSelectedJob(null);
            showToast('Job removed from history', 'success');
        } catch {
            showToast('Failed to remove job', 'error');
        } finally {
            setDeletingJobId(null);
        }
    };

    const requestCancel = async (jobId) => {
        setCancellingJobId(jobId);
        try {
            await cancelJob(jobId);
            setJobs((prev) =>
                prev.map((job) =>
                    job.id === jobId
                        ? {
                            ...job,
                            status: 'CANCELLED',
                        }
                        : job
                )
            );
            showToast('Cancellation requested', 'success');
            fetchJobs();
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to cancel job';
            showToast(message, 'error');
        } finally {
            setCancellingJobId(null);
        }
    };

    const triggerReprocess = async (jobId) => {
        setReprocessingJobId(jobId);
        try {
            const cloned = await reprocessJob(jobId);
            showToast(`Reprocess queued (${cloned.id})`, 'success');
            fetchJobs();
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to reprocess job';
            showToast(message, 'error');
        } finally {
            setReprocessingJobId(null);
        }
    };

    const formatDate = (dateString) => {
        if (!dateString) return '-';
        return new Date(dateString).toLocaleDateString('en-GB', {
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
                    <h1 className="page-title">Background Jobs</h1>
                    <p className="page-subtitle">Queue status, progress and troubleshooting details.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <select
                        className="input-shell px-2 py-1.5 text-sm"
                        value={statusFilter}
                        onChange={(event) => {
                            const nextStatus = event.target.value;
                            setStatusFilter(nextStatus);
                            setPage(1);
                            fetchJobs(1, nextStatus, typeFilter, dateRangeFilter);
                        }}
                    >
                        <option value="ALL">All status</option>
                        <option value="PENDING">Pending</option>
                        <option value="RUNNING">Running</option>
                        <option value="RETRY_SCHEDULED">Retry Scheduled</option>
                        <option value="COMPLETED">Completed</option>
                        <option value="FAILED">Failed</option>
                        <option value="DEAD_LETTER">Dead Letter</option>
                        <option value="CANCELLED">Cancelled</option>
                    </select>
                    <select
                        className="input-shell px-2 py-1.5 text-sm"
                        value={typeFilter}
                        onChange={(event) => {
                            const nextType = event.target.value;
                            setTypeFilter(nextType);
                            setPage(1);
                            fetchJobs(1, statusFilter, nextType, dateRangeFilter);
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
                            fetchJobs(1, statusFilter, typeFilter, nextRange);
                        }}
                    >
                        {DATE_RANGE_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                    </select>
                    <span className="status-chip">Page {page}</span>
                    <div className="flex gap-1">
                        <button
                            onClick={goToPreviousPage}
                            disabled={page <= 1 || loading}
                            className="ghost-icon-button p-1 disabled:opacity-50"
                            title="Previous page"
                        >
                            <ChevronLeft size={16} />
                        </button>
                        <button
                            onClick={goToNextPage}
                            disabled={!hasNextPage || loading}
                            className="ghost-icon-button p-1 disabled:opacity-50"
                            title="Next page"
                        >
                            <ChevronRight size={16} />
                        </button>
                    </div>
                    <button
                        onClick={() => fetchJobs()}
                        className="btn-refresh px-2.5"
                        title="Refresh"
                    >
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-auto">
                {jobs.length === 0 && !loading ? (
                    <div className="empty-state">
                        <div className="empty-state-title">No jobs found</div>
                        <p className="empty-state-text">Try changing the filters or wait for new background activity.</p>
                    </div>
                ) : (
                    <div className="surface-card overflow-x-auto">
                        <div className="min-w-[1660px]">
                            <div className="grid grid-cols-[120px_120px_1fr_140px_140px_140px_100px_150px_120px_72px_72px_72px_72px_78px] gap-4 p-3 border-b border-border/70 bg-muted/45 text-xs font-medium text-muted-foreground uppercase tracking-wider items-center">
                                <div>Status</div>
                                <div>Job ID</div>
                                <div>Type</div>
                                <div className="text-right">Created</div>
                                <div className="text-right">Started</div>
                                <div className="text-right">Finished</div>
                                <div className="text-right">Duration</div>
                                <div>ETA</div>
                                <div>Progress</div>
                                <div className="text-right">Total</div>
                                <div className="text-right">Success</div>
                                <div className="text-right">Failed</div>
                                <div className="text-right">Skipped</div>
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
                                            className="grid grid-cols-[120px_120px_1fr_140px_140px_140px_100px_150px_120px_72px_72px_72px_72px_78px] gap-4 p-3 items-center hover:bg-accent/35 transition-colors pointer-events-none"
                                        >
                                        <div className="pointer-events-auto">
                                            <div className={`inline-flex items-center gap-2 font-medium ${job.status === 'COMPLETED' ? 'text-green-600' :
                                                job.status === 'FAILED' || job.status === 'DEAD_LETTER' ? 'text-red-500' :
                                                    job.status === 'RUNNING' ? 'text-blue-500' :
                                                        job.status === 'CANCEL_REQUESTED' ? 'text-amber-600' :
                                                            job.status === 'CANCELLED' ? 'text-zinc-500' : 'text-zinc-500'
                                                }`}>
                                                {getStatusIcon(job.status)}
                                                <span>{formatJobStatus(job.status)}</span>
                                            </div>
                                        </div>
                                        <div className="pointer-events-auto font-mono text-xs text-muted-foreground truncate" title={job.id}>
                                            {String(job.id).slice(0, 8)}...
                                        </div>
                                        <div className="font-medium text-foreground truncate pointer-events-auto">
                                            {formatJobType(job.type)}
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
                                                    start: {formatDate(job.estimated_start_at)}
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
                                                        title="Undo Batch"
                                                    >
                                                        <Undo2 className="w-4 h-4" />
                                                    </button>
                                                )}
                                                {canCancel && (
                                                    <button
                                                        onClick={() => requestCancel(job.id)}
                                                        disabled={cancellingJobId === job.id || job.status === 'CANCEL_REQUESTED'}
                                                        className="p-1 text-muted-foreground hover:text-amber-600 hover:bg-amber-50 rounded-md transition-colors disabled:opacity-50"
                                                        title={job.status === 'CANCEL_REQUESTED' ? 'Cancellation requested' : 'Cancel job'}
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
                                                    title="View Details"
                                                >
                                                    <Eye className="w-4 h-4" />
                                                </button>
                                                {canDelete && (
                                                    <button
                                                        onClick={() => triggerReprocess(job.id)}
                                                        disabled={reprocessingJobId === job.id}
                                                        className="p-1 text-muted-foreground hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors disabled:opacity-50"
                                                        title="Reprocess job"
                                                    >
                                                        <RotateCcw className="w-4 h-4" />
                                                    </button>
                                                )}
                                                {canDelete && (
                                                    <button
                                                        onClick={() => removeJob(job.id)}
                                                        disabled={deletingJobId === job.id}
                                                        className="p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors disabled:opacity-50"
                                                        title="Delete from history"
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
                title="Job Details"
            >
                {selectedJob && (
                    <div className="space-y-6">
                        <div className="flex items-center justify-between pb-4 border-b">
                            <div>
                                <span className="text-sm text-muted-foreground block mb-1">Status</span>
                                <div className={`flex items-center gap-2 font-medium ${selectedJob.status === 'COMPLETED' ? 'text-green-600' :
                                    selectedJob.status === 'FAILED' || selectedJob.status === 'DEAD_LETTER' ? 'text-red-500' :
                                        selectedJob.status === 'RUNNING' ? 'text-blue-500' :
                                            selectedJob.status === 'CANCEL_REQUESTED' ? 'text-amber-600' :
                                                selectedJob.status === 'CANCELLED' ? 'text-zinc-500' : 'text-zinc-500'
                                    }`}>
                                    {getStatusIcon(selectedJob.status)}
                                    <span>{formatJobStatus(selectedJob.status)}</span>
                                </div>
                            </div>
                            <div className="text-right">
                                <span className="text-sm text-muted-foreground block mb-1">Type</span>
                                <span className="font-medium text-foreground">
                                    {formatJobType(selectedJob.type)}
                                </span>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <span className="text-sm text-muted-foreground block">Progress</span>
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
                                Retry: {selectedJob.retry_count}/{selectedJob.max_retries}
                            </div>
                            {selectedJob.next_retry_at && (
                                <div className="text-xs text-amber-600">
                                    Next retry: {formatDate(selectedJob.next_retry_at)}
                                </div>
                            )}
                            {['PENDING', 'RETRY_SCHEDULED'].includes(selectedJob.status) && (
                                <div className="text-xs text-muted-foreground">
                                    Queue: {selectedJob.queue_position ? `#${selectedJob.queue_position}` : '-'} | ETA start: {formatDate(selectedJob.estimated_start_at)} | Wait: {formatDuration(selectedJob.estimated_wait_seconds)}
                                </div>
                            )}
                            {selectedJob.dead_lettered_at && (
                                <div className="text-xs text-red-600">
                                    Dead Letter: {formatDate(selectedJob.dead_lettered_at)}
                                </div>
                            )}
                            {selectedMetricSummary && (
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-2">
                                    <div className="rounded border bg-muted/30 px-2 py-1 text-xs">
                                        <div className="text-muted-foreground">Total</div>
                                        <div className="font-semibold tabular-nums">{selectedMetricSummary.total}</div>
                                    </div>
                                    <div className="rounded border border-emerald-500/30 bg-emerald-500/5 px-2 py-1 text-xs">
                                        <div className="text-emerald-700">Success</div>
                                        <div className="font-semibold tabular-nums text-emerald-700">{selectedMetricSummary.success}</div>
                                    </div>
                                    <div className={`rounded border px-2 py-1 text-xs ${selectedMetricSummary.failed > 0 ? 'border-red-500/30 bg-red-500/5' : 'border-muted bg-muted/20'}`}>
                                        <div className={selectedMetricSummary.failed > 0 ? 'text-red-700' : 'text-muted-foreground'}>Failed</div>
                                        <div className={`font-semibold tabular-nums ${selectedMetricSummary.failed > 0 ? 'text-red-700' : 'text-muted-foreground'}`}>{selectedMetricSummary.failed}</div>
                                    </div>
                                    <div className="rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1 text-xs">
                                        <div className="text-amber-700">Skipped</div>
                                        <div className="font-semibold tabular-nums text-amber-700">{selectedMetricSummary.skipped}</div>
                                    </div>
                                </div>
                            )}
                        </div>

                        <div>
                            <span className="text-sm font-medium mb-2 block">Payload</span>
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
                                    Error Details
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
                                    Failed Items {selectedErrorItemsTruncated > 0 ? `(showing ${selectedErrorItems.length}, +${selectedErrorItemsTruncated} hidden)` : `(${selectedErrorItems.length})`}
                                </span>
                                <div className="bg-destructive/5 p-3 rounded-md border border-destructive/20 text-xs overflow-auto max-h-72">
                                    <div className="space-y-2">
                                        {selectedErrorItems.map((entry) => (
                                            <div key={entry.key} className="rounded border border-destructive/20 bg-background/70 p-2">
                                                <div className="font-mono text-[11px] text-muted-foreground">
                                                    {entry.itemId ? `item_id: ${entry.itemId}` : 'item_id: -'}
                                                    {entry.itemName ? ` | name: ${entry.itemName}` : ''}
                                                    {entry.stage ? ` | stage: ${entry.stage}` : ''}
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
                                Failed items were counted, but no per-item error details were persisted for this job execution.
                            </div>
                        )}

                        {selectedJob.status === 'COMPLETED' && selectedJob.result && (
                            <div>
                                <span className="text-sm font-medium text-green-600 mb-2 block">Result</span>
                                <div className="bg-green-500/5 p-3 rounded-md border border-green-500/20 text-xs font-mono overflow-auto max-h-60 text-green-600">
                                    <pre className="whitespace-pre-wrap break-all">
                                        {JSON.stringify(selectedJob.result, null, 2)}
                                    </pre>
                                </div>
                            </div>
                        )}

                        {selectedJob.metrics && (
                            <div>
                                <span className="text-sm font-medium mb-2 block">Metrics</span>
                                <div className="bg-muted/30 p-3 rounded-md border text-xs font-mono overflow-auto max-h-60">
                                    <pre className="whitespace-pre-wrap break-all text-muted-foreground">
                                        {JSON.stringify(selectedJob.metrics, null, 2)}
                                    </pre>
                                </div>
                            </div>
                        )}

                        <div>
                            <span className="text-sm font-medium mb-2 block">Attempt History</span>
                            <div className="bg-muted/30 p-3 rounded-md border text-xs overflow-auto max-h-60">
                                {loadingAttempts ? (
                                    <div className="text-muted-foreground">Loading attempts...</div>
                                ) : attempts.length === 0 ? (
                                    <div className="text-muted-foreground">No attempts recorded.</div>
                                ) : (
                                    <div className="space-y-2">
                                        {attempts.map((attempt) => (
                                            <div key={attempt.id} className="border rounded p-2 bg-background">
                                                <div className="font-medium text-foreground">
                                                    Attempt #{attempt.attempt_number} - {formatJobStatus(attempt.status)}
                                                </div>
                                                <div className="text-muted-foreground">
                                                    Started: {formatDate(attempt.started_at)} | Finished: {formatDate(attempt.completed_at)} | Duration: {attempt.duration_seconds ?? '-'}s
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
