import { ArrowRight, Bot, Database, FileText, HardDrive, Loader2, RefreshCw, Sparkles, Wand2 } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ProviderIcon from '../components/ProviderIcon';
import { useWorkspacePage } from '../contexts/WorkspaceContext';
import { useJobActivity } from '../contexts/JobActivityContext';
import { useToast } from '../contexts/ToastContext';
import { useAccountsQuery, useItemsListQuery, useQuotaQuery } from '../hooks/useAppQueries';
import { createWorkspaceAction, WORKSPACE_ACTION_IDS } from '../lib/workspace';
import { useJobsActions } from '../features/jobs/hooks/useJobsData';

const LAST_ACCOUNT_STORAGE_KEY = 'driver-last-account-id';

function formatSize(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const exp = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const value = bytes / Math.pow(1024, exp);
    return `${value.toFixed(exp === 0 ? 0 : 1)} ${units[exp]}`;
}

function getProviderLabel(account, t) {
    const provider = String(account?.provider || '').toLowerCase();
    if (provider === 'microsoft' || provider === 'onedrive') return 'OneDrive';
    if (provider === 'google') return 'Google Drive';
    if (provider === 'dropbox') return 'Dropbox';
    return t('accountsHub.connectedProvider');
}

function AccountCard({ account, isLastUsed, syncing, onSync, relatedJobs }) {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const { data: quota, isLoading: quotaLoading } = useQuotaQuery(account.id);
    const { data: mappedItemsResponse, isLoading: mappedItemsLoading } = useItemsListQuery(
        {
            page: 1,
            page_size: 1,
            account_id: account.id,
            item_type: 'file',
        },
        {
            staleTime: 45000,
        },
    );
    const latestJob = relatedJobs[0] || null;
    const used = Number(quota?.used || 0);
    const total = Number(quota?.total || 0);
    const mappedFiles = Number(mappedItemsResponse?.total || 0);
    const usedPercent = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;

    return (
        <article className="account-workspace-card p-3 sm:p-3.5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                    <div className="flex flex-wrap items-start gap-2.5">
                        <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-primary/15 bg-primary/10 text-primary">
                            <ProviderIcon provider={account.provider} className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                                <h2 className="truncate text-base font-semibold">{account.display_name || account.email || account.id}</h2>
                                {isLastUsed && (
                                    <span className="status-chip border-primary/25 bg-primary/10 text-primary">
                                        {t('accountsHub.lastUsed')}
                                    </span>
                                )}
                            </div>
                            <div className="truncate text-sm text-muted-foreground">{account.email || account.id}</div>
                            <div className="mt-2">
                                <span className="workspace-context-chip">{getProviderLabel(account, t)}</span>
                            </div>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2 self-start">
                    <button
                        type="button"
                        onClick={() => navigate(`/drive/${account.id}`)}
                        className="btn-minimal-primary h-8 px-2.5 text-xs"
                    >
                        {t('accountsHub.openDrive')}
                    </button>
                    <button
                        type="button"
                        onClick={() => onSync(account.id)}
                        disabled={syncing}
                        className="btn-minimal h-8 px-2.5 text-xs"
                    >
                        {syncing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                        <span>{t('accountsHub.syncNow')}</span>
                    </button>
                </div>
            </div>

            <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <div className="rounded-xl border border-border/70 bg-background/75 px-2.5 py-2.5">
                    <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('accountsHub.storage')}</div>
                    <div className="mt-1.5 text-sm font-semibold">
                        {quotaLoading ? t('common.loading') : `${formatSize(used)} / ${formatSize(total)}`}
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
                        <div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${usedPercent}%` }} />
                    </div>
                </div>
                <div className="rounded-xl border border-border/70 bg-background/75 px-2.5 py-2.5">
                    <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('accountsHub.mappedFiles')}</div>
                    <div className="mt-1.5 text-sm font-semibold">
                        {mappedItemsLoading ? t('common.loading') : t('accountsHub.mappedFilesCount', { count: mappedFiles })}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">{t('accountsHub.mappedFilesHelp')}</div>
                </div>
                <div className="rounded-xl border border-border/70 bg-background/75 px-2.5 py-2.5">
                    <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('accountsHub.activity')}</div>
                    <div className="mt-1.5 text-sm font-semibold">
                        {latestJob ? latestJob.status : t('accountsHub.noRecentActivity')}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                        {latestJob ? latestJob.type : t('accountsHub.activityHelp')}
                    </div>
                </div>
            </div>
        </article>
    );
}

export default function AccountsRedirect() {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const tx = useCallback((key, defaultValue, options = {}) => t(key, { defaultValue, ...options }), [t]);
    const { showToast } = useToast();
    const { createSyncJob } = useJobsActions();
    const { jobs = [], hasActiveJobs } = useJobActivity();
    const { data: accounts = [], isLoading } = useAccountsQuery();
    const [syncingAccountId, setSyncingAccountId] = useState('');

    const lastUsedAccountId = typeof window !== 'undefined'
        ? window.localStorage.getItem(LAST_ACCOUNT_STORAGE_KEY)
        : '';

    const providerCount = useMemo(
        () => new Set(accounts.map((account) => account.provider).filter(Boolean)).size,
        [accounts],
    );

    const workspaceActions = useMemo(() => ([
        createWorkspaceAction({ id: WORKSPACE_ACTION_IDS.LIBRARY, label: tx('workspace.actions.library', 'Biblioteca'), to: '/all-files' }),
        createWorkspaceAction({ id: WORKSPACE_ACTION_IDS.METADATA, label: tx('workspace.actions.metadata', 'Metadata'), to: '/metadata' }),
        createWorkspaceAction({ id: WORKSPACE_ACTION_IDS.RULES, label: tx('workspace.actions.rules', 'Regras'), to: '/rules' }),
        createWorkspaceAction({ id: WORKSPACE_ACTION_IDS.JOBS, label: tx('workspace.actions.jobs', 'Jobs'), to: '/jobs' }),
        createWorkspaceAction({ id: WORKSPACE_ACTION_IDS.AI, label: tx('workspace.actions.ai', 'IA'), to: '/ai' }),
    ]), [tx]);

    useWorkspacePage(useMemo(() => ({
        title: tx('accountsHub.title', 'Contas e workspaces'),
        subtitle: tx('accountsHub.subtitle', 'Escolha uma conta para explorar o drive ou salte direto para biblioteca, metadata, automacao e IA.'),
        entityType: 'workspace',
        entityId: 'accounts',
        sourceRoute: '/accounts',
        metrics: [
            tx('accountsHub.connectedAccounts', `${accounts.length} conta(s)`, { count: accounts.length }),
            tx('accountsHub.connectedProviders', `${providerCount} provedor(es)`, { count: providerCount }),
            hasActiveJobs ? tx('accountsHub.jobsRunning', 'jobs em execucao') : tx('accountsHub.jobsIdle', 'jobs em espera'),
        ],
        availableActions: workspaceActions,
        suggestedPrompts: [
            tx('workspace.aiPrompts.accountCleanup', 'Como organizar melhor esta conta e reduzir ruido?'),
            tx('workspace.aiPrompts.driveGaps', 'Quais lacunas de classificacao ou organizacao existem aqui?'),
            tx('workspace.aiPrompts.recommend', 'Sugira as proximas acoes com maior impacto.'),
        ],
    }), [accounts.length, hasActiveJobs, providerCount, tx, workspaceActions]));

    const platformLinks = [
        {
            key: 'library',
            icon: FileText,
            title: tx('accountsHub.workspaces.libraryTitle', 'Biblioteca'),
            description: tx('accountsHub.workspaces.libraryDescription', 'Explore tudo, busque rapido e destaque duplicados.'),
            to: '/all-files',
        },
        {
            key: 'metadata',
            icon: Database,
            title: tx('accountsHub.workspaces.metadataTitle', 'Metadata'),
            description: tx('accountsHub.workspaces.metadataDescription', 'Gerencie categorias, bibliotecas e layouts por dominio.'),
            to: '/metadata',
        },
        {
            key: 'automation',
            icon: Wand2,
            title: tx('accountsHub.workspaces.automationTitle', 'Automacao'),
            description: tx('accountsHub.workspaces.automationDescription', 'Crie regras, valide preview e acompanhe jobs.'),
            to: '/rules',
        },
        {
            key: 'jobs',
            icon: Sparkles,
            title: tx('accountsHub.workspaces.jobsTitle', 'Review jobs'),
            description: tx('accountsHub.workspaces.jobsDescription', 'Abra a fila operacional e acompanhe execucoes recentes.'),
            to: '/jobs',
        },
        {
            key: 'ai',
            icon: Bot,
            title: tx('accountsHub.workspaces.aiTitle', 'Assistente'),
            description: tx('accountsHub.workspaces.aiDescription', 'Investigue contexto, riscos e proximos passos.'),
            to: '/ai',
        },
    ];

    const handleSync = useCallback(async (accountId) => {
        setSyncingAccountId(accountId);
        try {
            await createSyncJob(accountId);
            showToast(t('accountsHub.syncQueued'), 'success');
        } catch (error) {
            showToast(error?.response?.data?.detail || t('accountsHub.syncFailed'), 'error');
        } finally {
            setSyncingAccountId('');
        }
    }, [createSyncJob, showToast, t]);

    return (
        <div className="app-page">
            <section className="grid gap-4 xl:grid-cols-[minmax(0,1.8fr)_minmax(320px,1fr)]">
                <div className="space-y-4">
                    <div className="surface-card p-4">
                        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                            <div>
                                <h1 className="text-lg font-semibold">{t('accountsHub.accountsSectionTitle')}</h1>
                                <p className="text-sm text-muted-foreground">{t('accountsHub.accountsSectionSubtitle')}</p>
                            </div>
                            <button
                                type="button"
                                onClick={() => navigate('/all-files')}
                                className="workspace-action-button"
                            >
                                <FileText size={14} />
                                <span>{t('accountsHub.openLibrary')}</span>
                            </button>
                        </div>

                        {isLoading ? (
                            <div className="flex justify-center p-10">
                                <Loader2 className="animate-spin text-primary" size={28} />
                            </div>
                        ) : accounts.length === 0 ? (
                            <div className="empty-state">
                                <div className="empty-state-icon">
                                    <HardDrive size={22} />
                                </div>
                                <div className="empty-state-title">{t('accountsHub.noAccounts')}</div>
                                <p className="empty-state-text">{t('accountsHub.noAccountsHelp')}</p>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {accounts.map((account) => (
                                    <AccountCard
                                        key={account.id}
                                        account={account}
                                        isLastUsed={account.id === lastUsedAccountId}
                                        syncing={syncingAccountId === account.id}
                                        relatedJobs={jobs.filter((job) => job?.payload?.account_id === account.id)}
                                        onSync={handleSync}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                <aside className="space-y-4">
                    <div className="surface-card p-4">
                        <div className="mb-3">
                            <h2 className="text-lg font-semibold">{t('accountsHub.workspacesTitle')}</h2>
                            <p className="text-sm text-muted-foreground">{t('accountsHub.workspacesSubtitle')}</p>
                        </div>
                        <div className="space-y-3">
                            {platformLinks.map((link) => {
                                const Icon = link.icon;
                                return (
                                    <button
                                        key={link.key}
                                        type="button"
                                        onClick={() => navigate(link.to)}
                                        className="w-full rounded-2xl border border-border/70 bg-background/75 px-4 py-3 text-left transition-colors hover:border-primary/20 hover:bg-primary/5"
                                    >
                                        <div className="flex items-center justify-between gap-3">
                                            <div className="flex min-w-0 items-start gap-3">
                                                <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-border/70 bg-card text-primary">
                                                    <Icon size={18} />
                                                </div>
                                                <div className="min-w-0">
                                                    <div className="font-medium text-foreground">{link.title}</div>
                                                    <div className="mt-1 text-sm text-muted-foreground">{link.description}</div>
                                                </div>
                                            </div>
                                            <ArrowRight size={16} className="shrink-0 text-muted-foreground" />
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                </aside>
            </section>
        </div>
    );
}
