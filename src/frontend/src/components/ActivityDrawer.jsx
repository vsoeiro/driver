import { Bell, CheckCheck, ChevronRight, Loader2, ShieldAlert, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useJobActivity } from '../contexts/JobActivityContext';
import { useObservabilityQuery } from '../hooks/useAppQueries';
import { getJobCrossLinkTarget } from '../lib/workspace';

const DISMISSED_STORAGE_KEY = 'driver-activity-dismissed-v1';
const OPEN_POLL_INTERVAL_MS = 30000;
const IDLE_POLL_INTERVAL_MS = 120000;
const NOTIFICATIONS_STALE_MS = 60000;

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
        window.localStorage.setItem(DISMISSED_STORAGE_KEY, JSON.stringify(Array.from(idsSet).slice(-500)));
    } catch {
        // Ignore storage failures.
    }
}

function asDateMs(value) {
    const ms = Date.parse(String(value || ''));
    return Number.isFinite(ms) ? ms : 0;
}

function relativeTime(value, t) {
    const ts = asDateMs(value);
    if (!ts) return '';
    const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
    if (diffSec < 60) return t('activity.secondsAgo', { value: diffSec });
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return t('activity.minutesAgo', { value: diffMin });
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return t('activity.hoursAgo', { value: diffHr });
    return t('activity.daysAgo', { value: Math.floor(diffHr / 24) });
}

function getActivityToneClass(kind) {
    if (kind === 'error') return 'status-badge-danger';
    if (kind === 'warning') return 'status-badge-warning';
    return 'status-badge-info';
}

function buildActivityItems({ alerts, jobs, t }) {
    const alertItems = (alerts || []).map((alert) => ({
        id: `alert:${alert.code}:${alert.created_at}`,
        kind: alert.severity === 'error' ? 'error' : alert.severity === 'warning' ? 'warning' : 'info',
        section: alert.severity === 'error' ? 'attention' : 'system',
        title: `${String(alert.severity || 'info').toUpperCase()} - ${alert.code}`,
        message: alert.message,
        createdAt: alert.created_at,
        target: {
            to: '/admin/dashboard',
            label: t('activity.openDashboard'),
        },
    }));

    const jobItems = (jobs || [])
        .filter((job) => ['COMPLETED', 'FAILED', 'DEAD_LETTER', 'CANCELLED'].includes(String(job.status || '').toUpperCase()))
        .map((job) => {
            const status = String(job.status || '').toUpperCase();
            const kind = status === 'FAILED' || status === 'DEAD_LETTER' ? 'error' : status === 'CANCELLED' ? 'warning' : 'info';
            const section = kind === 'error' ? 'attention' : 'operations';
            return {
                id: `job:${job.id}:${status}:${job.completed_at || job.created_at}`,
                kind,
                section,
                title: status === 'COMPLETED'
                    ? t('activity.jobCompleted', { type: job.type })
                    : status === 'FAILED'
                        ? t('activity.jobFailed', { type: job.type })
                        : status === 'DEAD_LETTER'
                            ? t('activity.jobDeadLetter', { type: job.type })
                            : t('activity.jobCancelled', { type: job.type }),
                message: `#${String(job.id).slice(0, 8)}`,
                createdAt: job.completed_at || job.created_at,
                target: getJobCrossLinkTarget(job, t),
            };
        });

    return [...alertItems, ...jobItems]
        .sort((a, b) => asDateMs(b.createdAt) - asDateMs(a.createdAt))
        .slice(0, 80);
}

export default function ActivityDrawer() {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const { jobs: recentJobs = [], refetch: refetchRecentJobs, canRefresh, hasActiveJobs } = useJobActivity();
    const [open, setOpen] = useState(false);
    const [dismissedIds, setDismissedIds] = useState(() => loadDismissedIds());
    const drawerRef = useRef(null);
    const pollIntervalMs = open ? OPEN_POLL_INTERVAL_MS : IDLE_POLL_INTERVAL_MS;

    useEffect(() => {
        if (!open) return undefined;
        const onKeyDown = (event) => {
            if (event.key === 'Escape') setOpen(false);
        };
        document.addEventListener('keydown', onKeyDown);
        return () => document.removeEventListener('keydown', onKeyDown);
    }, [open]);

    const {
        data: alertSnapshot,
        isLoading: alertsLoading,
        refetch: refetchAlerts,
    } = useObservabilityQuery({
        period: '24h',
        refetchInterval: pollIntervalMs,
        refetchIntervalInBackground: false,
        staleTime: NOTIFICATIONS_STALE_MS,
    });

    useEffect(() => {
        if (!open) return;
        void refetchAlerts();
        if (canRefresh) {
            void refetchRecentJobs();
        }
    }, [canRefresh, open, refetchAlerts, refetchRecentJobs]);

    useEffect(() => {
        if (!open) return undefined;
        const onClickOutside = (event) => {
            if (!drawerRef.current?.contains(event.target)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', onClickOutside);
        return () => document.removeEventListener('mousedown', onClickOutside);
    }, [open]);

    const allItems = useMemo(
        () => buildActivityItems({ alerts: alertSnapshot?.recent_alerts, jobs: recentJobs, t }),
        [alertSnapshot?.recent_alerts, recentJobs, t],
    );

    const visibleItems = useMemo(
        () => allItems.filter((item) => !dismissedIds.has(item.id)),
        [allItems, dismissedIds],
    );

    const badgeCount = visibleItems.length;
    const loading = alertsLoading && allItems.length === 0;
    const groupedItems = useMemo(() => ({
        attention: visibleItems.filter((item) => item.section === 'attention'),
        operations: visibleItems.filter((item) => item.section === 'operations'),
        system: visibleItems.filter((item) => item.section === 'system'),
    }), [visibleItems]);

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
            visibleItems.forEach((item) => next.add(item.id));
            saveDismissedIds(next);
            return next;
        });
    };

    const sectionEntries = [
        ['attention', t('activity.sections.attention')],
        ['operations', t('activity.sections.operations')],
        ['system', t('activity.sections.system')],
    ];

    return (
        <>
            <button
                type="button"
                className="btn-minimal relative"
                onClick={() => setOpen((prev) => !prev)}
                title={t('activity.title')}
                aria-label={t('activity.title')}
            >
                <Bell size={16} />
                {hasActiveJobs && (
                    <span className="absolute -left-1.5 -top-1.5 h-2.5 w-2.5 rounded-full bg-primary" />
                )}
                {badgeCount > 0 && (
                    <span className="absolute -right-1 -top-1 inline-flex min-w-5 items-center justify-center rounded-full border border-destructive/35 bg-destructive px-1.5 py-0.5 text-[10px] font-semibold text-destructive-foreground">
                        {badgeCount > 99 ? '99+' : badgeCount}
                    </span>
                )}
            </button>

            <div className={`layer-overlay fixed inset-0 bg-slate-950/30 backdrop-blur-[2px] transition-opacity ${open ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'}`}>
                <aside
                    ref={drawerRef}
                    className={`activity-drawer fixed inset-y-0 right-0 flex w-full max-w-[440px] flex-col border-l border-border/70 bg-card shadow-2xl transition-transform ${open ? 'translate-x-0' : 'translate-x-full'}`}
                    aria-hidden={!open}
                >
                    <header className="border-b border-border/70 px-4 py-4">
                        <div className="flex items-start justify-between gap-3">
                            <div>
                                <div className="text-sm font-semibold">{t('activity.title')}</div>
                                <p className="mt-1 text-sm text-muted-foreground">{t('activity.subtitle')}</p>
                            </div>
                            <button
                                type="button"
                                onClick={() => setOpen(false)}
                                className="ghost-icon-button h-9 w-9 p-0"
                                aria-label={t('common.close')}
                            >
                                <X size={14} />
                            </button>
                        </div>
                        <div className="mt-4 grid grid-cols-3 gap-2">
                            <div className="rounded-xl border border-border/70 bg-background/80 px-3 py-2">
                                <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('activity.summary.unread')}</div>
                                <div className="mt-1 text-lg font-semibold">{badgeCount}</div>
                            </div>
                            <div className="rounded-xl border border-border/70 bg-background/80 px-3 py-2">
                                <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('activity.summary.activeJobs')}</div>
                                <div className="mt-1 text-lg font-semibold">{hasActiveJobs ? t('common.yes') : t('common.no')}</div>
                            </div>
                            <div className="rounded-xl border border-border/70 bg-background/80 px-3 py-2">
                                <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('activity.summary.alerts')}</div>
                                <div className="mt-1 text-lg font-semibold">{groupedItems.attention.length}</div>
                            </div>
                        </div>
                        <div className="mt-4 flex items-center justify-between gap-2">
                            <button
                                type="button"
                                onClick={() => navigate('/jobs')}
                                className="btn-minimal text-xs"
                            >
                                <ChevronRight size={12} />
                                {t('activity.openJobs')}
                            </button>
                            <button
                                type="button"
                                onClick={dismissAll}
                                disabled={visibleItems.length === 0}
                                className="btn-minimal px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
                            >
                                <CheckCheck size={12} />
                                {t('activity.dismissAll')}
                            </button>
                        </div>
                    </header>

                    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
                        {loading && (
                            <div className="flex items-center justify-center py-10 text-muted-foreground">
                                <Loader2 className="h-4 w-4 animate-spin" />
                            </div>
                        )}

                        {!loading && visibleItems.length === 0 && (
                            <div className="empty-state border-dashed">
                                <div className="empty-state-icon">
                                    <ShieldAlert size={22} />
                                </div>
                                <div className="empty-state-title">{t('activity.none')}</div>
                                <p className="empty-state-text">{t('activity.noneHelp')}</p>
                            </div>
                        )}

                        {!loading && visibleItems.length > 0 && (
                            <div className="space-y-5">
                                {sectionEntries.map(([sectionKey, sectionLabel]) => {
                                    const sectionItems = groupedItems[sectionKey];
                                    if (!sectionItems || sectionItems.length === 0) return null;

                                    return (
                                        <section key={sectionKey} className="space-y-2">
                                            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                                                {sectionLabel}
                                            </div>
                                            <div className="space-y-2">
                                                {sectionItems.map((item) => (
                                                    <article key={item.id} className="rounded-2xl border border-border/70 bg-background/90 p-3 shadow-sm">
                                                        <div className="flex items-start justify-between gap-3">
                                                            <div className="min-w-0 flex-1">
                                                                <div className="mb-2 inline-flex">
                                                                    <span className={`status-badge ${getActivityToneClass(item.kind)}`}>
                                                                        {item.kind.toUpperCase()}
                                                                    </span>
                                                                </div>
                                                                <div className="text-sm font-semibold">{item.title}</div>
                                                                <p className="mt-1 text-sm text-muted-foreground">{item.message}</p>
                                                                <div className="mt-2 flex flex-wrap items-center gap-3">
                                                                    <span className="text-[11px] text-muted-foreground">
                                                                        {relativeTime(item.createdAt, t)}
                                                                    </span>
                                                                    {item.target && (
                                                                        <button
                                                                            type="button"
                                                                            className="text-xs font-medium text-primary hover:underline"
                                                                            onClick={() => {
                                                                                navigate(item.target.to, { state: item.target.state || null });
                                                                                setOpen(false);
                                                                            }}
                                                                        >
                                                                            {item.target.label}
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            </div>
                                                            <button
                                                                type="button"
                                                                onClick={() => dismissOne(item.id)}
                                                                className="ghost-icon-button h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                                                                title={t('activity.dismiss')}
                                                            >
                                                                <X size={12} />
                                                            </button>
                                                        </div>
                                                    </article>
                                                ))}
                                            </div>
                                        </section>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </aside>
            </div>
        </>
    );
}
