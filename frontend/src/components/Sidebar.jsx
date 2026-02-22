import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { accountsService } from '../services/accounts';
import { driveService } from '../services/drive';
import ProviderIcon from './ProviderIcon';
import ProviderPickerModal from './ProviderPickerModal';
import {
    Plus,
    Cloud,
    Activity,
    Database,
    FileText,
    Wand2,
    Settings,
    PanelLeftClose,
    PanelLeftOpen,
    HardDrive,
    ChevronDown,
} from 'lucide-react';

const { getAccounts, linkAccount } = accountsService;
const { getQuota } = driveService;

export default function Sidebar({ collapsed = false, onToggleCollapse }) {
    const [accounts, setAccounts] = useState([]);
    const [quotas, setQuotas] = useState({});
    const [pickerOpen, setPickerOpen] = useState(false);
    const [accountsOpen, setAccountsOpen] = useState(true);

    useEffect(() => {
        getAccounts()
            .then(async (data) => {
                setAccounts(data);
                const quotaMap = {};
                await Promise.all(data.map(async (acc) => {
                    try {
                        const q = await getQuota(acc.id);
                        quotaMap[acc.id] = q;
                    } catch (e) {
                        console.error(`Failed to fetch quota for ${acc.id}`, e);
                    }
                }));
                setQuotas(quotaMap);
            })
            .catch(console.error);
    }, []);

    const handleLinkAccount = (provider) => {
        linkAccount(provider);
    };

    const formatBytes = (bytes) => {
        const safe = Number(bytes);
        if (!Number.isFinite(safe) || safe <= 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(safe) / Math.log(k));
        return `${parseFloat((safe / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
    };

    const quickLinks = [
        { to: '/jobs', label: 'Jobs', icon: Activity },
        { to: '/metadata', label: 'Metadata', icon: Database },
        { to: '/all-files', label: 'File Library', icon: FileText },
        { to: '/rules', label: 'Rules', icon: Wand2 },
        { to: '/admin', label: 'Admin', icon: Settings },
    ];

    return (
        <aside className={`sticky top-0 flex h-full shrink-0 flex-col border-r border-border/70 bg-card/72 backdrop-blur-xl transition-[width] duration-200 ${collapsed ? 'w-24' : 'w-80'}`}>
            <div className={`border-b border-border/70 ${collapsed ? 'px-2 py-3' : 'px-4 py-4'}`}>
                <div className={`flex items-center ${collapsed ? 'justify-center gap-2' : 'justify-between gap-3'}`}>
                    <div className={`inline-flex items-center ${collapsed ? '' : 'gap-3'} min-w-0`}>
                        <div className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-cyan-500 text-primary-foreground shadow-lg shadow-primary/20">
                            <Cloud size={18} />
                        </div>
                        {!collapsed && (
                            <div className="min-w-0">
                                <div className="text-base font-semibold">Driver Hub</div>
                                <div className="text-xs text-muted-foreground">Storage orchestration</div>
                            </div>
                        )}
                    </div>
                    <button
                        type="button"
                        onClick={onToggleCollapse}
                        className="ghost-icon-button"
                        aria-label={collapsed ? 'Expandir barra lateral' : 'Minimizar barra lateral'}
                        title={collapsed ? 'Expandir barra lateral' : 'Minimizar barra lateral'}
                    >
                        {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
                    </button>
                </div>
            </div>

            <div className="flex-1 min-h-0 flex flex-col">
                <div className={`${collapsed ? 'px-2 pt-3' : 'px-3 pt-3'} pb-3 border-b border-border/70`}>
                    {!collapsed && (
                        <div className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                            Navigation
                        </div>
                    )}
                    <nav className={collapsed ? 'space-y-1' : 'space-y-1.5'}>
                        {quickLinks.map(({ to, label, icon: Icon }) => (
                            <NavLink
                                key={to}
                                to={to}
                                title={label}
                                className={({ isActive }) => `
                                    group flex items-center rounded-lg border px-3 py-2 text-sm font-medium transition-all
                                    ${collapsed ? 'justify-center px-2' : 'gap-3'}
                                    ${isActive
                                        ? 'border-primary/35 bg-primary/12 text-primary'
                                        : 'border-transparent text-muted-foreground hover:border-border/80 hover:bg-accent/70 hover:text-foreground'
                                    }
                                `}
                            >
                                <Icon size={16} className="shrink-0" />
                                {!collapsed && <span>{label}</span>}
                            </NavLink>
                        ))}
                    </nav>
                </div>

                <div className={`${collapsed ? 'px-2 py-3' : 'px-3 py-3'} flex-1 min-h-0 overflow-y-auto`}>
                    {!collapsed && (
                        <button
                            type="button"
                            onClick={() => setAccountsOpen((prev) => !prev)}
                            className="mb-2 flex w-full items-center justify-between rounded-lg border border-border/70 bg-card/70 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground hover:bg-accent/45"
                            aria-expanded={accountsOpen}
                            aria-controls="sidebar-accounts-list"
                        >
                            <span>Accounts ({accounts.length})</span>
                            <ChevronDown
                                size={14}
                                className={`transition-transform ${accountsOpen ? 'rotate-0' : '-rotate-90'}`}
                            />
                        </button>
                    )}
                    {accounts.length === 0 ? (
                        <div className={`${collapsed ? 'p-2' : 'p-3'} rounded-lg border border-dashed border-border bg-card/65 text-center`}>
                            {!collapsed && (
                                <>
                                    <div className="text-sm font-medium">No accounts</div>
                                    <div className="text-xs text-muted-foreground mt-1">Link your first provider</div>
                                </>
                            )}
                            {collapsed && <HardDrive size={16} className="mx-auto text-muted-foreground" />}
                        </div>
                    ) : (
                        <nav
                            id="sidebar-accounts-list"
                            className={`${collapsed || accountsOpen ? 'block' : 'hidden'} ${collapsed ? 'space-y-1' : 'space-y-2'}`}
                        >
                            {accounts.map((acc) => {
                                const accountQuota = quotas[acc.id];
                                const accountPct = accountQuota?.total
                                    ? Math.max(0, Math.min(100, (accountQuota.used / accountQuota.total) * 100))
                                    : 0;

                                return (
                                    <NavLink
                                        key={acc.id}
                                        to={`/drive/${acc.id}`}
                                        title={`${acc.display_name} (${acc.email})`}
                                        className={({ isActive }) => `
                                            block rounded-lg border transition-all
                                            ${isActive
                                                ? 'border-primary/35 bg-primary/10 shadow-[0_12px_25px_-20px_rgba(3,90,180,0.6)]'
                                                : 'border-border/70 bg-card/60 hover:border-border hover:bg-accent/45'
                                            }
                                        `}
                                    >
                                        <div className={`flex items-center ${collapsed ? 'justify-center p-2.5' : 'gap-3 p-3'} min-w-0`}>
                                            <div className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                                                <ProviderIcon provider={acc.provider} className="h-[17px] w-[17px]" />
                                            </div>
                                            {!collapsed && (
                                                <div className="min-w-0 flex-1">
                                                    <div className="truncate text-sm font-semibold leading-tight">{acc.display_name}</div>
                                                    <div className="truncate text-xs text-muted-foreground">{acc.email}</div>
                                                </div>
                                            )}
                                        </div>
                                        {!collapsed && accountQuota && (
                                            <div className="px-3 pb-3">
                                                <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
                                                    <span>{formatBytes(accountQuota.used)} / {formatBytes(accountQuota.total)}</span>
                                                    <span>{Math.round(accountPct)}%</span>
                                                </div>
                                                <div className="h-1.5 rounded-md bg-secondary/90">
                                                    <div
                                                        className={`h-full rounded-md ${accountPct > 90 ? 'bg-destructive' : 'bg-primary'}`}
                                                        style={{ width: `${accountPct}%` }}
                                                    />
                                                </div>
                                            </div>
                                        )}
                                    </NavLink>
                                );
                            })}
                        </nav>
                    )}
                </div>
            </div>

            <div className={`${collapsed ? 'px-2 pb-3 pt-2' : 'px-3 pb-4 pt-3'} border-t border-border/70 space-y-2`}>
                <button
                    onClick={() => setPickerOpen(true)}
                    className={`inline-flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-sm font-semibold transition-all ${collapsed
                        ? 'bg-primary/12 text-primary hover:bg-primary/18'
                        : 'bg-primary text-primary-foreground shadow-lg shadow-primary/25 hover:-translate-y-[1px] hover:bg-primary/92'
                    }`}
                    title="Link Account"
                >
                    <Plus size={16} />
                    {!collapsed && <span>Link Account</span>}
                </button>
            </div>

            <ProviderPickerModal
                isOpen={pickerOpen}
                onClose={() => setPickerOpen(false)}
                onSelect={(provider) => {
                    setPickerOpen(false);
                    handleLinkAccount(provider);
                }}
            />
        </aside>
    );
}
