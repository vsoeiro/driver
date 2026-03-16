import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Loader2, RefreshCw, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { settingsService } from '../services/settings';
import { jobsService } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';
import { useWorkspacePage } from '../contexts/WorkspaceContext';
import AdminTabs from '../components/AdminTabs';
import { useObservabilityQuery } from '../hooks/useAppQueries';
import { queryKeys } from '../lib/queryKeys';
import { formatDateTime } from '../utils/dateTime';

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
    const { t, i18n } = useTranslation();
    const location = useLocation();
    const { showToast } = useToast();
    const [refreshing, setRefreshing] = useState(false);
    const [period, setPeriod] = useState('24h');
    const [reprocessingJobId, setReprocessingJobId] = useState(null);
    const queryClient = useQueryClient();
    const PERIOD_OPTIONS = useMemo(
        () => [
            { value: '24h', label: t('adminDashboard.last24h') },
            { value: '3d', label: t('adminDashboard.last3d') },
            { value: '7d', label: t('adminDashboard.last7d') },
            { value: '30d', label: t('adminDashboard.last30d') },
            { value: '90d', label: t('adminDashboard.last90d') },
        ],
        [t]
    );

    const selectedPeriodLabel = useMemo(
        () => PERIOD_OPTIONS.find((option) => option.value === period)?.label || period,
        [period, PERIOD_OPTIONS],
    );

    const { data: snapshot, isLoading: loading, error } = useObservabilityQuery({
        period,
        refetchInterval: 60000,
        refetchIntervalInBackground: false,
    });

    useEffect(() => {
        if (error) {
            const message = error?.response?.data?.detail || t('adminDashboard.failedLoad');
            showToast(message, 'error');
        }
    }, [error, showToast, t]);

    const refreshSnapshot = useCallback(async ({ forceRefresh = false } = {}) => {
        setRefreshing(true);
        try {
            const data = await settingsService.getObservabilitySnapshot({
                period,
                forceRefresh,
            });
            queryClient.setQueryData(queryKeys.observability.detail(period), data);
        } catch (error) {
            const message = error?.response?.data?.detail || t('adminDashboard.failedLoad');
            showToast(message, 'error');
        } finally {
            setRefreshing(false);
        }
    }, [period, queryClient, showToast, t]);

    const windowLabel = useMemo(
        () => snapshot?.period_label || selectedPeriodLabel,
        [snapshot, selectedPeriodLabel],
    );

    const queueBars = useMemo(() => {
        if (!snapshot) return [];
        return [
            { label: t('adminDashboard.bars.pending'), value: snapshot.pending_jobs || 0 },
            { label: t('adminDashboard.bars.running'), value: snapshot.running_jobs || 0 },
            { label: t('adminDashboard.bars.retryScheduled'), value: snapshot.retry_scheduled_jobs || 0 },
            { label: t('adminDashboard.bars.queueDepth'), value: snapshot.queue_depth || 0 },
        ];
    }, [snapshot, t]);

    const throughputBars = useMemo(() => {
        if (!snapshot) return [];
        const windowValue = snapshot.throughput_window ?? snapshot.throughput_last_24h ?? 0;
        return [
            { label: t('adminDashboard.bars.lastHour'), value: snapshot.throughput_last_hour || 0 },
            { label: t('adminDashboard.bars.selected', { window: windowLabel }), value: windowValue },
        ];
    }, [snapshot, t, windowLabel]);

    const durationBars = useMemo(() => {
        if (!snapshot) return [];
        const avgDuration = snapshot.avg_duration_seconds_window ?? snapshot.avg_duration_seconds_last_24h ?? 0;
        const p95Duration = snapshot.p95_duration_seconds_window ?? snapshot.p95_duration_seconds_last_24h ?? 0;
        return [
            { label: t('adminDashboard.bars.average'), value: Number(avgDuration) },
            { label: t('adminDashboard.bars.p95'), value: Number(p95Duration) },
        ];
    }, [snapshot, t]);

    const metricsBars = useMemo(() => {
        if (!snapshot) return [];
        const total = snapshot.metrics_total_window ?? snapshot.metrics_total_24h ?? 0;
        const success = snapshot.metrics_success_window ?? snapshot.metrics_success_24h ?? 0;
        const failed = snapshot.metrics_failed_window ?? snapshot.metrics_failed_24h ?? 0;
        const skipped = snapshot.metrics_skipped_window ?? snapshot.metrics_skipped_24h ?? 0;
        return [
            { label: t('adminDashboard.bars.total'), value: total },
            { label: t('adminDashboard.bars.success'), value: success },
            { label: t('adminDashboard.bars.failed'), value: failed },
            { label: t('adminDashboard.bars.skipped'), value: skipped },
        ];
    }, [snapshot, t]);

    const providerUsageRows = useMemo(
        () => snapshot?.provider_request_usage || [],
        [snapshot],
    );

    const successRateWindow = snapshot?.success_rate_window ?? snapshot?.success_rate_last_24h ?? 0;
    const deadLetterWindow = snapshot?.dead_letter_jobs_window ?? snapshot?.dead_letter_jobs_24h ?? 0;

    useWorkspacePage(useMemo(() => ({
        title: t('adminDashboard.title'),
        subtitle: t('workspace.adminSubtitle', { defaultValue: 'Saude operacional, gargalos e telemetria em um unico lugar.' }),
        entityType: 'admin',
        entityId: 'dashboard',
        sourceRoute: location.pathname,
        activeFilters: [windowLabel],
        metrics: [
            t('workspace.queueDepthMetric', { value: snapshot?.queue_depth ?? 0, defaultValue: `Fila ${snapshot?.queue_depth ?? 0}` }),
            t('workspace.deadLetterMetric', { value: deadLetterWindow, defaultValue: `Dead letters ${deadLetterWindow}` }),
        ],
        suggestedPrompts: [
            t('workspace.aiPrompts.jobReview', { defaultValue: 'Explique o que aconteceu nestes jobs e o que fazer agora.' }),
            t('workspace.aiPrompts.recommend', { defaultValue: 'Sugira as proximas acoes com maior impacto.' }),
            t('workspace.aiPrompts.summarize', { defaultValue: 'Resuma o contexto atual e destaque riscos.' }),
        ],
    }), [deadLetterWindow, location.pathname, snapshot?.queue_depth, t, windowLabel]));

    const handleReprocess = useCallback(async (jobId) => {
        setReprocessingJobId(jobId);
        try {
            const job = await jobsService.reprocessJob(jobId);
            showToast(t('adminDashboard.reprocessQueued', { id: job.id }), 'success');
            await refreshSnapshot({ forceRefresh: true });
        } catch (error) {
            const message = error?.response?.data?.detail || t('adminDashboard.failedReprocess');
            showToast(message, 'error');
        } finally {
            setReprocessingJobId(null);
        }
    }, [refreshSnapshot, showToast, t]);

    return (
        <div className="app-page">
            <div className="page-header flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h1 className="page-title">{t('adminDashboard.title')}</h1>
                    <p className="page-subtitle">{t('adminDashboard.subtitle')}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <AdminTabs />
                    <select
                        value={period}
                        onChange={(event) => setPeriod(event.target.value)}
                        className="input-shell px-2 py-1.5 text-sm"
                        aria-label={t('adminDashboard.selectPeriod')}
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
                        {t('common.reload')}
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
                        <div className="empty-state-title">{t('adminDashboard.noData')}</div>
                        <p className="empty-state-text">{t('adminDashboard.noDataHelp')}</p>
                    </div>
                ) : (
                    <div className="space-y-5">
                        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                            <div className="surface-card p-3">
                                <div className="text-xs text-muted-foreground">{t('adminDashboard.queueDepth')}</div>
                                <div className="text-2xl font-semibold">{snapshot.queue_depth}</div>
                            </div>
                            <div className="surface-card p-3">
                                <div className="text-xs text-muted-foreground">{t('adminDashboard.deadLetterWindow', { window: windowLabel })}</div>
                                <div className="text-2xl font-semibold">{deadLetterWindow}</div>
                            </div>
                            <div className="surface-card p-3">
                                <div className="text-xs text-muted-foreground">{t('adminDashboard.generatedAt')}</div>
                                <div className="text-sm font-medium">{formatDateTime(snapshot.generated_at, i18n.language)}</div>
                                <div className="text-xs text-muted-foreground mt-1">
                                    {snapshot.cache_hit
                                        ? t('adminDashboard.cacheHit', { seconds: snapshot.cache_ttl_seconds })
                                        : t('adminDashboard.cacheFresh')}
                                </div>
                            </div>
                        </div>

                        <div className="surface-card p-4">
                            <h2 className="font-medium mb-3">{t('adminDashboard.jobMetrics', { window: windowLabel })}</h2>
                            <MiniBars
                                items={metricsBars}
                                max={Math.max(...metricsBars.map((item) => item.value), 1)}
                            />
                        </div>

                        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                            <div className="surface-card p-4">
                                <h2 className="font-medium mb-3">{t('adminDashboard.successRate', { window: windowLabel })}</h2>
                                <div className="flex items-center justify-center">
                                    <PercentRing value={successRateWindow * 100} />
                                </div>
                            </div>
                            <div className="surface-card p-4">
                                <h2 className="font-medium mb-3">{t('adminDashboard.queueLoad')}</h2>
                                <MiniBars
                                    items={queueBars}
                                    max={Math.max(...queueBars.map((item) => item.value), 1)}
                                />
                            </div>
                            <div className="surface-card p-4">
                                <h2 className="font-medium mb-3">{t('adminDashboard.throughput')}</h2>
                                <MiniBars
                                    items={throughputBars}
                                    max={Math.max(...throughputBars.map((item) => item.value), 1)}
                                />
                                <div className="border-t mt-4 pt-3">
                                    <h3 className="text-sm font-medium mb-2">{t('adminDashboard.latency')}</h3>
                                    <MiniBars
                                        items={durationBars}
                                        max={Math.max(...durationBars.map((item) => item.value), 1)}
                                    />
                                </div>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                            <div className="surface-card p-4">
                                <h2 className="font-medium mb-3">{t('adminDashboard.providerUsage')}</h2>
                                <div className="space-y-3">
                                    {providerUsageRows.length === 0 ? (
                                        <div className="text-sm text-muted-foreground">{t('adminDashboard.noTelemetry')}</div>
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
                                                <div className="mt-2 h-2 rounded-sm bg-muted overflow-hidden">
                                                    <div
                                                        className={`h-full rounded-sm ${pct >= 90 ? 'bg-destructive' : pct >= 75 ? 'bg-primary/70' : 'bg-primary'}`}
                                                        style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                                                    />
                                                </div>
                                                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                                                    <span>{t('adminDashboard.usage', { value: pct.toFixed(2) })}</span>
                                                    <span>{t('adminDashboard.totalSinceStart', { value: row.total_requests_since_start })}</span>
                                                    <span>{t('adminDashboard.throttled429', { value: row.throttled_responses })}</span>
                                                </div>
                                                {row.docs_url && (
                                                    <a
                                                        href={row.docs_url}
                                                        target="_blank"
                                                        rel="noreferrer"
                                                        className="mt-1 inline-flex text-xs text-primary hover:underline"
                                                    >
                                                        {t('adminDashboard.docs')}
                                                    </a>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            <div className="surface-card p-4">
                                <h2 className="font-medium mb-3">{t('adminDashboard.integrationHealth')}</h2>
                                <div className="space-y-2">
                                    {(snapshot.integration_health || []).map((item) => (
                                        <div key={item.key} className="flex items-start justify-between gap-2 rounded-lg border border-border/70 bg-card/70 p-2.5">
                                            <div>
                                                <div className="text-sm font-medium">{item.label}</div>
                                                <div className="text-xs text-muted-foreground">{item.detail || '-'}</div>
                                            </div>
                                            <span className={`status-chip ${item.status === 'ok' ? 'status-badge-success' : item.status === 'warning' ? 'status-badge-warning' : 'status-badge-danger'}`}>
                                                {item.status}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>

                        </div>

                        <div className="surface-card p-4">
                            <h2 className="font-medium mb-3">{t('adminDashboard.deadLetterQueue')}</h2>
                            {snapshot.dead_letter_jobs?.length > 0 ? (
                                <div className="space-y-2">
                                    {snapshot.dead_letter_jobs.map((job) => (
                                        <div key={job.id} className="rounded-lg border border-border/70 bg-card/70 p-2.5 flex items-center justify-between gap-3">
                                            <div className="min-w-0">
                                                <div className="text-sm font-medium truncate">{job.type}</div>
                                                <div className="text-xs text-muted-foreground truncate">
                                                    {job.dead_letter_reason || t('adminDashboard.noReason')}
                                                </div>
                                                <div className="text-xs text-muted-foreground">
                                                    {job.dead_lettered_at ? formatDateTime(job.dead_lettered_at, i18n.language) : '-'} - {t('adminDashboard.retry', { current: job.retry_count, max: job.max_retries })}
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
                                                {t('adminDashboard.reprocess')}
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="text-sm text-muted-foreground">{t('adminDashboard.noDeadLetters')}</div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
