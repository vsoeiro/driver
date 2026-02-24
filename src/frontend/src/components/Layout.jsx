import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Link2, Settings } from 'lucide-react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import ProviderPickerModal from './ProviderPickerModal';
import ProviderIcon from './ProviderIcon';
import { accountsService } from '../services/accounts';

const { getAccounts, linkAccount } = accountsService;
const LAST_ACCOUNT_STORAGE_KEY = 'driver-last-account-id';

export default function Layout() {
    const navigate = useNavigate();
    const location = useLocation();
    const [accounts, setAccounts] = useState([]);
    const [pickerOpen, setPickerOpen] = useState(false);
    const [accountMenuOpen, setAccountMenuOpen] = useState(false);
    const accountMenuRef = useRef(null);

    useEffect(() => {
        getAccounts()
            .then(setAccounts)
            .catch(console.error);
    }, []);

    const selectedAccountId = useMemo(() => {
        const match = location.pathname.match(/^\/drive\/([^/]+)/);
        return match ? match[1] : '';
    }, [location.pathname]);

    const selectedAccount = useMemo(
        () => accounts.find((account) => account.id === selectedAccountId) || null,
        [accounts, selectedAccountId]
    );

    const showAccountSelector = location.pathname.startsWith('/drive/') || location.pathname === '/accounts';

    useEffect(() => {
        if (!accountMenuOpen) return undefined;

        const onDocumentClick = (event) => {
            if (!accountMenuRef.current?.contains(event.target)) {
                setAccountMenuOpen(false);
            }
        };

        document.addEventListener('mousedown', onDocumentClick);
        return () => {
            document.removeEventListener('mousedown', onDocumentClick);
        };
    }, [accountMenuOpen]);

    useEffect(() => {
        if (!selectedAccountId) return;
        window.localStorage.setItem(LAST_ACCOUNT_STORAGE_KEY, selectedAccountId);
    }, [selectedAccountId]);

    return (
        <div className="app-shell">
            <div className="min-h-screen p-3 sm:p-4">
                <div className="app-panel flex h-[calc(100vh-1.5rem)] overflow-hidden">
                    <Sidebar />
                    <div className="flex flex-1 min-w-0 min-h-0 flex-col">
                        <header className="relative z-[90] border-b border-border/70 px-4 py-3 md:px-5">
                            <div className="flex items-center justify-between gap-3">
                                {showAccountSelector ? (
                                    <div className="relative flex min-w-0 items-center gap-3" ref={accountMenuRef}>
                                        <span className="text-sm font-medium text-muted-foreground">Account</span>
                                        <button
                                            type="button"
                                            className="input-shell inline-flex h-10 min-w-[240px] max-w-[360px] items-center justify-between gap-2 px-3 text-sm"
                                            onClick={() => setAccountMenuOpen((prev) => !prev)}
                                            disabled={accounts.length === 0}
                                        >
                                            <span className="inline-flex min-w-0 items-center gap-2">
                                                {selectedAccount ? (
                                                    <>
                                                        <ProviderIcon provider={selectedAccount.provider} className="h-4 w-4 shrink-0" />
                                                        <span className="truncate">{selectedAccount.email}</span>
                                                    </>
                                                ) : (
                                                    <span className="text-muted-foreground">Select an account</span>
                                                )}
                                            </span>
                                            <ChevronDown size={16} className="shrink-0 text-muted-foreground" />
                                        </button>
                                        {accountMenuOpen && accounts.length > 0 && (
                                            <div className="absolute left-[72px] top-11 z-[140] max-h-72 w-[360px] overflow-auto rounded-lg border border-border bg-card p-1 shadow-lg">
                                                {accounts.map((account) => (
                                                    <button
                                                        key={account.id}
                                                        type="button"
                                                        className="flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left hover:bg-accent/60"
                                                        onClick={() => {
                                                            setAccountMenuOpen(false);
                                                            navigate(`/drive/${account.id}`);
                                                        }}
                                                    >
                                                        <span className="inline-flex min-w-0 items-center gap-2">
                                                            <ProviderIcon provider={account.provider} className="h-4 w-4 shrink-0" />
                                                            <span className="truncate text-sm">{account.email}</span>
                                                        </span>
                                                        {account.id === selectedAccountId && <Check size={14} className="text-primary" />}
                                                    </button>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div />
                                )}
                                <div className="flex items-center gap-2">
                                    <button
                                        type="button"
                                        onClick={() => setPickerOpen(true)}
                                        className="ghost-icon-button"
                                        title="Link Account"
                                        aria-label="Link Account"
                                    >
                                        <Link2 size={16} />
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => navigate('/admin/settings')}
                                        className="ghost-icon-button"
                                        title="Settings"
                                        aria-label="Settings"
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
        </div>
    );
}
