import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bell, CheckCheck, Loader2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { settingsService } from '../services/settings';
import { jobsService } from '../services/jobs';

const DISMISSED_STORAGE_KEY = 'driver-notifications-dismissed-v1';

function loadDismissedIds() {
    try {
        const raw = window.localStorage.getItem(DISMISSED_STORAGE_KEY);
        if (!raw) return new Set();
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return new Set();
        return new Set(parsed.map((value) => String(value)));
    } catch {
        return new Set();
    }
}

function saveDismissedIds(idsSet) {
    try {
        const values = Array.from(idsSet).slice(-500);
        window.localStorage.setItem(DISMISSED_STORAGE_KEY, JSON.stringify(values));
    } catch {
        // ignore storage write errors
    }
}

function asDateMs(value) {
    const ms = Date.parse(String(value || ''));
    return Number.isFinite(ms) ? ms : 0;
}

function toneClass(kind) {
    if (kind === 'error') return 'border-rose-300/60 bg-rose-50/70';
    if (kind === 'warning') return 'border-amber-300/70 bg-amber-50/70';
    return 'border-border/70 bg-card/70';
}

function relativeTime(value, t) {
    const ts = asDateMs(value);
    if (!ts) return '';
    const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
    if (diffSec < 60) return t('notifications.secondsAgo', { value: diffSec });
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return t('notifications.minutesAgo', { value: diffMin });
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return t('notifications.hoursAgo', { value: diffHr });
    const diffDay = Math.floor(diffHr / 24);
    return t('notifications.daysAgo', { value: diffDay });
}

export default function NotificationBell() {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    const [dismissedIds, setDismissedIds] = useState(() => loadDismissedIds());
    const wrapperRef = useRef(null);

    useEffect(() => {
        const onClickOutside = (event) => {
            if (!wrapperRef.current?.contains(event.target)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', onClickOutside);
        return () => document.removeEventListener('mousedown', onClickOutside);
    }, []);

    const alertsQuery = useQuery({
        queryKey: ['notifications', 'observability'],
        queryFn: () => settingsService.getObservabilitySnapshot({ period: '24h', forceRefresh: false }),
        refetchInterval: 30000,
        refetchIntervalInBackground: true,
        staleTime: 15000,
    });

    const jobsQuery = useQuery({
        queryKey: ['notifications', 'jobs'],
        queryFn: () => {
            const createdAfter = new Date(Date.now() - (24 * 60 * 60 * 1000)).toISOString();
            return jobsService.getJobs(
                40,
                0,
                ['COMPLETED', 'FAILED', 'DEAD_LETTER', 'CANCELLED'],
                { createdAfter },
                { includeEstimates: false },
            );
        },
        refetchInterval: 30000,
        refetchIntervalInBackground: true,
        staleTime: 15000,
    });

    const notifications = useMemo(() => {
        const alerts = (alertsQuery.data?.recent_alerts || []).map((alert) => ({
            id: `alert:${alert.code}:${alert.created_at}`,
            kind: alert.severity === 'error' ? 'error' : alert.severity === 'warning' ? 'warning' : 'info',
            title: `${String(alert.severity || 'info').toUpperCase()} · ${alert.code}`,
            message: alert.message,
            created_at: alert.created_at,
        }));

        const jobs = (jobsQuery.data || []).map((job) => {
            const status = String(job.status || '').toUpperCase();
            const kind = status === 'FAILED' || status === 'DEAD_LETTER' ? 'error' : status === 'CANCELLED' ? 'warning' : 'info';
            const title = status === 'COMPLETED'
                ? t('notifications.jobCompleted', { type: job.type })
                : status === 'FAILED'
                    ? t('notifications.jobFailed', { type: job.type })
                    : status === 'DEAD_LETTER'
                        ? t('notifications.jobDeadLetter', { type: job.type })
                        : t('notifications.jobCancelled', { type: job.type });
            return {
                id: `job:${job.id}:${status}:${job.completed_at || job.created_at}`,
                kind,
                title,
                message: `#${String(job.id).slice(0, 8)}`,
                created_at: job.completed_at || job.created_at,
            };
        });

        return [...alerts, ...jobs]
            .sort((a, b) => asDateMs(b.created_at) - asDateMs(a.created_at))
            .slice(0, 80);
    }, [alertsQuery.data, jobsQuery.data, t]);

    const visibleNotifications = useMemo(
        () => notifications.filter((item) => !dismissedIds.has(item.id)),
        [notifications, dismissedIds],
    );

    const badgeCount = visibleNotifications.length;

    const dismissOne = (id) => {
        setDismissedIds((prev) => {
            const next = new Set(prev);
            next.add(id);
            saveDismissedIds(next);
            return next;
        });
    };

    const dismissAll = () => {
        setDismissedIds((prev) => {
            const next = new Set(prev);
            visibleNotifications.forEach((item) => next.add(item.id));
            saveDismissedIds(next);
            return next;
        });
    };

    const loading = alertsQuery.isLoading || jobsQuery.isLoading;

    return (
        <div className="relative" ref={wrapperRef}>
            <button
                type="button"
                className="ghost-icon-button relative"
                onClick={() => setOpen((prev) => !prev)}
                title={t('notifications.title')}
                aria-label={t('notifications.title')}
            >
                <Bell size={16} />
                {badgeCount > 0 && (
                    <span className="absolute -right-1 -top-1 inline-flex min-w-5 items-center justify-center rounded-full bg-rose-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                        {badgeCount > 99 ? '99+' : badgeCount}
                    </span>
                )}
            </button>

            {open && (
                <div className="absolute right-0 top-10 z-[360] w-[380px] max-w-[90vw] rounded-lg border border-border bg-card p-2 shadow-xl">
                    <div className="mb-2 flex items-center justify-between px-2 py-1">
                        <div className="text-sm font-semibold">{t('notifications.title')}</div>
                        <button
                            type="button"
                            onClick={dismissAll}
                            className="inline-flex items-center gap-1 rounded border border-border/80 px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
                            disabled={visibleNotifications.length === 0}
                        >
                            <CheckCheck size={12} />
                            {t('notifications.dismissAll')}
                        </button>
                    </div>

                    <div className="max-h-[420px] space-y-2 overflow-auto pr-1">
                        {loading && visibleNotifications.length === 0 && (
                            <div className="flex items-center justify-center py-6 text-muted-foreground">
                                <Loader2 className="h-4 w-4 animate-spin" />
                            </div>
                        )}

                        {!loading && visibleNotifications.length === 0 && (
                            <div className="rounded border border-border/70 bg-muted/20 px-3 py-6 text-center text-sm text-muted-foreground">
                                {t('notifications.none')}
                            </div>
                        )}

                        {visibleNotifications.map((item) => (
                            <div key={item.id} className={`rounded border px-2.5 py-2 ${toneClass(item.kind)}`}>
                                <div className="flex items-start justify-between gap-2">
                                    <div className="min-w-0">
                                        <div className="truncate text-xs font-semibold">{item.title}</div>
                                        <div className="mt-0.5 text-xs text-muted-foreground">{item.message}</div>
                                        <div className="mt-1 text-[11px] text-muted-foreground">{relativeTime(item.created_at, t)}</div>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => dismissOne(item.id)}
                                        className="rounded p-1 text-muted-foreground hover:bg-accent/70 hover:text-foreground"
                                        title={t('notifications.dismiss')}
                                    >
                                        <X size={12} />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
