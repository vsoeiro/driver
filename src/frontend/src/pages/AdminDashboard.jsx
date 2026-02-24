import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Loader2, RefreshCw, RotateCcw } from 'lucide-react';
import { settingsService } from '../services/settings';
import { jobsService } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';
import AdminTabs from '../components/AdminTabs';
import { usePolling } from '../hooks/usePolling';

const PERIOD_OPTIONS = [
    { value: '24h', label: 'Last 24h' },
    { value: '3d', label: 'Last 3 days' },
    { value: '7d', label: 'Last 7 days' },
    { value: '30d', label: 'Last 30 days' },
    { value: '90d', label: 'Last 90 days' },
];

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
    const [refreshing, setRefreshing] = useState(false);
    const [period, setPeriod] = useState('24h');
    const [reprocessingJobId, setReprocessingJobId] = useState(null);
    const queryClient = useQueryClient();

    const selectedPeriodLabel = useMemo(
        () => PERIOD_OPTIONS.find((option) => option.value === period)?.label || period,
        [period],
    );

    const { data: snapshot, isLoading: loading, error, refetch } = useQuery({
        queryKey: ['observability', period],
        queryFn: () => settingsService.getObservabilitySnapshot({ period, forceRefresh: false }),
        staleTime: 15000,
    });

    useEffect(() => {
        if (error) {
            const message = error?.response?.data?.detail || 'Failed to load observability snapshot';
            showToast(message, 'error');
        }
    }, [error, showToast]);

    const refreshSnapshot = useCallback(async ({ forceRefresh = false } = {}) => {
        setRefreshing(true);
        try {
            const data = await settingsService.getObservabilitySnapshot({
                period,
                forceRefresh,
            });
            queryClient.setQueryData(['observability', period], data);
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to load observability snapshot';
            showToast(message, 'error');
        } finally {
            setRefreshing(false);
        }
    }, [period, queryClient, showToast]);

    usePolling({
        callback: () => refetch(),
        intervalMs: 20000,
        enabled: true,
        pauseWhenHidden: true,
        runImmediately: false,
    });

    const windowLabel = useMemo(
        () => snapshot?.period_label || selectedPeriodLabel,
        [snapshot, selectedPeriodLabel],
    );

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
        const windowValue = snapshot.throughput_window ?? snapshot.throughput_last_24h ?? 0;
        return [
            { label: 'Last hour', value: snapshot.throughput_last_hour || 0 },
            { label: `Selected (${windowLabel})`, value: windowValue },
        ];
    }, [snapshot, windowLabel]);

    const durationBars = useMemo(() => {
        if (!snapshot) return [];
        const avgDuration = snapshot.avg_duration_seconds_window ?? snapshot.avg_duration_seconds_last_24h ?? 0;
        const p95Duration = snapshot.p95_duration_seconds_window ?? snapshot.p95_duration_seconds_last_24h ?? 0;
        return [
            { label: 'Average (s)', value: Number(avgDuration) },
            { label: 'P95 (s)', value: Number(p95Duration) },
        ];
    }, [snapshot]);

    const metricsBars = useMemo(() => {
        if (!snapshot) return [];
        const total = snapshot.metrics_total_window ?? snapshot.metrics_total_24h ?? 0;
        const success = snapshot.metrics_success_window ?? snapshot.metrics_success_24h ?? 0;
        const failed = snapshot.metrics_failed_window ?? snapshot.metrics_failed_24h ?? 0;
        const skipped = snapshot.metrics_skipped_window ?? snapshot.metrics_skipped_24h ?? 0;
        return [
            { label: 'Total', value: total },
            { label: 'Success', value: success },
            { label: 'Failed', value: failed },
            { label: 'Skipped', value: skipped },
        ];
    }, [snapshot]);

    const providerUsageRows = useMemo(
        () => snapshot?.provider_request_usage || [],
        [snapshot],
    );

    const successRateWindow = snapshot?.success_rate_window ?? snapshot?.success_rate_last_24h ?? 0;
    const deadLetterWindow = snapshot?.dead_letter_jobs_window ?? snapshot?.dead_letter_jobs_24h ?? 0;

    const handleReprocess = useCallback(async (jobId) => {
        setReprocessingJobId(jobId);
        try {
            const job = await jobsService.reprocessJob(jobId);
            showToast(`Reprocess job queued (${job.id}).`, 'success');
            await refreshSnapshot({ forceRefresh: true });
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to reprocess dead-letter job';
            showToast(message, 'error');
        } finally {
            setReprocessingJobId(null);
        }
    }, [refreshSnapshot, showToast]);

    return (
        <div className="app-page">
            <div className="page-header flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h1 className="page-title">Admin Dashboard</h1>
                    <p className="page-subtitle">Operational health and job analytics in real time.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <AdminTabs />
                    <select
                        value={period}
                        onChange={(event) => setPeriod(event.target.value)}
                        className="input-shell px-2 py-1.5 text-sm"
                        aria-label="Select period window"
                    >
                        {PERIOD_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                    </select>
                    <button
                        type="button"
                        onClick={() => refreshSnapshot({ forceRefresh: true })}
                        className="btn-refresh"
                    >
                        {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                        Reload
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-auto">
                {loading && !snapshot ? (
                    <div className="flex justify-center p-12">
                        <Loader2 className="animate-spin text-primary" size={30} />
                    </div>
                ) : !snapshot ? (
                    <div className="empty-state">
                        <div className="empty-state-title">No dashboard data available</div>
                        <p className="empty-state-text">Try reloading to fetch a fresh observability snapshot.</p>
                    </div>
                ) : (
                    <div className="space-y-5">
                        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                            <div className="surface-card p-3">
                                <div className="text-xs text-muted-foreground">Queue Depth</div>
                                <div className="text-2xl font-semibold">{snapshot.queue_depth}</div>
                            </div>
                            <div className="surface-card p-3">
                                <div className="text-xs text-muted-foreground">Dead-letter ({windowLabel})</div>
                                <div className="text-2xl font-semibold">{deadLetterWindow}</div>
                            </div>
                            <div className="surface-card p-3">
                                <div className="text-xs text-muted-foreground">Generated At</div>
                                <div className="text-sm font-medium">{new Date(snapshot.generated_at).toLocaleString()}</div>
                                <div className="text-xs text-muted-foreground mt-1">
                                    Cache: {snapshot.cache_hit ? `hit (${snapshot.cache_ttl_seconds}s left)` : 'fresh'}
                                </div>
                            </div>
                        </div>

                        <div className="surface-card p-4">
                            <h2 className="font-medium mb-3">Job Metrics ({windowLabel})</h2>
                            <MiniBars
                                items={metricsBars}
                                max={Math.max(...metricsBars.map((item) => item.value), 1)}
                            />
                        </div>

                        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                            <div className="surface-card p-4">
                                <h2 className="font-medium mb-3">Success Rate ({windowLabel})</h2>
                                <div className="flex items-center justify-center">
                                    <PercentRing value={successRateWindow * 100} />
                                </div>
                            </div>
                            <div className="surface-card p-4">
                                <h2 className="font-medium mb-3">Queue Load</h2>
                                <MiniBars
                                    items={queueBars}
                                    max={Math.max(...queueBars.map((item) => item.value), 1)}
                                />
                            </div>
                            <div className="surface-card p-4">
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
                            <div className="surface-card p-4">
                                <h2 className="font-medium mb-3">Provider API Usage</h2>
                                <div className="space-y-3">
                                    {providerUsageRows.length === 0 ? (
                                        <div className="text-sm text-muted-foreground">No provider request telemetry yet.</div>
                                    ) : providerUsageRows.map((row) => {
                                        const pct = (Number(row.utilization_ratio) || 0) * 100;
                                        return (
                                            <div key={row.provider} className="rounded-lg border border-border/70 bg-card/70 p-2.5">
                                                <div className="flex items-center justify-between gap-2">
                                                    <div className="text-sm font-medium">{row.provider_label}</div>
                                                    <div className="text-xs text-muted-foreground">
                                                        {row.requests_in_window}/{row.max_requests} in {row.window_seconds}s
                                                    </div>
                                                </div>
                                                <div className="mt-2 h-2 rounded bg-muted overflow-hidden">
                                                    <div
                                                        className={`h-full rounded ${pct >= 90 ? 'bg-destructive' : pct >= 75 ? 'bg-amber-500' : 'bg-primary'}`}
                                                        style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                                                    />
                                                </div>
                                                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                                                    <span>Usage: {pct.toFixed(2)}%</span>
                                                    <span>Total since start: {row.total_requests_since_start}</span>
                                                    <span>429: {row.throttled_responses}</span>
                                                </div>
                                                {row.docs_url && (
                                                    <a
                                                        href={row.docs_url}
                                                        target="_blank"
                                                        rel="noreferrer"
                                                        className="mt-1 inline-flex text-xs text-primary hover:underline"
                                                    >
                                                        Docs
                                                    </a>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            <div className="surface-card p-4">
                                <h2 className="font-medium mb-3">Integration Health</h2>
                                <div className="space-y-2">
                                    {(snapshot.integration_health || []).map((item) => (
                                        <div key={item.key} className="flex items-start justify-between gap-2 rounded-lg border border-border/70 bg-card/70 p-2.5">
                                            <div>
                                                <div className="text-sm font-medium">{item.label}</div>
                                                <div className="text-xs text-muted-foreground">{item.detail || '-'}</div>
                                            </div>
                                            <span className={`status-chip ${
                                                item.status === 'ok'
                                                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                                                    : item.status === 'warning'
                                                        ? 'border-amber-200 bg-amber-50 text-amber-700'
                                                        : 'border-rose-200 bg-rose-50 text-rose-700'
                                            }`}>
                                                {item.status}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="surface-card p-4">
                                <h2 className="font-medium mb-3">Alerts</h2>
                                <div className="space-y-2">
                                    {(snapshot.recent_alerts || []).map((alert) => (
                                        <div key={`${alert.code}:${alert.created_at}`} className="rounded-lg border border-border/70 bg-muted/25 p-2.5">
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

                        <div className="surface-card p-4">
                            <h2 className="font-medium mb-3">Dead-letter Queue</h2>
                            {snapshot.dead_letter_jobs?.length > 0 ? (
                                <div className="space-y-2">
                                    {snapshot.dead_letter_jobs.map((job) => (
                                        <div key={job.id} className="rounded-lg border border-border/70 bg-card/70 p-2.5 flex items-center justify-between gap-3">
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
                                                className="btn-refresh disabled:opacity-50"
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
