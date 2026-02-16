import React, { useState, useEffect } from 'react';
import { RefreshCw, CheckCircle, XCircle, Clock, PlayCircle, Eye, AlertTriangle, Undo2, Trash2 } from 'lucide-react';
import { createMetadataUndoJob, deleteJob, getJobs } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';
import Modal from '../components/Modal';

export default function Jobs() {
    const [jobs, setJobs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedJob, setSelectedJob] = useState(null);
    const [undoingBatchId, setUndoingBatchId] = useState(null);
    const [deletingJobId, setDeletingJobId] = useState(null);
    const { showToast } = useToast();

    const fetchJobs = async () => {
        setLoading(true);
        try {
            const data = await getJobs();
            setJobs(data);
        } catch (error) {
            console.error('Failed to load jobs:', error);
            showToast('Failed to load jobs', 'error');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchJobs();
        const interval = setInterval(fetchJobs, 5000); // Poll every 5 seconds
        return () => clearInterval(interval);
    }, []);

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
        } catch (error) {
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
        } catch (error) {
            showToast('Failed to remove job', 'error');
        } finally {
            setDeletingJobId(null);
        }
    };

    const formatDate = (dateString) => {
        if (!dateString) return '-';
        const date = new Date(dateString);
        return new Date(dateString).toLocaleDateString('en-GB', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    return (
        <div className="flex flex-col h-screen">
            <div className="p-4 border-b flex items-center justify-between bg-background z-10 sticky top-0 h-16">
                <div>
                    <h1 className="text-lg font-semibold text-foreground">Background Jobs</h1>
                </div>
                <button
                    onClick={fetchJobs}
                    className="p-2 hover:bg-accent rounded-md text-muted-foreground hover:text-foreground transition-colors"
                    title="Refresh"
                >
                    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>

            <div className="flex-1 overflow-auto p-4">
                {jobs.length === 0 && !loading ? (
                    <div className="text-center p-12 text-muted-foreground">
                        No jobs found.
                    </div>
                ) : (
                    <div className="border rounded-lg overflow-hidden bg-card">
                        <div className="grid grid-cols-[130px_1fr_170px_110px_150px_78px] gap-4 p-3 border-b bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider items-center">
                            <div>Status</div>
                            <div>Type</div>
                            <div className="text-right">Created</div>
                            <div className="text-right">Duration</div>
                            <div>Progress</div>
                            <div className="text-center"></div>
                        </div>

                        <div className="divide-y text-sm">
                            {jobs.map((job) => {
                                const started = job.started_at ? new Date(job.started_at) : null;
                                const completed = job.completed_at ? new Date(job.completed_at) : null;
                                const duration = started && completed
                                    ? ((completed - started) / 1000).toFixed(1) + 's'
                                    : '-';
                                const progressPercent = job.progress_percent ?? 0;
                                const canUndo = job.status === 'COMPLETED' && job.result?.batch_id;
                                const canDelete = ['COMPLETED', 'FAILED', 'DEAD_LETTER'].includes(job.status);

                                return (
                                    <div
                                        key={job.id}
                                        className="grid grid-cols-[130px_1fr_170px_110px_150px_78px] gap-4 p-3 items-center hover:bg-muted/30 transition-colors pointer-events-none"
                                    >
                                        <div className="pointer-events-auto">
                                            <div className={`inline-flex items-center gap-2 font-medium ${job.status === 'COMPLETED' ? 'text-green-600' :
                                                job.status === 'FAILED' || job.status === 'DEAD_LETTER' ? 'text-red-500' :
                                                    job.status === 'RUNNING' ? 'text-blue-500' : 'text-zinc-500'
                                                }`}>
                                                {getStatusIcon(job.status)}
                                                <span className="capitalize">{job.status.toLowerCase()}</span>
                                            </div>
                                        </div>
                                        <div className="font-medium text-foreground truncate pointer-events-auto capitalize">
                                            {job.type.replace(/_/g, ' ')}
                                        </div>
                                        <div className="text-right text-muted-foreground tabular-nums pointer-events-auto">
                                            {formatDate(job.created_at)}
                                        </div>
                                        <div className="text-right text-muted-foreground tabular-nums font-mono pointer-events-auto">
                                            {duration}
                                        </div>
                                        <div className="pointer-events-auto">
                                            <div className="h-2 w-full bg-muted rounded overflow-hidden">
                                                <div
                                                    className={`h-full ${job.status === 'FAILED' || job.status === 'DEAD_LETTER' ? 'bg-red-500' : 'bg-primary'}`}
                                                    style={{ width: `${Math.max(0, Math.min(100, progressPercent))}%` }}
                                                />
                                            </div>
                                            <div className="text-xs text-muted-foreground mt-1">
                                                {job.progress_current ?? 0}
                                                {job.progress_total ? ` / ${job.progress_total}` : ''} ({progressPercent}%)
                                            </div>
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
                                                <button
                                                    onClick={() => setSelectedJob(job)}
                                                    className="p-1 text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors"
                                                    title="View Details"
                                                >
                                                    <Eye className="w-4 h-4" />
                                                </button>
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
                                        selectedJob.status === 'RUNNING' ? 'text-blue-500' : 'text-zinc-500'
                                    }`}>
                                    {getStatusIcon(selectedJob.status)}
                                    <span className="capitalize">{selectedJob.status.toLowerCase()}</span>
                                </div>
                            </div>
                            <div className="text-right">
                                <span className="text-sm text-muted-foreground block mb-1">Type</span>
                                <span className="font-medium text-foreground capitalize">
                                    {selectedJob.type.replace(/_/g, ' ')}
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
                                {selectedJob.progress_current ?? 0}
                                {selectedJob.progress_total ? ` / ${selectedJob.progress_total}` : ''} ({selectedJob.progress_percent ?? 0}%)
                            </div>
                            <div className="text-xs text-muted-foreground">
                                Retry: {selectedJob.retry_count}/{selectedJob.max_retries}
                            </div>
                            {selectedJob.next_retry_at && (
                                <div className="text-xs text-amber-600">
                                    Next retry: {formatDate(selectedJob.next_retry_at)}
                                </div>
                            )}
                            {selectedJob.dead_lettered_at && (
                                <div className="text-xs text-red-600">
                                    Dead-letter: {formatDate(selectedJob.dead_lettered_at)}
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

                        {selectedJob.status === 'FAILED' && selectedJob.result?.error && (
                            <div>
                                <span className="text-sm font-medium text-destructive mb-2 flex items-center gap-2">
                                    <AlertTriangle className="w-4 h-4" />
                                    Error Details
                                </span>
                                <div className="bg-destructive/5 p-3 rounded-md border border-destructive/20 text-xs font-mono overflow-auto max-h-60 text-destructive">
                                    <pre className="whitespace-pre-wrap break-all">
                                        {selectedJob.result.error}
                                    </pre>
                                </div>
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
                    </div>
                )}
            </Modal>
        </div>
    );
}
