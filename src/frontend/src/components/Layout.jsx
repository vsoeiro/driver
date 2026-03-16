import { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import { Bot, ChevronLeft, ChevronRight, Link2, Menu, Settings, X } from 'lucide-react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { WorkspaceProvider } from '../contexts/WorkspaceContext';
import ActivityDrawer from './ActivityDrawer';
const LAST_ACCOUNT_STORAGE_KEY = 'driver-last-account-id';
const SIDEBAR_COLLAPSED_STORAGE_KEY = 'driver-sidebar-collapsed-v1';
const AccountSwitcher = lazy(() => import('./AccountSwitcher'));
const Sidebar = lazy(() => import('./Sidebar'));
const ProviderPickerModal = lazy(() => import('./ProviderPickerModal'));
const AIAssistantWorkspace = lazy(() => import('./AIAssistantWorkspace'));
let sidebarModulePromise;
let quickAiModulePromise;
let providerPickerPromise;

function preloadSidebar() {
    sidebarModulePromise ||= import('./Sidebar');
    return sidebarModulePromise;
}

function preloadQuickAiWorkspace() {
    quickAiModulePromise ||= import('./AIAssistantWorkspace');
    return quickAiModulePromise;
}

function preloadProviderPicker() {
    providerPickerPromise ||= import('./ProviderPickerModal');
    return providerPickerPromise;
}

export default function Layout() {
    const navigate = useNavigate();
    const location = useLocation();
    const { t } = useTranslation();
    const [pickerOpen, setPickerOpen] = useState(false);
    const [quickAiOpen, setQuickAiOpen] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [sidebarReady, setSidebarReady] = useState(false);
    const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
        if (typeof window === 'undefined') return false;
        return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === '1';
    });
    const [quickAiRequested, setQuickAiRequested] = useState(false);

    const selectedAccountId = useMemo(() => {
        const match = location.pathname.match(/^\/drive\/([^/]+)/);
        return match ? match[1] : '';
    }, [location.pathname]);

    const showAccountSelector = location.pathname.startsWith('/drive/') || location.pathname === '/accounts';
    const showQuickAiLauncher = !location.pathname.startsWith('/ai');

    useEffect(() => {
        if (!showQuickAiLauncher) setQuickAiOpen(false);
    }, [showQuickAiLauncher]);

    useEffect(() => {
        if (!selectedAccountId) return;
        window.localStorage.setItem(LAST_ACCOUNT_STORAGE_KEY, selectedAccountId);
    }, [selectedAccountId]);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, sidebarCollapsed ? '1' : '0');
    }, [sidebarCollapsed]);

    useEffect(() => {
        setSidebarOpen(false);
    }, [location.pathname]);

    useEffect(() => {
        if (sidebarReady) return undefined;
        if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
            const idleId = window.requestIdleCallback(() => {
                preloadSidebar();
                setSidebarReady(true);
            }, { timeout: 1200 });
            return () => window.cancelIdleCallback(idleId);
        }

        const timeoutId = window.setTimeout(() => {
            preloadSidebar();
            setSidebarReady(true);
        }, 200);
        return () => window.clearTimeout(timeoutId);
    }, [sidebarReady]);

    const openQuickAi = () => {
        setQuickAiRequested(true);
        preloadQuickAiWorkspace();
        setQuickAiOpen(true);
    };

    const toggleQuickAi = () => {
        if (quickAiOpen) {
            setQuickAiOpen(false);
            return;
        }
        openQuickAi();
    };

    return (
        <WorkspaceProvider>
        <div className="app-shell">
            <div className="min-h-screen">
                <div className="app-panel flex min-h-screen overflow-hidden rounded-none shadow-none lg:h-screen">
                    {sidebarReady ? (
                        <Suspense fallback={sidebarCollapsed ? null : <aside className="hidden h-full w-56 shrink-0 border-r border-border bg-card lg:flex xl:w-60" aria-hidden="true" />}>
                            <Sidebar
                                mobileOpen={sidebarOpen}
                                desktopCollapsed={sidebarCollapsed}
                                onNavigate={() => setSidebarOpen(false)}
                            />
                        </Suspense>
                    ) : !sidebarCollapsed ? (
                        <aside className="hidden h-full w-56 shrink-0 border-r border-border bg-card lg:flex xl:w-60" aria-hidden="true" />
                    ) : null}
                    <div className="flex flex-1 min-w-0 min-h-0 flex-col">
                        <header className="layer-overlay relative border-b border-border/80 px-3 py-2 md:px-4 lg:h-16 lg:py-0">
                            <div className="flex w-full flex-col gap-3 lg:h-full lg:flex-row lg:items-center lg:justify-between">
                                <div className="flex min-w-0 items-center gap-2 lg:flex-1">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            preloadSidebar();
                                            setSidebarReady(true);
                                            setSidebarOpen(true);
                                        }}
                                        onMouseEnter={() => {
                                            preloadSidebar();
                                            setSidebarReady(true);
                                        }}
                                        onFocus={() => {
                                            preloadSidebar();
                                            setSidebarReady(true);
                                        }}
                                        className="btn-minimal px-2 py-2 lg:hidden"
                                        aria-label={t('sidebar.navigation')}
                                    >
                                        <Menu size={16} />
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            const nextCollapsed = !sidebarCollapsed;
                                            if (!nextCollapsed) {
                                                preloadSidebar();
                                                setSidebarReady(true);
                                            }
                                            setSidebarCollapsed(nextCollapsed);
                                        }}
                                        onMouseEnter={() => {
                                            if (!sidebarCollapsed) return;
                                            preloadSidebar();
                                            setSidebarReady(true);
                                        }}
                                        onFocus={() => {
                                            if (!sidebarCollapsed) return;
                                            preloadSidebar();
                                            setSidebarReady(true);
                                        }}
                                        className="hidden btn-minimal px-2 py-2 lg:inline-flex"
                                        aria-label={sidebarCollapsed ? t('sidebar.expand') : t('sidebar.collapse')}
                                        title={sidebarCollapsed ? t('sidebar.expand') : t('sidebar.collapse')}
                                    >
                                        {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
                                    </button>
                                    {showAccountSelector ? (
                                        <Suspense fallback={<div className="input-shell h-9 flex-1 animate-pulse sm:max-w-[340px]" />}>
                                            <AccountSwitcher
                                                selectedAccountId={selectedAccountId}
                                                onSelectAccount={(accountId) => navigate(`/drive/${accountId}`)}
                                                accountLabel={t('layout.account')}
                                                placeholderLabel={t('layout.selectAccount')}
                                            />
                                        </Suspense>
                                    ) : (
                                        <div className="flex-1" />
                                    )}
                                </div>
                                <div className="flex items-center justify-end gap-1.5 sm:justify-normal">
                                    <ActivityDrawer />
                                    <button
                                        type="button"
                                        onClick={() => {
                                            preloadProviderPicker();
                                            setPickerOpen(true);
                                        }}
                                        onMouseEnter={preloadProviderPicker}
                                        onFocus={preloadProviderPicker}
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
            {pickerOpen && (
                <Suspense fallback={null}>
                    <ProviderPickerModal
                        isOpen={pickerOpen}
                        onClose={() => setPickerOpen(false)}
                    />
                </Suspense>
            )}
            {showQuickAiLauncher && (
                <>
                    {quickAiOpen && quickAiRequested && (
                        <div
                            className="fixed bottom-20 right-4 z-[430] h-[min(72vh,560px)] w-[min(96vw,420px)] min-w-[min(320px,calc(100vw-2rem))]"
                            aria-hidden={false}
                        >
                            <div className="surface-card h-full overflow-hidden shadow-2xl">
                                <div className="h-full min-h-0 p-2">
                                    <Suspense fallback={<div className="flex h-full items-center justify-center text-sm text-muted-foreground">{t('app.loadingWorkspace')}</div>}>
                                        <AIAssistantWorkspace
                                            showPageHeader={false}
                                            compact
                                            startWithDraft
                                            onCompactClose={() => setQuickAiOpen(false)}
                                            className="h-full min-h-0"
                                        />
                                    </Suspense>
                                </div>
                            </div>
                        </div>
                    )}

                    <button
                        type="button"
                        onClick={toggleQuickAi}
                        onMouseEnter={preloadQuickAiWorkspace}
                        onFocus={preloadQuickAiWorkspace}
                        className="fixed bottom-4 right-4 z-[440] inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg shadow-primary/35 transition-transform hover:scale-105"
                        title={quickAiOpen ? t('common.close') : t('sidebar.aiExperimental')}
                        aria-label={quickAiOpen ? t('common.close') : t('sidebar.aiExperimental')}
                    >
                        {quickAiOpen ? <X size={18} /> : <Bot size={18} />}
                    </button>
                </>
            )}
        </div>
        </WorkspaceProvider>
    );
}
