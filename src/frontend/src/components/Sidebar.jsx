import { NavLink, useLocation } from 'react-router-dom';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
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
    ChevronDown,
} from 'lucide-react';
import { accountsService } from '../services/accounts';
import { driveService } from '../services/drive';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible';

const { getAccounts } = accountsService;
const { getQuota } = driveService;

function formatSize(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1);
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
}

export default function Sidebar() {
    const { t } = useTranslation();
    const location = useLocation();
    const [navigationOpen, setNavigationOpen] = useState(false);
    const showQuotaCard = location.pathname === '/accounts' || location.pathname.startsWith('/drive/');

    const { data: accounts = [] } = useQuery({
        queryKey: ['accounts'],
        queryFn: getAccounts,
        staleTime: 60000,
    });

    const selectedAccountId = useMemo(() => {
        const match = location.pathname.match(/^\/drive\/([^/]+)/);
        if (match?.[1]) return match[1];
        return accounts[0]?.id || '';
    }, [accounts, location.pathname]);

    const { data: quota, isLoading: isQuotaLoading, isError: isQuotaError } = useQuery({
        queryKey: ['quota', selectedAccountId],
        queryFn: () => getQuota(selectedAccountId),
        enabled: showQuotaCard && !!selectedAccountId,
        staleTime: 45000,
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
    ];

    return (
        <aside className="sticky top-0 flex h-full w-56 shrink-0 flex-col border-r border-border bg-card xl:w-60">
            <div className="flex h-14 items-center border-b border-border px-3">
                <div className="inline-flex min-w-0 items-center gap-3">
                    <div className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
                        <Cloud size={16} />
                    </div>
                    <div className="min-w-0">
                        <div className="text-sm font-semibold">{t('sidebar.product')}</div>
                    </div>
                </div>
            </div>

            <div className="flex-1 min-h-0 flex flex-col px-2 py-3">
                <Collapsible open={navigationOpen} onOpenChange={setNavigationOpen} className="mb-2">
                    <CollapsibleTrigger className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-xs font-semibold tracking-wide text-muted-foreground hover:bg-accent/70 hover:text-foreground">
                        <span>{t('sidebar.navigation')}</span>
                        <ChevronDown size={14} className={`transition-transform ${navigationOpen ? 'rotate-180' : ''}`} />
                    </CollapsibleTrigger>
                    <CollapsibleContent className="pt-1">
                        <nav className="space-y-1">
                            {quickLinks.map(({ to, label, icon: Icon }) => (
                                <NavLink
                                    key={to}
                                    to={to}
                                    title={label}
                                    className={({ isActive }) => {
                                        const activeByDrive = to === '/accounts' && location.pathname.startsWith('/drive/');
                                        const isLinkActive = isActive || activeByDrive;
                                        return `
                                            group flex items-center rounded-md border px-2.5 py-1.5 text-sm font-medium transition-all
                                            gap-2
                                            ${isLinkActive
                                                ? 'border-primary/35 bg-primary/12 text-primary'
                                                : 'border-transparent text-muted-foreground hover:bg-accent/70 hover:text-foreground'
                                            }
                                        `;
                                    }}
                                >
                                    <Icon size={15} className="shrink-0" />
                                    <span>{label}</span>
                                </NavLink>
                            ))}
                        </nav>
                    </CollapsibleContent>
                </Collapsible>
                {showQuotaCard && (
                    <div className="mt-auto border-t border-border px-2 pt-3">
                        <div className="rounded-md border border-border bg-background px-3 py-2.5">
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
                                    <div className="mb-2 h-1.5 overflow-hidden rounded-md bg-muted">
                                        <div
                                            className="h-full rounded-md bg-primary transition-[width] duration-300"
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
        </aside>
    );
}
