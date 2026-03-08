import { useState, useEffect, useCallback, Fragment } from 'react';
import { FolderInput, Check, ChevronRight, Folder, File } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { getAccounts } from '../services/accounts';
import { getFiles, getFolderFiles } from '../services/drive';
import { createMoveJob } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';
import Modal from './Modal';

export default function MoveModal({ isOpen, onClose, item, sourceAccountId, onSuccess }) {
    const { t } = useTranslation();
    const [accounts, setAccounts] = useState([]);
    const [selectedAccount, setSelectedAccount] = useState('');
    const [currentPath, setCurrentPath] = useState([]);
    const [currentFolderId, setCurrentFolderId] = useState('root');
    const [folders, setFolders] = useState([]);
    const [loading, setLoading] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const { showToast } = useToast();

    const loadAccounts = useCallback(async () => {
        try {
            const data = await getAccounts();
            setAccounts(data);
            setSelectedAccount((current) => {
                if (current || data.length === 0) return current;
                return sourceAccountId || data[0].id;
            });
        } catch (error) {
            console.error('Failed to load accounts:', error);
            showToast(t('moveModal.failedLoadAccounts'), 'error');
        }
    }, [sourceAccountId, showToast, t]);

    const loadFolders = useCallback(async (accountId, folderId) => {
        setLoading(true);
        try {
            const data = folderId === 'root'
                ? await getFiles(accountId)
                : await getFolderFiles(accountId, folderId);
            setFolders(data.items || []);
        } catch (error) {
            console.error('Failed to load folders:', error);
            showToast(`${t('moveModal.failedLoadFolder')}: ${error.message}`, 'error');
            setFolders([]);
        } finally {
            setLoading(false);
        }
    }, [showToast, t]);

    useEffect(() => {
        if (!isOpen) return;
        loadAccounts();
        setCurrentPath([]);
        setCurrentFolderId('root');
    }, [isOpen, loadAccounts]);

    useEffect(() => {
        if (!isOpen || !selectedAccount) return;
        loadFolders(selectedAccount, currentFolderId);
    }, [isOpen, selectedAccount, currentFolderId, loadFolders]);

    const handleMove = async () => {
        if (!selectedAccount || !item) return;
        setSubmitting(true);
        try {
            await createMoveJob(
                sourceAccountId,
                item.id,
                selectedAccount,
                currentFolderId,
            );
            showToast(t('moveModal.jobStarted', { name: item.name }), 'success');
            onSuccess();
            onClose();
        } catch (error) {
            console.error('Failed to create move job:', error);
            showToast(`${t('moveModal.failedStart')}: ${error.message}`, 'error');
        } finally {
            setSubmitting(false);
        }
    };

    const navigateToFolder = (folder) => {
        if (!folder.id) {
            showToast(t('moveModal.missingFolderId'), 'error');
            return;
        }
        setCurrentPath([...currentPath, folder]);
        setCurrentFolderId(folder.id);
    };

    const navigateUp = () => {
        if (currentPath.length === 0) return;
        const newPath = currentPath.slice(0, -1);
        setCurrentPath(newPath);
        setCurrentFolderId(newPath.length > 0 ? newPath[newPath.length - 1].id : 'root');
    };

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title={(
                <span className="inline-flex items-center gap-2">
                    <FolderInput className="h-5 w-5 text-primary" />
                    {t('moveModal.title')}
                </span>
            )}
            maxWidthClass="max-w-md"
        >
            <div className="space-y-4">
                <div className="rounded-md border bg-muted/50 p-3 text-sm">
                    <p className="mb-1 text-muted-foreground">{t('moveModal.moving')}</p>
                    <p className="truncate font-medium text-foreground">{item?.name || '-'}</p>
                </div>

                <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">{t('moveModal.destinationAccount')}</label>
                    <select
                        value={selectedAccount}
                        onChange={(event) => {
                            setSelectedAccount(event.target.value);
                            setCurrentFolderId('root');
                            setCurrentPath([]);
                        }}
                        className="w-full rounded-md border bg-background p-2 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                    >
                        {accounts.map((acc) => (
                            <option key={acc.id} value={acc.id}>
                                {acc.display_name} ({acc.email})
                            </option>
                        ))}
                    </select>
                </div>

                <div className="space-y-2">
                    <div className="flex items-center justify-between">
                        <label className="text-sm font-medium text-foreground">{t('moveModal.destinationFolder')}</label>
                        <button
                            onClick={navigateUp}
                            disabled={currentPath.length === 0}
                            className="text-xs text-primary hover:underline disabled:opacity-50"
                        >
                            {t('moveModal.goUp')}
                        </button>
                    </div>

                    <div className="overflow-hidden rounded-md border">
                        <div className="flex items-center gap-1 overflow-x-auto border-b bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
                            <span
                                onClick={() => {
                                    setCurrentPath([]);
                                    setCurrentFolderId('root');
                                }}
                                className="cursor-pointer hover:text-foreground"
                            >
                                {t('moveModal.root')}
                            </span>
                            {currentPath.map((part) => (
                                <Fragment key={part.id}>
                                    <ChevronRight className="h-3 w-3" />
                                    <span className="whitespace-nowrap">{part.name}</span>
                                </Fragment>
                            ))}
                        </div>

                        <div className="h-48 space-y-1 overflow-y-auto bg-background p-2">
                            {loading ? (
                                <div className="flex justify-center py-4">
                                    <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                                </div>
                            ) : folders.length === 0 ? (
                                <div className="py-8 text-center text-sm text-muted-foreground">
                                    {t('moveModal.emptyFolder')}
                                </div>
                            ) : (
                                folders.map((entry) => (
                                    <button
                                        key={entry.id}
                                        onClick={() => entry.item_type === 'folder' && navigateToFolder(entry)}
                                        disabled={entry.item_type !== 'folder'}
                                        className={`w-full rounded-md p-2 text-left transition-colors ${
                                            entry.item_type === 'folder'
                                                ? 'group flex cursor-pointer items-center gap-3 hover:bg-accent'
                                                : 'flex cursor-default items-center gap-3 opacity-50'
                                        }`}
                                    >
                                        {entry.item_type === 'folder' ? (
                                            <Folder className="h-4 w-4 text-primary/80 group-hover:text-primary" />
                                        ) : (
                                            <File className="h-4 w-4 text-muted-foreground" />
                                        )}
                                        <span className={entry.item_type === 'folder' ? 'truncate text-sm text-foreground' : 'truncate text-sm text-muted-foreground'}>
                                            {entry.name}
                                        </span>
                                        {entry.item_type !== 'folder' ? (
                                            <span className="ml-auto text-[10px] text-muted-foreground">{t('moveModal.file')}</span>
                                        ) : null}
                                    </button>
                                ))
                            )}
                        </div>
                    </div>
                </div>

                <div className="flex justify-end gap-3 border-t bg-muted/20 pt-4">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
                    >
                        {t('common.cancel')}
                    </button>
                    <button
                        onClick={handleMove}
                        disabled={submitting || !selectedAccount || !item}
                        className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        {submitting ? (
                            t('moveModal.processing')
                        ) : (
                            <>
                                <Check className="h-4 w-4" />
                                {t('moveModal.moveHere')}
                            </>
                        )}
                    </button>
                </div>
            </div>
        </Modal>
    );
}
