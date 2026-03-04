import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, ArrowDown, ArrowUp, CheckSquare, ChevronLeft, ChevronRight, Copy, Loader2, RefreshCcw, Square, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { itemsService } from '../services/items';
import { driveService } from '../services/drive';
import { jobsService } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';

function formatSize(bytes) {
    const value = Number(bytes) || 0;
    if (value === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(value) / Math.log(k));
    return `${parseFloat((value / (k ** i)).toFixed(2))} ${sizes[i]}`;
}

export default function SimilarFilesReportTab({ accounts = [] }) {
    const { t } = useTranslation();
    const { showToast } = useToast();
    const [page, setPage] = useState(1);
    const [scope, setScope] = useState('all');
    const [accountId, setAccountId] = useState('');
    const [sortBy, setSortBy] = useState('size');
    const [sortOrder, setSortOrder] = useState('desc');
    const [extensionsInput, setExtensionsInput] = useState('');
    const [hideLowPriority, setHideLowPriority] = useState(true);
    const [selectedKeys, setSelectedKeys] = useState(new Set());
    const [removeDuplicatesModalOpen, setRemoveDuplicatesModalOpen] = useState(false);
    const [preferredKeepAccountId, setPreferredKeepAccountId] = useState('');
    const [creatingRemoveDuplicatesJob, setCreatingRemoveDuplicatesJob] = useState(false);
    const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
    const extensions = useMemo(
        () => extensionsInput.split(',').map((part) => part.trim()).filter(Boolean),
        [extensionsInput]
    );

    const {
        data,
        isLoading,
        isFetching,
        isError,
        refetch,
    } = useQuery({
        queryKey: ['items-similar-report', page, scope, accountId, sortBy, sortOrder, extensions.join('|'), hideLowPriority],
        queryFn: () => itemsService.getSimilarReport({
            page,
            page_size: 20,
            scope,
            account_id: accountId || undefined,
            sort_by: sortBy,
            sort_order: sortOrder,
            extensions,
            hide_low_priority: hideLowPriority,
        }),
        staleTime: 15000,
    });

    const groups = useMemo(() => data?.groups || [], [data?.groups]);
    const totalGroups = data?.total_groups || 0;
    const totalItems = data?.total_items || 0;
    const totalPages = data?.total_pages || 0;
    const collapsedRecords = data?.collapsed_records || 0;
    const totalPotentialSavings = data?.potential_savings_bytes || 0;
    const visibleItems = useMemo(
        () => groups.flatMap((group) => group.items || []),
        [groups]
    );
    const visibleItemsByKey = useMemo(() => {
        const map = new Map();
        visibleItems.forEach((item) => {
            map.set(`${item.account_id}:${item.item_id}`, item);
        });
        return map;
    }, [visibleItems]);
    const selectedVisibleCount = useMemo(() => {
        let count = 0;
        selectedKeys.forEach((key) => {
            if (visibleItemsByKey.has(key)) count += 1;
        });
        return count;
    }, [selectedKeys, visibleItemsByKey]);
    const allVisibleSelected = visibleItems.length > 0 && selectedVisibleCount === visibleItems.length;
    const someVisibleSelected = selectedVisibleCount > 0 && !allVisibleSelected;

    const toggleSelectOne = (item) => {
        const rowKey = `${item.account_id}:${item.item_id}`;
        setSelectedKeys((prev) => {
            const next = new Set(prev);
            if (next.has(rowKey)) next.delete(rowKey);
            else next.add(rowKey);
            return next;
        });
    };

    const toggleSelectAllVisible = () => {
        setSelectedKeys((prev) => {
            const next = new Set(prev);
            if (allVisibleSelected) {
                visibleItems.forEach((item) => next.delete(`${item.account_id}:${item.item_id}`));
            } else {
                groups.forEach((group) => {
                    (group.items || []).slice(1).forEach((item) => {
                        next.add(`${item.account_id}:${item.item_id}`);
                    });
                });
            }
            return next;
        });
    };

    const handleDeleteSelected = async () => {
        if (selectedVisibleCount === 0) return;
        const selectedItems = [];
        selectedKeys.forEach((key) => {
            const item = visibleItemsByKey.get(key);
            if (item) selectedItems.push(item);
        });
        if (selectedItems.length === 0) return;

        const violatingGroups = groups.filter((group) => {
            const totalInGroup = (group.items || []).length;
            if (totalInGroup === 0) return false;
            let selectedInGroup = 0;
            (group.items || []).forEach((item) => {
                if (selectedKeys.has(`${item.account_id}:${item.item_id}`)) selectedInGroup += 1;
            });
            return selectedInGroup >= totalInGroup;
        });
        if (violatingGroups.length > 0) {
            showToast(t('similarFiles.safetyRule'), 'error');
            return;
        }

        setConfirmDeleteOpen(true);
    };

    const confirmDeleteSelected = async () => {
        const selectedItems = [];
        selectedKeys.forEach((key) => {
            const item = visibleItemsByKey.get(key);
            if (item) selectedItems.push(item);
        });
        if (selectedItems.length === 0) {
            setConfirmDeleteOpen(false);
            return;
        }

        const byAccount = new Map();
        selectedItems.forEach((item) => {
            const list = byAccount.get(item.account_id) || [];
            list.push(item.item_id);
            byAccount.set(item.account_id, list);
        });

        try {
            await Promise.all(
                Array.from(byAccount.entries()).map(([accId, itemIds]) =>
                    driveService.batchDeleteItems(accId, itemIds)
                )
            );
            showToast(t('similarFiles.deleted', { count: selectedItems.length }), 'success');
            setSelectedKeys((prev) => {
                const next = new Set(prev);
                selectedItems.forEach((item) => next.delete(`${item.account_id}:${item.item_id}`));
                return next;
            });
            await refetch();
        } catch (error) {
            showToast(`${t('similarFiles.failedDelete')}: ${error.message}`, 'error');
        } finally {
            setConfirmDeleteOpen(false);
        }
    };

    const handleOpenRemoveDuplicatesModal = () => {
        const fallbackAccountId = accountId || accounts[0]?.id || '';
        setPreferredKeepAccountId(fallbackAccountId);
        setRemoveDuplicatesModalOpen(true);
    };

    const handleCreateRemoveDuplicatesJob = async () => {
        if (!preferredKeepAccountId) {
            showToast(t('similarFiles.selectPreferredAccount'), 'error');
            return;
        }

        try {
            setCreatingRemoveDuplicatesJob(true);
            const job = await jobsService.createRemoveDuplicatesJob({
                preferred_account_id: preferredKeepAccountId,
                account_id: accountId || null,
                scope,
                extensions,
                hide_low_priority: hideLowPriority,
            });
            showToast(t('similarFiles.jobCreated', { id: String(job.id).slice(0, 8) }), 'success');
            setRemoveDuplicatesModalOpen(false);
        } catch (error) {
            const message = error?.response?.data?.detail || error?.message || t('similarFiles.failedCreateJob');
            showToast(message, 'error');
        } finally {
            setCreatingRemoveDuplicatesJob(false);
        }
    };

    return (
        <div className="flex flex-col gap-4">
            <div className="page-header layer-dropdown flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                    <h2 className="page-title">{t('similarFiles.title')}</h2>
                    <span className="text-xs text-muted-foreground font-normal bg-muted px-2 py-0.5 rounded-full">
                        {t('similarFiles.groups', { count: totalGroups })}
                    </span>
                    <span className="text-xs text-muted-foreground font-normal bg-muted px-2 py-0.5 rounded-full">
                        {t('similarFiles.files', { count: totalItems })}
                    </span>
                    <span className="status-badge status-badge-success">
                        {t('similarFiles.potentialSavings', { value: formatSize(totalPotentialSavings) })}
                    </span>
                    {collapsedRecords > 0 && (
                        <span className="status-badge status-badge-warning">
                            {t('similarFiles.collapsed', { count: collapsedRecords })}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <select
                        className="input-shell px-2 py-1.5 text-sm"
                        value={scope}
                        onChange={(event) => {
                            setPage(1);
                            setScope(event.target.value);
                        }}
                    >
                        <option value="all">{t('similarFiles.allMatches')}</option>
                        <option value="same_account">{t('similarFiles.sameAccount')}</option>
                        <option value="cross_account">{t('similarFiles.crossAccount')}</option>
                    </select>
                    <select
                        className="input-shell px-2 py-1.5 text-sm"
                        value={sortBy}
                        onChange={(event) => {
                            setPage(1);
                            setSortBy(event.target.value);
                        }}
                    >
                        <option value="size">{t('similarFiles.sortSize')}</option>
                        <option value="name">{t('similarFiles.sortName')}</option>
                    </select>
                    <button
                        type="button"
                        className="input-shell px-2 py-1.5 text-sm inline-flex items-center justify-center"
                        onClick={() => {
                            setPage(1);
                            setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
                        }}
                        title={t('fileBrowser.sortOrder')}
                        aria-label={t('fileBrowser.sortOrder')}
                    >
                        {sortOrder === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
                    </button>
                    <select
                        className="input-shell px-2 py-1.5 text-sm"
                        value={accountId}
                        onChange={(event) => {
                            setPage(1);
                            setAccountId(event.target.value);
                        }}
                    >
                        <option value="">{t('similarFiles.allAccounts')}</option>
                        {accounts.map((account) => (
                            <option key={account.id} value={account.id}>
                                {account.email || account.display_name}
                            </option>
                        ))}
                    </select>
                    <input
                        type="text"
                        className="input-shell px-2 py-1.5 text-sm w-52"
                        placeholder={t('similarFiles.extensionsPlaceholder')}
                        value={extensionsInput}
                        onChange={(event) => {
                            setPage(1);
                            setExtensionsInput(event.target.value);
                        }}
                    />
                    <button type="button" onClick={() => refetch()} className="btn-minimal">
                        <RefreshCcw size={14} className={isFetching ? 'animate-spin' : ''} />
                        {t('similarFiles.refresh')}
                    </button>
                    <label className="text-sm text-muted-foreground inline-flex items-center gap-2 px-2">
                        <input
                            type="checkbox"
                            checked={hideLowPriority}
                            onChange={(event) => {
                                setPage(1);
                                setSelectedKeys(new Set());
                                setHideLowPriority(event.target.checked);
                            }}
                        />
                        {t('similarFiles.hideLowPriority')}
                    </label>
                </div>
            </div>

            <div className="toolbar-surface relative z-40 px-4 py-2 flex items-center justify-end gap-2 text-sm">
                <span className="text-muted-foreground">{t('similarFiles.selected', { count: selectedVisibleCount })}</span>
                <button
                    type="button"
                    onClick={handleOpenRemoveDuplicatesModal}
                    className="btn-minimal-danger text-xs"
                >
                    <Trash2 size={13} />
                    {t('similarFiles.removeDuplicatesJob')}
                </button>
                <button
                    type="button"
                    onClick={handleDeleteSelected}
                    disabled={selectedVisibleCount === 0}
                    className="btn-minimal-danger text-xs disabled:opacity-50"
                >
                    <Trash2 size={13} />
                    {t('similarFiles.deleteSelected')}
                </button>
                <span className="text-muted-foreground">{t('similarFiles.pageOf', { page, total: Math.max(totalPages, 1) })}</span>
                <button
                    disabled={page <= 1 || isLoading}
                    onClick={() => setPage((prev) => prev - 1)}
                    className="p-1 hover:bg-background rounded disabled:opacity-50"
                >
                    <ChevronLeft size={16} />
                </button>
                <button
                    disabled={page >= totalPages || totalPages === 0 || isLoading}
                    onClick={() => setPage((prev) => prev + 1)}
                    className="p-1 hover:bg-background rounded disabled:opacity-50"
                >
                    <ChevronRight size={16} />
                </button>
            </div>

            <Modal
                isOpen={removeDuplicatesModalOpen}
                onClose={() => !creatingRemoveDuplicatesJob && setRemoveDuplicatesModalOpen(false)}
                title={t('similarFiles.removeDuplicatesJob')}
                maxWidthClass="max-w-lg"
            >
                <div className="space-y-4">
                    <p className="text-sm text-muted-foreground">
                        {t('similarFiles.modalDescription')}
                    </p>
                    <div>
                        <label className="block text-sm font-medium mb-1">{t('similarFiles.preferredAccount')}</label>
                        <select
                            className="w-full border rounded-md p-2 bg-background"
                            value={preferredKeepAccountId}
                            onChange={(event) => setPreferredKeepAccountId(event.target.value)}
                            disabled={creatingRemoveDuplicatesJob}
                        >
                            <option value="">{t('similarFiles.selectAccount')}</option>
                            {accounts.map((account) => (
                                <option key={account.id} value={account.id}>
                                    {account.email || account.display_name}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="rounded-md border border-border/70 bg-muted/30 p-3 text-xs text-muted-foreground space-y-1">
                        <div>{t('similarFiles.scope')}: {scope}</div>
                        <div>{t('similarFiles.accountFilter')}: {accountId ? (accounts.find((acc) => acc.id === accountId)?.email || accountId) : t('similarFiles.allAccounts')}</div>
                        <div>{t('similarFiles.extensions')}: {extensions.length > 0 ? extensions.join(', ') : t('similarFiles.all')}</div>
                        <div>{t('similarFiles.hideLowPriority')}: {hideLowPriority ? t('common.yes') : t('common.no')}</div>
                    </div>
                    <div className="flex justify-end gap-2">
                        <button
                            type="button"
                            onClick={() => setRemoveDuplicatesModalOpen(false)}
                            disabled={creatingRemoveDuplicatesJob}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent disabled:opacity-50"
                        >
                            {t('common.cancel')}
                        </button>
                        <button
                            type="button"
                            onClick={handleCreateRemoveDuplicatesJob}
                            disabled={creatingRemoveDuplicatesJob || !preferredKeepAccountId}
                            className="px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50 flex items-center gap-2"
                        >
                            {creatingRemoveDuplicatesJob && <Loader2 className="animate-spin" size={14} />}
                            {t('similarFiles.createJob')}
                        </button>
                    </div>
                </div>
            </Modal>
            <ConfirmDialog
                isOpen={confirmDeleteOpen}
                onCancel={() => setConfirmDeleteOpen(false)}
                onConfirm={confirmDeleteSelected}
                title={t('similarFiles.deleteSelected')}
                description={t('similarFiles.confirmDelete', { count: selectedVisibleCount })}
                confirmLabel={t('similarFiles.deleteSelected')}
                tone="danger"
            />

            {isLoading ? (
                <div className="flex justify-center p-12">
                    <Loader2 className="animate-spin text-primary" size={32} />
                </div>
            ) : isError ? (
                <div className="surface-card p-5 text-sm text-destructive flex items-center gap-2">
                    <AlertCircle size={16} />
                    {t('similarFiles.failedLoad')}
                </div>
            ) : groups.length === 0 ? (
                <div className="empty-state">
                    <div className="empty-state-icon">
                        <Copy size={26} />
                    </div>
                    <div className="empty-state-title">{t('similarFiles.noGroups')}</div>
                    <p className="empty-state-text">{t('similarFiles.noGroupsHelp')}</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {groups.map((group, idx) => (
                        <div key={`${group.match_type}-${group.name}-${group.size}-${idx}`} className="surface-card overflow-hidden">
                            <div className="border-b border-border/70 p-3 flex flex-wrap items-center justify-between gap-2">
                                <div className="min-w-0">
                                    <div className="text-sm font-semibold truncate">
                                        {group.name}
                                    </div>
                                    <div className="text-xs text-muted-foreground flex flex-wrap gap-2 mt-1">
                                        <span>{group.match_type === 'with_extension' ? t('similarFiles.withExtension') : t('similarFiles.withoutExtension')}</span>
                                        <span>{t('similarFiles.size')}: {formatSize(group.size)}</span>
                                        <span>{t('similarFiles.files', { count: group.total_items })}</span>
                                        <span>{t('similarFiles.savings')}: {formatSize(group.potential_savings_bytes || 0)}</span>
                                        <span>{t('similarFiles.accounts', { count: group.total_accounts })}</span>
                                        {group.extensions?.length > 0 && (
                                            <span>{t('similarFiles.extensions')}: {group.extensions.join(', ')}</span>
                                        )}
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    {group.priority_level === 'low' && (
                                        <span className="status-badge status-badge-warning">
                                            {t('similarFiles.lowPriority')}
                                        </span>
                                    )}
                                    {group.has_same_account_matches && (
                                        <span className="status-badge status-badge-info">{t('similarFiles.sameAccount')}</span>
                                    )}
                                    {group.has_cross_account_matches && (
                                        <span className="status-badge status-badge-success">{t('similarFiles.crossAccount')}</span>
                                    )}
                                </div>
                            </div>
                            {group.priority_level === 'low' && group.low_priority_reasons?.length > 0 && (
                                <div className="status-badge status-badge-warning m-3 mt-2 border-b-0 px-3 py-2 text-xs">
                                    {t('similarFiles.lowPriorityReasons')}: {group.low_priority_reasons.join(', ')}
                                </div>
                            )}
                            <div className="clarity-datagrid-shell">
                                <table className="clarity-datagrid table-fixed">
                                    <colgroup>
                                        <col className="w-10" />
                                        <col className="w-72" />
                                        <col className="w-28" />
                                        <col className="w-28" />
                                        <col />
                                    </colgroup>
                                    <thead>
                                        <tr>
                                            <th>
                                                <button type="button" onClick={toggleSelectAllVisible} className="inline-flex items-center">
                                                    {allVisibleSelected ? (
                                                        <CheckSquare size={14} />
                                                    ) : someVisibleSelected ? (
                                                        <CheckSquare size={14} className="opacity-60" />
                                                    ) : (
                                                        <Square size={14} />
                                                    )}
                                                </button>
                                            </th>
                                            <th>{t('similarFiles.account')}</th>
                                            <th>{t('similarFiles.extension')}</th>
                                            <th>{t('similarFiles.size')}</th>
                                            <th>{t('similarFiles.path')}</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {group.items.map((item) => {
                                            const rowKey = `${item.account_id}:${item.item_id}`;
                                            const isSelected = selectedKeys.has(rowKey);
                                            const account = accounts.find((acc) => acc.id === item.account_id);
                                            return (
                                                <tr key={`${group.name}-${item.account_id}-${item.item_id}`}>
                                                    <td>
                                                        <button type="button" onClick={() => toggleSelectOne(item)} className="inline-flex items-center">
                                                            {isSelected ? <CheckSquare size={14} /> : <Square size={14} />}
                                                        </button>
                                                    </td>
                                                    <td className="text-muted-foreground truncate">
                                                        {account?.email || account?.display_name || item.account_id}
                                                    </td>
                                                    <td>{item.extension || '-'}</td>
                                                    <td>{formatSize(item.size)}</td>
                                                    <td className="text-muted-foreground truncate" title={item.path || '-'}>
                                                        {item.path || '-'}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
