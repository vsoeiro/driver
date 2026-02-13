import React, { useState, useEffect } from 'react';
import { RefreshCw, CheckCircle, XCircle, Clock, PlayCircle, Eye, AlertTriangle } from 'lucide-react';
import { getJobs } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';
import Modal from '../components/Modal';

export default function Jobs() {
    const [jobs, setJobs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedJob, setSelectedJob] = useState(null);
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
            case 'RUNNING':
                return <PlayCircle className="w-4 h-4" />;
            default:
                return <Clock className="w-4 h-4" />;
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
                        <div className="grid grid-cols-[120px_1fr_180px_100px_40px] gap-4 p-3 border-b bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider items-center">
                            <div>Status</div>
                            <div>Type</div>
                            <div className="text-right">Started</div>
                            <div className="text-right">Duration</div>
                            <div className="text-center"></div>
                        </div>

                        <div className="divide-y text-sm">
                            {jobs.map((job) => {
                                const started = job.started_at ? new Date(job.started_at) : null;
                                const completed = job.completed_at ? new Date(job.completed_at) : null;
                                const duration = started && completed
                                    ? ((completed - started) / 1000).toFixed(1) + 's'
                                    : '-';

                                return (
                                    <div
                                        key={job.id}
                                        className="grid grid-cols-[120px_1fr_180px_100px_40px] gap-4 p-3 items-center hover:bg-muted/30 transition-colors pointer-events-none"
                                    >
                                        <div className="pointer-events-auto">
                                            <div className={`inline-flex items-center gap-2 font-medium ${job.status === 'COMPLETED' ? 'text-green-600' :
                                                job.status === 'FAILED' ? 'text-red-500' :
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
                                        <div className="text-right pointer-events-auto">
                                            <button
                                                onClick={() => setSelectedJob(job)}
                                                className="p-1 text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors"
                                                title="View Details"
                                            >
                                                <Eye className="w-4 h-4" />
                                            </button>
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
                                    selectedJob.status === 'FAILED' ? 'text-red-500' :
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
                    </div>
                )}
            </Modal>
        </div>
    );
}
