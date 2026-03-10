import { NavLink, useLocation } from 'react-router-dom';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
    Cloud,
    Activity,
    Database,
    FileText,
    Wand2,
    HardDrive,
    Gauge,
    Bot,
    Settings,
    X,
} from 'lucide-react';
import { useAccountsQuery, useQuotaQuery } from '../hooks/useAppQueries';

function formatSize(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1);
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
}

function SidebarBody({ location, quickLinks, showQuotaCard, usedPercent, used, total, isQuotaLoading, isQuotaError, onNavigate, t }) {
    return (
        <>
            <div className="flex h-14 items-center justify-between border-b border-border px-3">
                <div className="inline-flex min-w-0 items-center gap-3">
                    <div className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
                        <Cloud size={16} />
                    </div>
                    <div className="min-w-0">
                        <div className="text-sm font-semibold">{t('sidebar.product')}</div>
                    </div>
                </div>
                {onNavigate && (
                    <button
                        type="button"
                        onClick={onNavigate}
                        className="btn-minimal px-2 py-2 lg:hidden"
                        aria-label={t('common.close')}
                    >
                        <X size={16} />
                    </button>
                )}
            </div>

            <div className="flex min-h-0 flex-1 flex-col px-2 py-3">
                <div className="mb-2 px-2 py-1.5 text-xs font-semibold tracking-wide text-muted-foreground">
                    {t('sidebar.navigation')}
                </div>
                <nav className="space-y-1">
                    {quickLinks.map(({ to, label, icon: Icon }) => (
                        <NavLink
                            key={to}
                            to={to}
                            title={label}
                            onClick={onNavigate || undefined}
                            className={({ isActive }) => {
                                const activeByDrive = to === '/accounts' && location.pathname.startsWith('/drive/');
                                const isLinkActive = isActive || activeByDrive;
                                return `
                                    group flex items-center rounded-sm border px-2.5 py-1.5 text-sm font-medium transition-all
                                    gap-2
                                    ${isLinkActive
                                        ? 'border-primary/35 bg-primary/10 text-primary'
                                        : 'border-transparent text-muted-foreground hover:bg-accent/70 hover:text-foreground'
                                    }
                                `;
                            }}
                        >
                            <Icon size={15} className="shrink-0" />
                            <span className="truncate">{label}</span>
                        </NavLink>
                    ))}
                </nav>
                {showQuotaCard && (
                    <div className="mt-auto border-t border-border px-2 pt-3">
                        <div className="rounded-sm border border-border bg-background px-3 py-2.5">
                            <div className="mb-2 inline-flex items-center gap-2 text-xs font-medium text-muted-foreground">
                                <Gauge size={12} />
                                <span>{t('sidebar.quota')}</span>
                            </div>
                            {isQuotaLoading ? (
                                <div className="text-xs text-muted-foreground">{t('common.loading')}</div>
                            ) : isQuotaError ? (
                                <div className="text-xs text-muted-foreground">{t('common.unavailable')}</div>
                            ) : (
                                <>
                                    <div className="mb-1 text-xs font-semibold">{t('sidebar.quotaUsed', { percent: usedPercent })}</div>
                                    <div className="mb-2 h-1.5 overflow-hidden rounded-sm bg-muted">
                                        <div
                                            className="h-full rounded-sm bg-primary transition-[width] duration-300"
                                            style={{ width: `${usedPercent}%` }}
                                        />
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                        {formatSize(used)} / {formatSize(total)}
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </>
    );
}

export default function Sidebar({ mobileOpen = false, onNavigate = null }) {
    const { t } = useTranslation();
    const location = useLocation();
    const showQuotaCard = location.pathname === '/accounts' || location.pathname.startsWith('/drive/');

    const { data: accounts = [] } = useAccountsQuery();

    const selectedAccountId = useMemo(() => {
        const match = location.pathname.match(/^\/drive\/([^/]+)/);
        if (match?.[1]) return match[1];
        return accounts[0]?.id || '';
    }, [accounts, location.pathname]);

    const { data: quota, isLoading: isQuotaLoading, isError: isQuotaError } = useQuotaQuery(selectedAccountId, {
        enabled: showQuotaCard && !!selectedAccountId,
    });

    const used = Number(quota?.used || 0);
    const total = Number(quota?.total || 0);
    const usedPercent = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;

    const quickLinks = [
        { to: '/accounts', label: t('sidebar.accounts'), icon: HardDrive },
        { to: '/all-files', label: t('sidebar.files'), icon: FileText },
        { to: '/metadata', label: t('sidebar.metadata'), icon: Database },
        { to: '/rules', label: t('sidebar.rules'), icon: Wand2 },
        { to: '/jobs', label: t('sidebar.jobs'), icon: Activity },
        { to: '/ai', label: t('sidebar.aiExperimental'), icon: Bot },
        { to: '/admin/dashboard', label: t('sidebar.admin'), icon: Settings },
    ];

    return (
        <>
            <aside className="sticky top-0 hidden h-full w-56 shrink-0 flex-col border-r border-border bg-card lg:flex xl:w-60">
                <SidebarBody
                    location={location}
                    quickLinks={quickLinks}
                    showQuotaCard={showQuotaCard}
                    usedPercent={usedPercent}
                    used={used}
                    total={total}
                    isQuotaLoading={isQuotaLoading}
                    isQuotaError={isQuotaError}
                    onNavigate={null}
                    t={t}
                />
            </aside>

            <div
                className={`layer-overlay fixed inset-0 bg-slate-900/35 transition-opacity duration-200 lg:hidden ${
                    mobileOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
                }`}
                onClick={onNavigate || undefined}
                aria-hidden={!mobileOpen}
            />
            <aside
                className={`layer-overlay fixed inset-y-0 left-0 z-[330] flex w-[min(18rem,calc(100vw-1.5rem))] flex-col border-r border-border bg-card shadow-xl transition-transform duration-200 lg:hidden ${
                    mobileOpen ? 'translate-x-0' : '-translate-x-full'
                }`}
                aria-hidden={!mobileOpen}
            >
                <SidebarBody
                    location={location}
                    quickLinks={quickLinks}
                    showQuotaCard={showQuotaCard}
                    usedPercent={usedPercent}
                    used={used}
                    total={total}
                    isQuotaLoading={isQuotaLoading}
                    isQuotaError={isQuotaError}
                    onNavigate={onNavigate}
                    t={t}
                />
            </aside>
        </>
    );
}
