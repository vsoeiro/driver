import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, CheckSquare, ChevronLeft, ChevronRight, Copy, Loader2, RefreshCcw, Square, Trash2 } from 'lucide-react';
import { itemsService } from '../services/items';
import { driveService } from '../services/drive';
import { useToast } from '../contexts/ToastContext';

function formatSize(bytes) {
    const value = Number(bytes) || 0;
    if (value === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(value) / Math.log(k));
    return `${parseFloat((value / (k ** i)).toFixed(2))} ${sizes[i]}`;
}

export default function SimilarFilesReportTab({ accounts = [] }) {
    const { showToast } = useToast();
    const [page, setPage] = useState(1);
    const [scope, setScope] = useState('all');
    const [accountId, setAccountId] = useState('');
    const [sortBy, setSortBy] = useState('size');
    const [sortOrder, setSortOrder] = useState('desc');
    const [extensionsInput, setExtensionsInput] = useState('');
    const [hideLowPriority, setHideLowPriority] = useState(true);
    const [selectedKeys, setSelectedKeys] = useState(new Set());
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

    const groups = data?.groups || [];
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
            showToast('Safety rule: keep at least 1 file per duplicate group.', 'error');
            return;
        }

        const confirmed = window.confirm(`Delete ${selectedItems.length} selected file(s)?`);
        if (!confirmed) return;

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
            showToast(`Deleted ${selectedItems.length} file(s).`, 'success');
            setSelectedKeys((prev) => {
                const next = new Set(prev);
                selectedItems.forEach((item) => next.delete(`${item.account_id}:${item.item_id}`));
                return next;
            });
            await refetch();
        } catch (error) {
            showToast(`Failed to delete selected files: ${error.message}`, 'error');
        }
    };

    return (
        <div className="flex flex-col gap-4">
            <div className="page-header z-[80] flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                    <div className="text-lg font-semibold">Similar Files Report</div>
                    <span className="text-xs text-muted-foreground font-normal bg-muted px-2 py-0.5 rounded-full">
                        {totalGroups} groups
                    </span>
                    <span className="text-xs text-muted-foreground font-normal bg-muted px-2 py-0.5 rounded-full">
                        {totalItems} files
                    </span>
                    <span className="text-xs font-normal bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full">
                        Potential savings: {formatSize(totalPotentialSavings)}
                    </span>
                    {collapsedRecords > 0 && (
                        <span className="text-xs text-muted-foreground font-normal bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full">
                            {collapsedRecords} collapsed duplicates
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
                        <option value="all">All matches</option>
                        <option value="same_account">Same account</option>
                        <option value="cross_account">Cross account</option>
                    </select>
                    <select
                        className="input-shell px-2 py-1.5 text-sm"
                        value={sortBy}
                        onChange={(event) => {
                            setPage(1);
                            setSortBy(event.target.value);
                        }}
                    >
                        <option value="size">Sort: Size</option>
                        <option value="name">Sort: Name</option>
                    </select>
                    <select
                        className="input-shell px-2 py-1.5 text-sm"
                        value={sortOrder}
                        onChange={(event) => {
                            setPage(1);
                            setSortOrder(event.target.value);
                        }}
                    >
                        <option value="desc">Desc</option>
                        <option value="asc">Asc</option>
                    </select>
                    <select
                        className="input-shell px-2 py-1.5 text-sm"
                        value={accountId}
                        onChange={(event) => {
                            setPage(1);
                            setAccountId(event.target.value);
                        }}
                    >
                        <option value="">All accounts</option>
                        {accounts.map((account) => (
                            <option key={account.id} value={account.id}>
                                {account.email || account.display_name}
                            </option>
                        ))}
                    </select>
                    <input
                        type="text"
                        className="input-shell px-2 py-1.5 text-sm w-52"
                        placeholder="Extensions: cbz, cbr"
                        value={extensionsInput}
                        onChange={(event) => {
                            setPage(1);
                            setExtensionsInput(event.target.value);
                        }}
                    />
                    <button
                        type="button"
                        onClick={() => refetch()}
                        className="flex items-center gap-2 px-3 py-2 border rounded-md text-sm font-medium hover:bg-accent"
                    >
                        <RefreshCcw size={14} className={isFetching ? 'animate-spin' : ''} />
                        Refresh
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
                        Hide low priority
                    </label>
                </div>
            </div>

            <div className="toolbar-surface relative z-40 px-4 py-2 flex items-center justify-end gap-2 text-sm">
                <span className="text-muted-foreground">{selectedVisibleCount} selected</span>
                <button
                    type="button"
                    onClick={handleDeleteSelected}
                    disabled={selectedVisibleCount === 0}
                    className="inline-flex items-center gap-2 rounded-md border border-destructive/30 px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10 disabled:opacity-50"
                >
                    <Trash2 size={13} />
                    Delete Selected
                </button>
                <span className="text-muted-foreground">Page {page} of {Math.max(totalPages, 1)}</span>
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

            {isLoading ? (
                <div className="flex justify-center p-12">
                    <Loader2 className="animate-spin text-primary" size={32} />
                </div>
            ) : isError ? (
                <div className="surface-card p-5 text-sm text-destructive flex items-center gap-2">
                    <AlertCircle size={16} />
                    Failed to load similar files report.
                </div>
            ) : groups.length === 0 ? (
                <div className="empty-state">
                    <div className="empty-state-icon">
                        <Copy size={26} />
                    </div>
                    <div className="empty-state-title">No similar groups found</div>
                    <p className="empty-state-text">Try switching scope or account to broaden the report.</p>
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
                                        <span>{group.match_type === 'with_extension' ? 'With extension' : 'Without extension'}</span>
                                        <span>Size: {formatSize(group.size)}</span>
                                        <span>{group.total_items} files</span>
                                        <span>Savings: {formatSize(group.potential_savings_bytes || 0)}</span>
                                        <span>{group.total_accounts} accounts</span>
                                        {group.extensions?.length > 0 && (
                                            <span>Extensions: {group.extensions.join(', ')}</span>
                                        )}
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    {group.priority_level === 'low' && (
                                        <span className="text-xs rounded-full px-2 py-1 bg-amber-100 text-amber-800">
                                            low priority
                                        </span>
                                    )}
                                    {group.has_same_account_matches && (
                                        <span className="text-xs rounded-full px-2 py-1 bg-blue-100 text-blue-700">same account</span>
                                    )}
                                    {group.has_cross_account_matches && (
                                        <span className="text-xs rounded-full px-2 py-1 bg-emerald-100 text-emerald-700">cross account</span>
                                    )}
                                </div>
                            </div>
                            {group.priority_level === 'low' && group.low_priority_reasons?.length > 0 && (
                                <div className="px-3 py-2 text-xs text-amber-800 bg-amber-50 border-b border-amber-200">
                                    Low-priority reasons: {group.low_priority_reasons.join(', ')}
                                </div>
                            )}
                            <div className="overflow-x-auto">
                                <table className="w-full table-fixed text-sm">
                                    <colgroup>
                                        <col className="w-10" />
                                        <col className="w-72" />
                                        <col className="w-28" />
                                        <col className="w-28" />
                                        <col />
                                    </colgroup>
                                    <thead>
                                        <tr className="text-xs uppercase tracking-wider text-muted-foreground bg-muted/40">
                                            <th className="text-left p-2">
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
                                            <th className="text-left p-2 align-middle">Account</th>
                                            <th className="text-left p-2 align-middle">Extension</th>
                                            <th className="text-left p-2 align-middle">Size</th>
                                            <th className="text-left p-2 align-middle">Path</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-border/60">
                                        {group.items.map((item) => {
                                            const rowKey = `${item.account_id}:${item.item_id}`;
                                            const isSelected = selectedKeys.has(rowKey);
                                            const account = accounts.find((acc) => acc.id === item.account_id);
                                            return (
                                                <tr key={`${group.name}-${item.account_id}-${item.item_id}`}>
                                                    <td className="p-2 align-middle">
                                                        <button type="button" onClick={() => toggleSelectOne(item)} className="inline-flex items-center">
                                                            {isSelected ? <CheckSquare size={14} /> : <Square size={14} />}
                                                        </button>
                                                    </td>
                                                    <td className="p-2 align-middle text-muted-foreground truncate">
                                                        {account?.email || account?.display_name || item.account_id}
                                                    </td>
                                                    <td className="p-2 align-middle">{item.extension || '-'}</td>
                                                    <td className="p-2 align-middle">{formatSize(item.size)}</td>
                                                    <td className="p-2 align-middle text-muted-foreground truncate" title={item.path || '-'}>
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
