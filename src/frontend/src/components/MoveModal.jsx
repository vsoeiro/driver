import { useState, useEffect, useCallback, Fragment } from 'react';
import { X, FolderInput, Check, ChevronRight, Folder } from 'lucide-react';
import { getAccounts } from '../services/accounts';
import { getFiles, getFolderFiles } from '../services/drive';
import { createMoveJob } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';

export default function MoveModal({ isOpen, onClose, item, sourceAccountId, onSuccess }) {
    const [accounts, setAccounts] = useState([]);
    const [selectedAccount, setSelectedAccount] = useState('');
    const [currentPath, setCurrentPath] = useState([]); // [{id: 'root', name: 'Root'}]
    const [currentFolderId, setCurrentFolderId] = useState('root');
    const [folders, setFolders] = useState([]);
    const [loading, setLoading] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    const { showToast } = useToast();

    const loadAccounts = useCallback(async () => {
        try {
            const data = await getAccounts();
            setAccounts(data);
            // Default to current account if available, or first account
            setSelectedAccount((current) => {
                if (current || data.length === 0) return current;
                return sourceAccountId || data[0].id;
            });
        } catch (error) {
            console.error('Failed to load accounts:', error);
            showToast('Failed to load accounts', 'error');
        }
    }, [sourceAccountId, showToast]);

    const loadFolders = useCallback(async (accountId, folderId) => {
        setLoading(true);
        console.log(`Loading folders for account ${accountId}, folder ${folderId}`);
        try {
            const data = folderId === 'root'
                ? await getFiles(accountId)
                : await getFolderFiles(accountId, folderId);

            console.log('Folders loaded:', data);
            // Show all items, but disable files in UI
            setFolders(data.items);
        } catch (error) {
            console.error('Failed to load folders:', error);
            showToast(`Error loading folder: ${error.message}`, 'error');
            setFolders([]);
        } finally {
            setLoading(false);
        }
    }, [showToast]);

    useEffect(() => {
        if (isOpen) {
            loadAccounts();
        }
    }, [isOpen, loadAccounts]);

    useEffect(() => {
        if (selectedAccount) {
            loadFolders(selectedAccount, currentFolderId);
        }
    }, [selectedAccount, currentFolderId, loadFolders]);

    const handleMove = async () => {
        if (!selectedAccount || !item) return;

        setSubmitting(true);
        try {
            await createMoveJob(
                sourceAccountId,
                item.id,
                selectedAccount,
                currentFolderId
            );
            showToast(`Move job started for ${item.name}`, 'success');
            onSuccess();
            onClose();
        } catch (error) {
            console.error('Failed to create move job:', error);
            showToast(`Failed to start move job: ${error.message}`, 'error');
        } finally {
            setSubmitting(false);
        }
    };

    const navigateToFolder = (folder) => {
        console.log('Navigating to folder:', folder);
        if (!folder.id) {
            showToast('Folder ID is missing', 'error');
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

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
            <div className="w-full max-w-md bg-card border text-card-foreground rounded-lg shadow-lg overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b">
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                        <FolderInput className="w-5 h-5 text-primary" />
                        Move Item
                    </h3>
                    <button onClick={onClose} className="p-1 hover:bg-accent rounded-md transition-colors">
                        <X className="w-5 h-5 text-muted-foreground" />
                    </button>
                </div>

                {/* Body */}
                <div className="p-4 space-y-4">
                    <div className="p-3 bg-muted/50 rounded-md border text-sm">
                        <p className="text-muted-foreground mb-1">Moving:</p>
                        <p className="font-medium text-foreground truncate">{item?.name}</p>
                    </div>

                    <div className="space-y-2">
                        <label className="text-sm font-medium text-foreground">Destination Account</label>
                        <select
                            value={selectedAccount}
                            onChange={(e) => {
                                setSelectedAccount(e.target.value);
                                setCurrentFolderId('root');
                                setCurrentPath([]);
                            }}
                            className="w-full p-2 bg-background border rounded-md text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                        >
                            {accounts.map(acc => (
                                <option key={acc.id} value={acc.id}>
                                    {acc.display_name} ({acc.email})
                                </option>
                            ))}
                        </select>
                    </div>

                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <label className="text-sm font-medium text-foreground">Destination Folder</label>
                            <button
                                onClick={navigateUp}
                                disabled={currentPath.length === 0}
                                className="text-xs text-primary hover:underline disabled:opacity-50"
                            >
                                Go Up
                            </button>
                        </div>

                        <div className="border rounded-md overflow-hidden">
                            <div className="bg-muted/50 px-3 py-2 text-xs text-muted-foreground border-b flex items-center gap-1 overflow-x-auto">
                                <span onClick={() => { setCurrentPath([]); setCurrentFolderId('root'); }} className="cursor-pointer hover:text-foreground">Root</span>
                                {currentPath.map((p) => (
                                    <Fragment key={p.id}>
                                        <ChevronRight className="w-3 h-3" />
                                        <span className="whitespace-nowrap">{p.name}</span>
                                    </Fragment>
                                ))}
                            </div>

                            <div className="h-48 overflow-y-auto bg-background p-2 space-y-1">
                                {loading ? (
                                    <div className="flex justify-center py-4">
                                        <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                                    </div>
                                ) : folders.length === 0 ? (
                                    <div className="text-center py-8 text-muted-foreground text-sm">
                                        Empty folder
                                    </div>
                                ) : (
                                    folders.map(item => (
                                        <button
                                            key={item.id}
                                            onClick={() => item.item_type === 'folder' && navigateToFolder(item)}
                                            disabled={item.item_type !== 'folder'}
                                            className={`w-full flex items-center gap-3 p-2 rounded-md text-left transition-colors ${item.item_type === 'folder'
                                                ? 'hover:bg-accent cursor-pointer group'
                                                : 'opacity-50 cursor-default'
                                                }`}
                                        >
                                            {item.item_type === 'folder' ? (
                                                <Folder className="w-4 h-4 text-primary/80 group-hover:text-primary" />
                                            ) : (
                                                <div className="w-4 h-4 bg-muted rounded flex items-center justify-center text-[10px] text-muted-foreground">
                                                    DOC
                                                </div>
                                            )}
                                            <span className={`text-sm truncate ${item.item_type === 'folder' ? 'text-foreground' : 'text-muted-foreground'
                                                }`}>
                                                {item.name}
                                            </span>
                                        </button>
                                    ))
                                )}
                            </div>
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="p-4 border-t flex justify-end gap-3 bg-muted/20">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleMove}
                        disabled={submitting || !selectedAccount}
                        className="px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90 text-sm font-medium rounded-md transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {submitting ? (
                            <>Processing...</>
                        ) : (
                            <>
                                <Check className="w-4 h-4" />
                                Move Here
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
}
