import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { Archive, Check, ChevronRight, Folder } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAccountsActions } from '../features/accounts/hooks/useAccountsData';
import { useDriveActions } from '../features/drive/hooks/useDriveData';
import Modal from './Modal';

export default function ExtractZipModal({
    isOpen,
    onClose,
    onConfirm,
    selectedItems,
    initialTarget = null,
    submitting = false,
}) {
    const { t } = useTranslation();
    const { getAccounts } = useAccountsActions();
    const { getPath, listFolderEntries } = useDriveActions();
    const [accounts, setAccounts] = useState([]);
    const [selectedAccount, setSelectedAccount] = useState('');
    const [currentFolderId, setCurrentFolderId] = useState('root');
    const [currentPath, setCurrentPath] = useState([]);
    const [folders, setFolders] = useState([]);
    const [loadingAccounts, setLoadingAccounts] = useState(false);
    const [loadingFolders, setLoadingFolders] = useState(false);
    const [deleteSourceAfterExtract, setDeleteSourceAfterExtract] = useState(false);

    const selectedCount = Array.isArray(selectedItems) ? selectedItems.length : 0;
    const previewItems = useMemo(
        () => (Array.isArray(selectedItems) ? selectedItems.slice(0, 3) : []),
        [selectedItems],
    );
    const extraCount = Math.max(0, selectedCount - previewItems.length);

    const currentFolderPath = useMemo(() => {
        if (currentPath.length === 0) {
            return t('folderPicker.root');
        }
        return `${t('folderPicker.root')}/${currentPath.map((part) => part.name).join('/')}`;
    }, [currentPath, t]);

    const restoreFolderState = useCallback(async (accountId, folderId, folderPathHint = '') => {
        const safeFolderId = folderId || 'root';
        setCurrentFolderId(safeFolderId);

        if (!accountId || safeFolderId === 'root') {
            setCurrentPath([]);
            return;
        }

        try {
            const pathData = await getPath(accountId, safeFolderId);
            const breadcrumb = Array.isArray(pathData?.breadcrumb) ? pathData.breadcrumb : [];
            const parts = breadcrumb
                .filter((part) => String(part?.name || '').toLowerCase() !== 'root')
                .map((part) => ({ id: part.id, name: part.name }));
            setCurrentPath(parts);
        } catch {
            const fallbackSegments = String(folderPathHint || '')
                .split('/')
                .map((segment) => segment.trim())
                .filter(Boolean)
                .filter((segment) => segment !== t('folderPicker.root'));
            const fallbackName = fallbackSegments.at(-1);
            setCurrentPath(fallbackName ? [{ id: safeFolderId, name: fallbackName }] : []);
        }
    }, [getPath, t]);

    useEffect(() => {
        if (!isOpen) return;
        let active = true;

        const loadAccounts = async () => {
            setDeleteSourceAfterExtract(false);
            setLoadingAccounts(true);
            try {
                const data = await getAccounts();
                if (!active) return;
                setAccounts(data);
                const initialAccount = data.some((account) => account.id === initialTarget?.account_id)
                    ? initialTarget.account_id
                    : (data[0]?.id || '');
                setSelectedAccount(initialAccount);
                await restoreFolderState(
                    initialAccount,
                    initialAccount ? (initialTarget?.folder_id || 'root') : 'root',
                    initialTarget?.folder_path || '',
                );
            } finally {
                if (active) {
                    setLoadingAccounts(false);
                }
            }
        };

        loadAccounts();

        return () => {
            active = false;
        };
    }, [getAccounts, initialTarget, isOpen, restoreFolderState]);

    useEffect(() => {
        if (!isOpen || !selectedAccount) return;
        let active = true;

        const loadFolders = async () => {
            setLoadingFolders(true);
            try {
                const data = await listFolderEntries(selectedAccount, currentFolderId);
                if (!active) return;
                setFolders((data.items || []).filter((item) => item.item_type === 'folder'));
            } finally {
                if (active) {
                    setLoadingFolders(false);
                }
            }
        };

        loadFolders();

        return () => {
            active = false;
        };
    }, [currentFolderId, isOpen, listFolderEntries, selectedAccount]);

    const canConfirm = Boolean(selectedAccount && currentFolderId && selectedCount > 0 && !submitting);

    const handleConfirm = () => {
        if (!canConfirm) return;
        onConfirm?.({
            target: {
                account_id: selectedAccount,
                folder_id: currentFolderId || 'root',
                folder_path: currentFolderPath,
            },
            deleteSourceAfterExtract,
        });
    };

    const navigateRoot = () => {
        setCurrentPath([]);
        setCurrentFolderId('root');
    };

    const navigateToFolder = (folder) => {
        setCurrentPath((prev) => [...prev, { id: folder.id, name: folder.name }]);
        setCurrentFolderId(folder.id);
    };

    const navigateUp = () => {
        if (currentPath.length === 0) return;
        const nextPath = currentPath.slice(0, -1);
        setCurrentPath(nextPath);
        setCurrentFolderId(nextPath[nextPath.length - 1]?.id || 'root');
    };

    return (
        <Modal
            isOpen={isOpen}
            onClose={() => !submitting && onClose?.()}
            title={(
                <span className="inline-flex items-center gap-2">
                    <Archive className="h-5 w-5 text-primary" />
                    {t('extractZipModal.title')}
                </span>
            )}
            maxWidthClass="max-w-lg"
        >
            <div className="space-y-4">
                <div className="rounded-md border bg-muted/40 p-3">
                    <div className="mb-2 text-sm font-medium text-foreground">
                        {t('extractZipModal.selectedCount', { count: selectedCount })}
                    </div>
                    <div className="space-y-1 text-sm text-muted-foreground">
                        {previewItems.map((item) => (
                            <div key={`${item.account_id}-${item.item_id}`} className="truncate">
                                {item.name}
                            </div>
                        ))}
                        {extraCount > 0 ? (
                            <div>{t('extractZipModal.moreItems', { count: extraCount })}</div>
                        ) : null}
                    </div>
                </div>

                <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">{t('extractZipModal.destination')}</label>

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-foreground">{t('folderPicker.account')}</label>
                        <select
                            value={selectedAccount}
                            onChange={(event) => {
                                const nextAccount = event.target.value;
                                setSelectedAccount(nextAccount);
                                setFolders([]);
                                void restoreFolderState(nextAccount, 'root');
                            }}
                            className="w-full rounded-md border bg-background p-2 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                            disabled={loadingAccounts || accounts.length === 0 || submitting}
                        >
                            {accounts.map((account) => (
                                <option key={account.id} value={account.id}>
                                    {account.display_name} ({account.email})
                                </option>
                            ))}
                        </select>
                    </div>

                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <label className="text-sm font-medium text-foreground">{t('folderPicker.folder')}</label>
                            <button
                                type="button"
                                onClick={navigateUp}
                                disabled={currentPath.length === 0 || submitting}
                                className="text-xs text-primary hover:underline disabled:opacity-50"
                            >
                                {t('folderPicker.goUp')}
                            </button>
                        </div>

                        <div className="overflow-hidden rounded-md border">
                            <div className="flex items-center gap-1 overflow-x-auto border-b bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
                                <button
                                    type="button"
                                    onClick={navigateRoot}
                                    className="whitespace-nowrap hover:text-foreground"
                                    disabled={submitting}
                                >
                                    {t('folderPicker.root')}
                                </button>
                                {currentPath.map((part) => (
                                    <Fragment key={part.id}>
                                        <ChevronRight className="h-3 w-3" />
                                        <span className="whitespace-nowrap">{part.name}</span>
                                    </Fragment>
                                ))}
                            </div>

                            <div className="h-48 space-y-1 overflow-y-auto bg-background p-2">
                                {loadingFolders ? (
                                    <div className="flex justify-center py-4">
                                        <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                                    </div>
                                ) : folders.length === 0 ? (
                                    <div className="py-8 text-center text-sm text-muted-foreground">
                                        {t('folderPicker.noFolders')}
                                    </div>
                                ) : (
                                    folders.map((folder) => (
                                        <button
                                            key={folder.id}
                                            type="button"
                                            onClick={() => navigateToFolder(folder)}
                                            disabled={submitting}
                                            className="flex w-full items-center gap-3 rounded-md p-2 text-left transition-colors hover:bg-accent disabled:opacity-50"
                                        >
                                            <Folder className="h-4 w-4 text-primary/80" />
                                            <span className="truncate text-sm text-foreground">{folder.name}</span>
                                        </button>
                                    ))
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="rounded-md border bg-background p-3 text-sm">
                        <div className="font-medium text-foreground">{t('extractZipModal.destinationReady')}</div>
                        <div className="text-muted-foreground">{currentFolderPath}</div>
                    </div>
                </div>

                <div className="rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground">
                    {t('extractZipModal.helper')}
                </div>

                <label className="flex items-start gap-3 rounded-md border p-3 text-sm">
                    <input
                        type="checkbox"
                        checked={deleteSourceAfterExtract}
                        onChange={(event) => setDeleteSourceAfterExtract(event.target.checked)}
                        disabled={submitting}
                        className="mt-0.5"
                    />
                    <span>
                        <span className="block font-medium text-foreground">{t('extractZipModal.deleteSource')}</span>
                        <span className="block text-muted-foreground">{t('extractZipModal.deleteSourceHelp')}</span>
                    </span>
                </label>

                {!canConfirm ? (
                    <div className="text-sm text-destructive">{t('extractZipModal.destinationRequired')}</div>
                ) : null}

                <div className="flex justify-end gap-3 border-t bg-muted/20 pt-4">
                    <button
                        type="button"
                        onClick={onClose}
                        disabled={submitting}
                        className="px-4 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
                    >
                        {t('common.cancel')}
                    </button>
                    <button
                        type="button"
                        onClick={handleConfirm}
                        disabled={!canConfirm}
                        className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                    >
                        <Check className="h-4 w-4" />
                        {submitting ? t('extractZipModal.processing') : t('extractZipModal.confirm')}
                    </button>
                </div>
            </div>
        </Modal>
    );
}
