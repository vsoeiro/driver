import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Loader2, RefreshCw, RotateCcw } from 'lucide-react';
import { settingsService } from '../services/settings';
import { jobsService } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';
import AdminTabs from '../components/AdminTabs';

function PercentRing({ value }) {
    const safe = Math.max(0, Math.min(100, Number(value) || 0));
    const style = {
        background: `conic-gradient(hsl(var(--primary)) ${safe}%, hsl(var(--muted)) ${safe}% 100%)`,
    };
    return (
        <div className="w-28 h-28 rounded-full p-2" style={style}>
            <div className="w-full h-full rounded-full bg-background border flex items-center justify-center text-xl font-semibold">
                {safe.toFixed(1)}%
            </div>
        </div>
    );
}

function MiniBars({ items, max }) {
    return (
        <div className="space-y-2">
            {items.map((item) => {
                const pct = max > 0 ? (item.value / max) * 100 : 0;
                return (
                    <div key={item.label}>
                        <div className="flex items-center justify-between text-xs mb-1">
                            <span className="text-muted-foreground">{item.label}</span>
                            <span className="font-medium">{item.value}</span>
                        </div>
                        <div className="h-2 rounded bg-muted overflow-hidden">
                            <div className="h-full bg-primary rounded" style={{ width: `${Math.max(2, pct)}%` }} />
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

export default function AdminDashboard() {
    const { showToast } = useToast();
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [snapshot, setSnapshot] = useState(null);
    const [reprocessingJobId, setReprocessingJobId] = useState(null);

    const loadSnapshot = useCallback(async (silent = false) => {
        if (silent) {
            setRefreshing(true);
        } else {
            setLoading(true);
        }
        try {
            const data = await settingsService.getObservabilitySnapshot();
            setSnapshot(data);
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to load observability snapshot';
            showToast(message, 'error');
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, [showToast]);

    useEffect(() => {
        let cancelled = false;
        const run = async () => {
            if (!cancelled) {
                await loadSnapshot(false);
            }
        };
        run();
        const interval = setInterval(() => {
            if (!cancelled) {
                loadSnapshot(true);
            }
        }, 15000);
        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, [loadSnapshot]);

    const queueBars = useMemo(() => {
        if (!snapshot) return [];
        return [
            { label: 'Pending', value: snapshot.pending_jobs || 0 },
            { label: 'Running', value: snapshot.running_jobs || 0 },
            { label: 'Retry Scheduled', value: snapshot.retry_scheduled_jobs || 0 },
            { label: 'Queue Depth', value: snapshot.queue_depth || 0 },
        ];
    }, [snapshot]);

    const throughputBars = useMemo(() => {
        if (!snapshot) return [];
        return [
            { label: 'Last hour', value: snapshot.throughput_last_hour || 0 },
            { label: 'Last 24h', value: snapshot.throughput_last_24h || 0 },
        ];
    }, [snapshot]);

    const durationBars = useMemo(() => {
        if (!snapshot) return [];
        return [
            { label: 'Average (s)', value: Number(snapshot.avg_duration_seconds_last_24h || 0) },
            { label: 'P95 (s)', value: Number(snapshot.p95_duration_seconds_last_24h || 0) },
        ];
    }, [snapshot]);

    const metricsBars = useMemo(() => {
        if (!snapshot) return [];
        return [
            { label: 'Total', value: snapshot.metrics_total_24h || 0 },
            { label: 'Success', value: snapshot.metrics_success_24h || 0 },
            { label: 'Failed', value: snapshot.metrics_failed_24h || 0 },
            { label: 'Skipped', value: snapshot.metrics_skipped_24h || 0 },
        ];
    }, [snapshot]);

    const handleReprocess = async (jobId) => {
        setReprocessingJobId(jobId);
        try {
            const job = await jobsService.reprocessJob(jobId);
            showToast(`Reprocess job queued (${job.id}).`, 'success');
            await loadSnapshot(true);
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to reprocess dead-letter job';
            showToast(message, 'error');
        } finally {
            setReprocessingJobId(null);
        }
    };

    return (
        <div className="h-screen flex flex-col bg-background">
            <div className="border-b px-5 py-4 flex items-center justify-between gap-3">
                <div>
                    <h1 className="text-xl font-semibold">Admin Dashboard</h1>
                    <p className="text-sm text-muted-foreground">Operational health and job analytics in real time.</p>
                </div>
                <div className="flex items-center gap-2">
                    <AdminTabs />
                    <button
                        type="button"
                        onClick={() => loadSnapshot(true)}
                        className="px-3 py-1.5 rounded-md border text-sm hover:bg-accent inline-flex items-center gap-2"
                    >
                        {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                        Refresh
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-auto p-5">
                {loading && !snapshot ? (
                    <div className="flex justify-center p-12">
                        <Loader2 className="animate-spin text-primary" size={30} />
                    </div>
                ) : !snapshot ? (
                    <div className="text-sm text-muted-foreground">No dashboard data available.</div>
                ) : (
                    <div className="space-y-5">
                        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
                            <div className="rounded-lg border p-3 bg-card">
                                <div className="text-xs text-muted-foreground">Queue Depth</div>
                                <div className="text-2xl font-semibold">{snapshot.queue_depth}</div>
                            </div>
                            <div className="rounded-lg border p-3 bg-card">
                                <div className="text-xs text-muted-foreground">Dead-letter (24h)</div>
                                <div className="text-2xl font-semibold">{snapshot.dead_letter_jobs_24h}</div>
                            </div>
                            <div className="rounded-lg border p-3 bg-card">
                                <div className="text-xs text-muted-foreground">AI Provider</div>
                                <div className="text-lg font-semibold truncate">{snapshot.ai_provider}</div>
                                <div className="text-xs text-muted-foreground truncate">{snapshot.ai_model}</div>
                            </div>
                            <div className="rounded-lg border p-3 bg-card">
                                <div className="text-xs text-muted-foreground">Generated At</div>
                                <div className="text-sm font-medium">{new Date(snapshot.generated_at).toLocaleString()}</div>
                            </div>
                        </div>

                        <div className="rounded-lg border p-4 bg-card">
                            <h2 className="font-medium mb-3">Job Metrics (24h)</h2>
                            <MiniBars
                                items={metricsBars}
                                max={Math.max(...metricsBars.map((item) => item.value), 1)}
                            />
                        </div>

                        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                            <div className="rounded-lg border p-4 bg-card">
                                <h2 className="font-medium mb-3">Success Rate (24h)</h2>
                                <div className="flex items-center justify-center">
                                    <PercentRing value={(snapshot.success_rate_last_24h || 0) * 100} />
                                </div>
                            </div>
                            <div className="rounded-lg border p-4 bg-card">
                                <h2 className="font-medium mb-3">Queue Load</h2>
                                <MiniBars
                                    items={queueBars}
                                    max={Math.max(...queueBars.map((item) => item.value), 1)}
                                />
                            </div>
                            <div className="rounded-lg border p-4 bg-card">
                                <h2 className="font-medium mb-3">Throughput</h2>
                                <MiniBars
                                    items={throughputBars}
                                    max={Math.max(...throughputBars.map((item) => item.value), 1)}
                                />
                                <div className="border-t mt-4 pt-3">
                                    <h3 className="text-sm font-medium mb-2">Latency</h3>
                                    <MiniBars
                                        items={durationBars}
                                        max={Math.max(...durationBars.map((item) => item.value), 1)}
                                    />
                                </div>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                            <div className="rounded-lg border p-4 bg-card">
                                <h2 className="font-medium mb-3">Integration Health</h2>
                                <div className="space-y-2">
                                    {(snapshot.integration_health || []).map((item) => (
                                        <div key={item.key} className="flex items-start justify-between gap-2 border rounded-md p-2">
                                            <div>
                                                <div className="text-sm font-medium">{item.label}</div>
                                                <div className="text-xs text-muted-foreground">{item.detail || '-'}</div>
                                            </div>
                                            <span className={`px-2 py-0.5 rounded border text-xs ${
                                                item.status === 'ok'
                                                    ? 'text-green-700 border-green-200 bg-green-50'
                                                    : item.status === 'warning'
                                                        ? 'text-amber-700 border-amber-200 bg-amber-50'
                                                        : 'text-red-700 border-red-200 bg-red-50'
                                            }`}>
                                                {item.status}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="rounded-lg border p-4 bg-card">
                                <h2 className="font-medium mb-3">Alerts</h2>
                                <div className="space-y-2">
                                    {(snapshot.recent_alerts || []).map((alert) => (
                                        <div key={`${alert.code}:${alert.created_at}`} className="border rounded-md p-2 bg-muted/20">
                                            <div className="text-sm font-medium inline-flex items-center gap-1">
                                                {alert.severity !== 'info' && <AlertTriangle className="w-4 h-4" />}
                                                {alert.severity.toUpperCase()} - {alert.code}
                                            </div>
                                            <p className="text-xs text-muted-foreground">{alert.message}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>

                        <div className="rounded-lg border p-4 bg-card">
                            <h2 className="font-medium mb-3">Dead-letter Queue</h2>
                            {snapshot.dead_letter_jobs?.length > 0 ? (
                                <div className="space-y-2">
                                    {snapshot.dead_letter_jobs.map((job) => (
                                        <div key={job.id} className="border rounded-md p-2 flex items-center justify-between gap-3">
                                            <div className="min-w-0">
                                                <div className="text-sm font-medium truncate">{job.type}</div>
                                                <div className="text-xs text-muted-foreground truncate">
                                                    {job.dead_letter_reason || 'No reason captured'}
                                                </div>
                                                <div className="text-xs text-muted-foreground">
                                                    {job.dead_lettered_at ? new Date(job.dead_lettered_at).toLocaleString() : '-'} - retry {job.retry_count}/{job.max_retries}
                                                </div>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => handleReprocess(job.id)}
                                                disabled={reprocessingJobId === job.id}
                                                className="px-3 py-1.5 rounded-md border text-sm hover:bg-accent disabled:opacity-50 inline-flex items-center gap-2"
                                            >
                                                {reprocessingJobId === job.id
                                                    ? <Loader2 className="w-4 h-4 animate-spin" />
                                                    : <RotateCcw className="w-4 h-4" />}
                                                Reprocess
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="text-sm text-muted-foreground">No dead-letter jobs right now.</div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
