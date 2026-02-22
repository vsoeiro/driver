import { useEffect, useRef, useState } from 'react';
import { NavLink, useLocation, useParams } from 'react-router-dom';
import { accountsService } from '../services/accounts';
import { driveService } from '../services/drive';
import ProviderIcon from './ProviderIcon';
import ProviderPickerModal from './ProviderPickerModal';

const { getAccounts, linkAccount } = accountsService;
const { getQuota } = driveService;
import {
    Plus,
    Cloud,
    Activity,
    Database,
    FileText,
    Wand2,
    Settings,
    Menu,
    ChevronDown,
    PanelLeftClose,
    PanelLeftOpen,
} from 'lucide-react';

export default function Sidebar({ collapsed = false, onToggleCollapse }) {
    const { accountId } = useParams();
    const location = useLocation();
    const [accounts, setAccounts] = useState([]);
    const [quotas, setQuotas] = useState({});
    const [pickerOpen, setPickerOpen] = useState(false);
    const [menuOpen, setMenuOpen] = useState(false);
    const menuRef = useRef(null);

    useEffect(() => {
        getAccounts().then(async (data) => {
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
        }).catch(console.error);
    }, []);

    const handleLinkAccount = (provider) => {
        linkAccount(provider);
    };

    const formatBytes = (bytes) => {
        if (!bytes) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    };

    const activeAccount = accounts.find(a => a.id === accountId);
    const activeQuota = activeAccount ? quotas[activeAccount.id] : null;
    const quickLinks = [
        { to: '/jobs', label: 'Jobs', icon: Activity },
        { to: '/metadata', label: 'Metadata', icon: Database },
        { to: '/all-files', label: 'File Library', icon: FileText },
        { to: '/rules', label: 'Rules', icon: Wand2 },
        { to: '/admin', label: 'Admin', icon: Settings },
    ];

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (menuRef.current && !menuRef.current.contains(event.target)) {
                setMenuOpen(false);
            }
        };

        const handleEscape = (event) => {
            if (event.key === 'Escape') {
                setMenuOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        document.addEventListener('keydown', handleEscape);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
            document.removeEventListener('keydown', handleEscape);
        };
    }, []);

    useEffect(() => {
        setMenuOpen(false);
    }, [location.pathname]);

    useEffect(() => {
        if (collapsed) {
            setMenuOpen(false);
        }
    }, [collapsed]);

    return (
        <aside className={`border-r bg-muted/10 flex flex-col h-screen sticky top-0 transition-[width] duration-200 ${collapsed ? 'w-24' : 'w-64'}`}>
            <div className={`border-b ${collapsed ? 'px-2 py-3 flex flex-col items-center gap-2' : 'p-4 flex items-center gap-2'}`}>
                <div className="p-2 bg-primary text-primary-foreground rounded-lg">
                    <Cloud size={20} />
                </div>
                {!collapsed && <span className="font-bold text-lg">Driver</span>}
                <button
                    type="button"
                    onClick={onToggleCollapse}
                    className="inline-flex items-center justify-center h-8 w-8 rounded-md border bg-background/70 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                    aria-label={collapsed ? 'Expandir barra lateral' : 'Minimizar barra lateral'}
                    title={collapsed ? 'Expandir barra lateral' : 'Minimizar barra lateral'}
                >
                    {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
                </button>
            </div>

            <div className={`flex-1 overflow-y-auto ${collapsed ? 'p-2' : 'p-4'}`}>
                {!collapsed && (
                    <div className="text-xs font-semibold text-muted-foreground mb-3 text-center uppercase tracking-wider">
                        Accounts
                    </div>
                )}
                <nav className={collapsed ? 'space-y-1' : 'space-y-2'}>
                    {accounts.map(acc => (
                        <NavLink
                            key={acc.id}
                            to={`/drive/${acc.id}`}
                            title={`${acc.display_name} (${acc.email})`}
                            className={({ isActive }) => `
                                flex items-center ${collapsed ? 'justify-center px-2' : 'gap-3 px-3'} py-2 rounded-md text-sm font-medium transition-colors
                                ${isActive
                                    ? 'bg-primary text-primary-foreground shadow-sm'
                                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                                }
                            `}
                        >
                            <ProviderIcon provider={acc.provider} className="w-[18px] h-[18px] shrink-0" />
                            {!collapsed && (
                                <div className="flex-1 min-w-0 flex flex-col">
                                    <span className="truncate font-medium leading-none">{acc.display_name}</span>
                                    <span className={`text-xs truncate ${acc.id === accountId ? 'text-primary-foreground/80' : 'text-muted-foreground'}`}>
                                        {acc.email}
                                    </span>
                                </div>
                            )}
                        </NavLink>
                    ))}
                </nav>
            </div>

            <div className={`${collapsed ? 'p-2' : 'p-4'} border-t space-y-2`}>
                {!collapsed && activeQuota && (
                    <div className="bg-card p-3 rounded-md border shadow-sm">
                        <div className="text-xs font-semibold text-muted-foreground mb-2 flex justify-between">
                            <span>Storage</span>
                            <span>{Math.round((activeQuota.used / activeQuota.total) * 100)}%</span>
                        </div>
                        <div className="flex justify-between text-xs mb-1">
                            <span>{formatBytes(activeQuota.used)}</span>
                            <span className="text-muted-foreground">of {formatBytes(activeQuota.total)}</span>
                        </div>
                        <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                            <div
                                className={`h-full rounded-full transition-all duration-500 ${(activeQuota.used / activeQuota.total) > 0.9 ? 'bg-destructive' : 'bg-primary'
                                    }`}
                                style={{ width: `${(activeQuota.used / activeQuota.total) * 100}%` }}
                            />
                        </div>
                    </div>
                )}

                <div className="space-y-2">
                    <button
                        onClick={() => setPickerOpen(true)}
                        className={`flex w-full items-center ${collapsed ? 'justify-center px-2' : 'gap-3 px-3'} bg-primary/10 text-primary hover:bg-primary/20 py-2 rounded-md text-sm font-medium transition-colors`}
                        title="Link Account"
                    >
                        <Plus size={18} className="shrink-0" />
                        {!collapsed && <span>Link Account</span>}
                    </button>
                </div>
            </div>

            <div className={`${collapsed ? 'px-2 pb-2' : 'px-4 pb-4'}`} ref={menuRef}>
                <div className="relative">
                    <button
                        type="button"
                        onClick={() => setMenuOpen((prev) => !prev)}
                        className={`w-full flex items-center ${collapsed ? 'justify-center px-2' : 'justify-between gap-3 px-3'} py-2 rounded-md text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors border bg-background/70`}
                        title="Menu"
                    >
                        <span className={`inline-flex items-center ${collapsed ? '' : 'gap-2'}`}>
                            <Menu size={16} className="shrink-0" />
                            {!collapsed && 'Menu'}
                        </span>
                        {!collapsed && <ChevronDown size={16} className={`transition-transform ${menuOpen ? 'rotate-180' : ''}`} />}
                    </button>

                    {menuOpen && (
                        <div className={`absolute bottom-full mb-2 border rounded-md bg-popover shadow-lg p-1 z-20 ${collapsed ? 'left-0 w-52' : 'left-0 right-0'}`}>
                            {quickLinks.map(({ to, label, icon: Icon }) => (
                                <NavLink
                                    key={to}
                                    to={to}
                                    className={({ isActive }) => `
                                        flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors
                                        ${isActive
                                            ? 'bg-primary text-primary-foreground shadow-sm'
                                            : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                                        }
                                    `}
                                >
                                    <Icon size={16} className="shrink-0" />
                                    <span>{label}</span>
                                </NavLink>
                            ))}
                        </div>
                    )}
                </div>
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
