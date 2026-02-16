import { Fragment, useEffect, useState } from 'react';
import { Check, ChevronRight, Folder, FolderInput, X } from 'lucide-react';
import { accountsService } from '../services/accounts';
import { driveService } from '../services/drive';

export default function FolderTargetPickerModal({
    isOpen,
    initialValue,
    onClose,
    onConfirm,
}) {
    const [accounts, setAccounts] = useState([]);
    const [selectedAccount, setSelectedAccount] = useState('');
    const [currentFolderId, setCurrentFolderId] = useState('root');
    const [currentPath, setCurrentPath] = useState([]);
    const [folders, setFolders] = useState([]);
    const [loadingAccounts, setLoadingAccounts] = useState(false);
    const [loadingFolders, setLoadingFolders] = useState(false);

    useEffect(() => {
        if (!isOpen) return;
        const load = async () => {
            setLoadingAccounts(true);
            try {
                const data = await accountsService.getAccounts();
                setAccounts(data);
                const initialAccount = initialValue?.account_id || data[0]?.id || '';
                setSelectedAccount(initialAccount);
                setCurrentFolderId(initialValue?.folder_id || 'root');
                setCurrentPath([]);
            } finally {
                setLoadingAccounts(false);
            }
        };
        load();
    }, [isOpen, initialValue]);

    useEffect(() => {
        if (!isOpen || !selectedAccount) return;
        const loadFolders = async () => {
            setLoadingFolders(true);
            try {
                const data = currentFolderId === 'root'
                    ? await driveService.getFiles(selectedAccount)
                    : await driveService.getFolderFiles(selectedAccount, currentFolderId);
                setFolders((data.items || []).filter((item) => item.item_type === 'folder'));
            } finally {
                setLoadingFolders(false);
            }
        };
        loadFolders();
    }, [isOpen, selectedAccount, currentFolderId]);

    if (!isOpen) return null;

    const handleNavigateFolder = (folder) => {
        setCurrentPath((prev) => [...prev, { id: folder.id, name: folder.name }]);
        setCurrentFolderId(folder.id);
    };

    const handleGoUp = () => {
        if (currentPath.length === 0) return;
        const nextPath = currentPath.slice(0, -1);
        setCurrentPath(nextPath);
        setCurrentFolderId(nextPath[nextPath.length - 1]?.id || 'root');
    };

    const handleConfirm = () => {
        const folderPath = currentPath.length === 0
            ? 'Root'
            : `Root/${currentPath.map((p) => p.name).join('/')}`;
        onConfirm({
            account_id: selectedAccount || '',
            folder_id: currentFolderId || 'root',
            folder_path: folderPath,
        });
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
            <div className="w-full max-w-md bg-card border text-card-foreground rounded-lg shadow-lg overflow-hidden">
                <div className="flex items-center justify-between p-4 border-b">
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                        <FolderInput className="w-5 h-5 text-primary" />
                        Select Cover Destination
                    </h3>
                    <button onClick={onClose} className="p-1 hover:bg-accent rounded-md transition-colors">
                        <X className="w-5 h-5 text-muted-foreground" />
                    </button>
                </div>

                <div className="p-4 space-y-4">
                    <div className="space-y-2">
                        <label className="text-sm font-medium text-foreground">Account</label>
                        <select
                            value={selectedAccount}
                            onChange={(e) => {
                                setSelectedAccount(e.target.value);
                                setCurrentFolderId('root');
                                setCurrentPath([]);
                            }}
                            className="w-full p-2 bg-background border rounded-md text-foreground"
                            disabled={loadingAccounts || accounts.length === 0}
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
                            <label className="text-sm font-medium text-foreground">Folder</label>
                            <button
                                onClick={handleGoUp}
                                disabled={currentPath.length === 0}
                                className="text-xs text-primary hover:underline disabled:opacity-50"
                            >
                                Go Up
                            </button>
                        </div>
                        <div className="border rounded-md overflow-hidden">
                            <div className="bg-muted/50 px-3 py-2 text-xs text-muted-foreground border-b flex items-center gap-1 overflow-x-auto">
                                <span
                                    onClick={() => { setCurrentPath([]); setCurrentFolderId('root'); }}
                                    className="cursor-pointer hover:text-foreground"
                                >
                                    Root
                                </span>
                                {currentPath.map((part) => (
                                    <Fragment key={part.id}>
                                        <ChevronRight className="w-3 h-3" />
                                        <span className="whitespace-nowrap">{part.name}</span>
                                    </Fragment>
                                ))}
                            </div>
                            <div className="h-48 overflow-y-auto bg-background p-2 space-y-1">
                                {loadingFolders ? (
                                    <div className="flex justify-center py-4">
                                        <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                                    </div>
                                ) : folders.length === 0 ? (
                                    <div className="text-center py-8 text-muted-foreground text-sm">No folders</div>
                                ) : (
                                    folders.map((item) => (
                                        <button
                                            key={item.id}
                                            onClick={() => handleNavigateFolder(item)}
                                            className="w-full flex items-center gap-3 p-2 rounded-md text-left transition-colors hover:bg-accent"
                                        >
                                            <Folder className="w-4 h-4 text-primary/80" />
                                            <span className="text-sm truncate text-foreground">{item.name}</span>
                                        </button>
                                    ))
                                )}
                            </div>
                        </div>
                    </div>
                </div>

                <div className="p-4 border-t flex justify-end gap-3 bg-muted/20">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleConfirm}
                        disabled={!selectedAccount}
                        className="px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90 text-sm font-medium rounded-md transition-colors flex items-center gap-2 disabled:opacity-50"
                    >
                        <Check className="w-4 h-4" />
                        Use This Folder
                    </button>
                </div>
            </div>
        </div>
    );
}
