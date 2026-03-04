import { useEffect, useMemo, useState } from 'react';
import { Bot, Check, ChevronDown, Link2, Settings, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Sidebar from './Sidebar';
import NotificationBell from './NotificationBell';
import ProviderPickerModal from './ProviderPickerModal';
import ProviderIcon from './ProviderIcon';
import AIAssistantWorkspace from './AIAssistantWorkspace';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from './ui/dropdown-menu';
import { accountsService } from '../services/accounts';

const { getAccounts, linkAccount } = accountsService;
const LAST_ACCOUNT_STORAGE_KEY = 'driver-last-account-id';

export default function Layout() {
    const navigate = useNavigate();
    const location = useLocation();
    const { t } = useTranslation();
    const [pickerOpen, setPickerOpen] = useState(false);
    const [quickAiOpen, setQuickAiOpen] = useState(false);

    const { data: accounts = [] } = useQuery({
        queryKey: ['accounts'],
        queryFn: getAccounts,
        staleTime: 60000,
    });

    const selectedAccountId = useMemo(() => {
        const match = location.pathname.match(/^\/drive\/([^/]+)/);
        return match ? match[1] : '';
    }, [location.pathname]);

    const selectedAccount = useMemo(
        () => accounts.find((account) => account.id === selectedAccountId) || null,
        [accounts, selectedAccountId]
    );

    const showAccountSelector = location.pathname.startsWith('/drive/') || location.pathname === '/accounts';
    const showQuickAiLauncher = !location.pathname.startsWith('/ai');

    useEffect(() => {
        if (!showQuickAiLauncher) setQuickAiOpen(false);
    }, [showQuickAiLauncher]);

    useEffect(() => {
        if (!selectedAccountId) return;
        window.localStorage.setItem(LAST_ACCOUNT_STORAGE_KEY, selectedAccountId);
    }, [selectedAccountId]);

    return (
        <div className="app-shell">
            <div className="min-h-screen">
                <div className="app-panel flex h-screen overflow-hidden rounded-none shadow-none">
                    <Sidebar />
                    <div className="flex flex-1 min-w-0 min-h-0 flex-col">
                        <header className="layer-overlay relative flex h-14 items-center border-b border-border px-3 md:px-4">
                            <div className="flex w-full items-center justify-between gap-2">
                                {showAccountSelector ? (
                                    <div className="relative flex min-w-0 items-center gap-2">
                                        <span className="text-xs font-medium text-muted-foreground">{t('layout.account')}</span>
                                        <DropdownMenu>
                                            <DropdownMenuTrigger
                                                className="input-shell inline-flex h-9 min-w-[220px] max-w-[340px] items-center justify-between gap-2 px-2.5 text-sm disabled:opacity-50"
                                                disabled={accounts.length === 0}
                                            >
                                                <span className="inline-flex min-w-0 items-center gap-2">
                                                    {selectedAccount ? (
                                                        <>
                                                            <ProviderIcon provider={selectedAccount.provider} className="h-4 w-4 shrink-0" />
                                                            <span className="truncate">{selectedAccount.email}</span>
                                                        </>
                                                    ) : (
                                                        <span className="text-muted-foreground">{t('layout.selectAccount')}</span>
                                                    )}
                                                </span>
                                                <ChevronDown size={16} className="shrink-0 text-muted-foreground" />
                                            </DropdownMenuTrigger>
                                            <DropdownMenuContent
                                                className="layer-popover max-h-72 w-[340px] overflow-auto rounded-sm border-border/90 bg-card p-1"
                                                align="start"
                                            >
                                                {accounts.map((account) => (
                                                    <DropdownMenuItem
                                                        key={account.id}
                                                        className="flex w-full items-center justify-between gap-3 rounded-sm px-3 py-2 text-left"
                                                        onClick={() => {
                                                            navigate(`/drive/${account.id}`);
                                                        }}
                                                    >
                                                        <span className="inline-flex min-w-0 items-center gap-2">
                                                            <ProviderIcon provider={account.provider} className="h-4 w-4 shrink-0" />
                                                            <span className="truncate text-sm">{account.email}</span>
                                                        </span>
                                                        {account.id === selectedAccountId && <Check size={14} className="text-primary" />}
                                                    </DropdownMenuItem>
                                                ))}
                                            </DropdownMenuContent>
                                        </DropdownMenu>
                                    </div>
                                ) : (
                                    <div />
                                )}
                                <div className="flex items-center gap-1.5">
                                    <NotificationBell />
                                    <button
                                        type="button"
                                        onClick={() => setPickerOpen(true)}
                                        className="btn-minimal"
                                        title={t('layout.linkAccount')}
                                        aria-label={t('layout.linkAccount')}
                                    >
                                        <Link2 size={16} />
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => navigate('/admin/settings')}
                                        className="btn-minimal"
                                        title={t('layout.settings')}
                                        aria-label={t('layout.settings')}
                                    >
                                        <Settings size={16} />
                                    </button>
                                </div>
                            </div>
                        </header>
                        <main className="flex-1 min-w-0 min-h-0 overflow-auto">
                            <Outlet />
                        </main>
                    </div>
                </div>
            </div>
            <ProviderPickerModal
                isOpen={pickerOpen}
                onClose={() => setPickerOpen(false)}
                onSelect={(provider) => {
                    setPickerOpen(false);
                    linkAccount(provider);
                }}
            />
            {showQuickAiLauncher && (
                <>
                    <div
                        className={`fixed bottom-20 right-4 z-[430] h-[min(72vh,560px)] w-[min(96vw,420px)] min-w-[320px] transition-all ${
                            quickAiOpen ? 'opacity-100 translate-y-0 pointer-events-auto' : 'opacity-0 translate-y-2 pointer-events-none'
                        }`}
                        aria-hidden={!quickAiOpen}
                    >
                        <div className="surface-card h-full overflow-hidden shadow-2xl">
                            <div className="h-full min-h-0 p-2">
                                <AIAssistantWorkspace
                                    showPageHeader={false}
                                    compact
                                    startWithDraft
                                    onCompactClose={() => setQuickAiOpen(false)}
                                    className="h-full min-h-0"
                                />
                            </div>
                        </div>
                    </div>

                    <button
                        type="button"
                        onClick={() => setQuickAiOpen((prev) => !prev)}
                        className="fixed bottom-4 right-4 z-[440] inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg shadow-primary/35 transition-transform hover:scale-105"
                        title={quickAiOpen ? t('common.close') : t('sidebar.aiExperimental')}
                        aria-label={quickAiOpen ? t('common.close') : t('sidebar.aiExperimental')}
                    >
                        {quickAiOpen ? <X size={18} /> : <Bot size={18} />}
                    </button>
                </>
            )}
        </div>
    );
}
