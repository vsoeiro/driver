import React, { useRef, useState, useMemo, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useDrive } from '../hooks/useDrive';
import { useUpload } from '../hooks/useUpload';
import { driveService } from '../services/drive';
import { metadataService } from '../services/metadata';
const { getDownloadUrl } = driveService;
const { batchDeleteMetadata } = metadataService;
import {
    Folder, File, Download, Trash2,
    UploadCloud, FolderPlus, Loader2, ArrowRightLeft, Database, XCircle, CheckSquare, Square, Search, X, ChevronDown
} from 'lucide-react';
import Modal from '../components/Modal';
import MoveModal from '../components/MoveModal';
import MetadataModal from '../components/MetadataModal';

export default function FileBrowser() {
    const { accountId, folderId } = useParams();
    const { files, breadcrumbs, loading, error, refresh, handleBatchDelete, handleCreateFolder, searchQuery, setSearchQuery } = useDrive(accountId, folderId);
    const { upload, uploading, progress: uploadProgress } = useUpload(accountId, folderId, refresh);

    // Listen for job completion to auto-refresh
    React.useEffect(() => {
        const handleJobCompleted = () => {
            console.log('Job completed, refreshing file list...');
            refresh();
        };

        window.addEventListener('job-completed', handleJobCompleted);
        return () => window.removeEventListener('job-completed', handleJobCompleted);
    }, [refresh]);

    // Local search state to debounce/control API calls
    const [searchTerm, setSearchTerm] = useState('');
    useEffect(() => {
        setSearchTerm(searchQuery);
    }, [searchQuery]);

    // State
    const [selectedItems, setSelectedItems] = useState(new Set());
    const [lastSelectedIndex, setLastSelectedIndex] = useState(null);

    // Modal State
    const [deleteModal, setDeleteModal] = useState({ isOpen: false });
    const [moveModal, setMoveModal] = useState({ isOpen: false });
    const [metadataModalOpen, setMetadataModalOpen] = useState(false);
    const [removeMetadataModal, setRemoveMetadataModal] = useState(false);
    const [createFolderModal, setCreateFolderModal] = useState(false);
    const [metadataMenuOpen, setMetadataMenuOpen] = useState(false);
    const metadataMenuRef = useRef(null);
    const [newFolderName, setNewFolderName] = useState('');
    const [actionLoading, setActionLoading] = useState(false);

    // Reset selection on folder change
    React.useEffect(() => {
        setSelectedItems(new Set());
        setLastSelectedIndex(null);
    }, [folderId, accountId]);

    // Helper to format date
    const formatDate = (dateString) => {
        if (!dateString) return '-';
        return new Date(dateString).toLocaleDateString('en-GB', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    };

    // Click outside handler for metadata menu
    useEffect(() => {
        function handleClickOutside(event) {
            if (metadataMenuRef.current && !metadataMenuRef.current.contains(event.target)) {
                setMetadataMenuOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => {
            document.removeEventListener("mousedown", handleClickOutside);
        };
    }, [metadataMenuRef]);

    // Helper to format size
    const formatSize = (bytes) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    // Sorted items
    const sortedFiles = useMemo(() => {
        return [...files].sort((a, b) => {
            if (a.item_type === b.item_type) return a.name.localeCompare(b.name);
            return a.item_type === 'folder' ? -1 : 1;
        });
    }, [files]);

    // Selection Logic
    const toggleSelection = (id, index, multiSelect, rangeSelect) => {
        const newSelection = new Set(multiSelect ? selectedItems : []);

        if (rangeSelect && lastSelectedIndex !== null) {
            const start = Math.min(lastSelectedIndex, index);
            const end = Math.max(lastSelectedIndex, index);
            for (let i = start; i <= end; i++) {
                newSelection.add(sortedFiles[i].id);
            }
        } else {
            if (newSelection.has(id)) {
                newSelection.delete(id);
            } else {
                newSelection.add(id);
            }
        }

        setSelectedItems(newSelection);
        setLastSelectedIndex(index);
    };

    const toggleSelectAll = () => {
        if (selectedItems.size === files.length) {
            setSelectedItems(new Set());
        } else {
            setSelectedItems(new Set(files.map(f => f.id)));
        }
    };

    // Actions
    const handleDownload = async () => {
        const selectedFiles = sortedFiles.filter(f => selectedItems.has(f.id) && f.item_type === 'file');
        for (const file of selectedFiles) {
            try {
                const url = await getDownloadUrl(accountId, file.id);
                window.open(url, '_blank');
            } catch (e) {
                console.error(`Failed to download ${file.name}`, e);
            }
        }
    };

    const executeDelete = async () => {
        setActionLoading(true);
        try {
            await handleBatchDelete(Array.from(selectedItems));
            setSelectedItems(new Set());
            setDeleteModal({ isOpen: false });
        } catch (e) {
            alert(e.message);
        } finally {
            setActionLoading(false);
        }
    };

    const executeRemoveMetadata = async () => {
        setActionLoading(true);
        try {
            await batchDeleteMetadata(accountId, Array.from(selectedItems));

            setRemoveMetadataModal(false);
            refresh();
        } catch (e) {
            alert(e.message);
        } finally {
            setActionLoading(false);
        }
    };

    const executeCreateFolder = async (e) => {
        e.preventDefault();
        if (!newFolderName.trim()) return;
        setActionLoading(true);
        try {
            await handleCreateFolder(newFolderName);
            setCreateFolderModal(false);
            setNewFolderName('');
        } catch (e) {
            alert(e.message);
        } finally {
            setActionLoading(false);
        }
    };

    const handleSearchSubmit = (e) => {
        if (e.key === 'Enter') {
            setSearchQuery(searchTerm);
        }
    }

    const clearSearch = () => {
        setSearchTerm('');
        setSearchQuery('');
    };

    const fileInputRef = useRef(null);

    // Get single selected item for singular actions
    const singleSelectedItem = selectedItems.size === 1
        ? files.find(f => f.id === Array.from(selectedItems)[0])
        : null;

    return (
        <div className="flex flex-col h-screen">
            {/* Header */}
            <header className="p-4 border-b flex items-center justify-between bg-background z-10 sticky top-0 h-16">
                <div className="flex items-center gap-4 overflow-hidden">
                    <nav className="flex items-center text-sm text-muted-foreground overflow-x-auto whitespace-nowrap scrollbar-hide">
                        <Link to={`/drive/${accountId}`} className="hover:text-foreground hover:underline px-1 font-medium">
                            Root
                        </Link>
                        {breadcrumbs.map((crumb) => (
                            <React.Fragment key={crumb.id}>
                                <span className="mx-1">/</span>
                                <Link to={`/drive/${accountId}/${crumb.id}`} className="hover:text-foreground hover:underline px-1 font-medium text-foreground">
                                    {crumb.name}
                                </Link>
                            </React.Fragment>
                        ))}
                    </nav>
                </div>

                <div className="flex items-center gap-2">
                    <button onClick={() => setCreateFolderModal(true)} className="flex items-center gap-2 px-3 py-2 text-sm font-medium hover:bg-accent rounded-md">
                        <FolderPlus size={16} />
                        New Folder
                    </button>
                    <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50">
                        {uploading ? <Loader2 className="animate-spin" size={16} /> : <UploadCloud size={16} />}
                        {uploading ? `Uploading ${uploadProgress}%` : 'Upload'}
                    </button>
                    <input type="file" ref={fileInputRef} className="hidden" onChange={(e) => upload(e.target.files[0])} />
                </div>
            </header>

            {/* Toolbar (Always visible) */}
            <div className="bg-muted/50 border-b px-4 py-2 flex items-center justify-between gap-2 text-sm h-14">
                <div className="flex items-center w-full max-w-sm relative">
                    <Search className="absolute left-2 text-muted-foreground" size={16} />
                    <input
                        type="text"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        onKeyDown={handleSearchSubmit}
                        placeholder="Search files..."
                        className="pl-8 pr-8 py-1.5 text-sm w-full rounded-md border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                    {searchTerm && (
                        <button onClick={clearSearch} className="absolute right-2 text-muted-foreground hover:text-foreground">
                            <X size={14} />
                        </button>
                    )}
                </div>

                <div className="flex items-center gap-2">
                    <div className="h-4 w-px bg-border mx-2" />
                    <span className="font-medium mr-2 whitespace-nowrap w-24 text-right tabular-nums">{selectedItems.size} selected</span>

                    {/* Actions */}
                    <button
                        onClick={handleDownload}
                        disabled={selectedItems.size === 0}
                        className="p-2 hover:bg-background rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Download"
                    >
                        <Download size={16} /> <span className="hidden sm:inline">Download</span>
                    </button>

                    <button
                        onClick={() => setMoveModal({ isOpen: true })}
                        disabled={selectedItems.size === 0}
                        className="p-2 hover:bg-background rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Move"
                    >
                        <ArrowRightLeft size={16} /> <span className="hidden sm:inline">Move</span>
                    </button>

                    <div
                        className={`relative ${selectedItems.size === 0 ? 'pointer-events-none opacity-50' : ''}`}
                        ref={metadataMenuRef}
                        onMouseEnter={() => selectedItems.size > 0 && setMetadataMenuOpen(true)}
                        onMouseLeave={() => setMetadataMenuOpen(false)}
                    >
                        <button
                            onClick={() => setMetadataMenuOpen(!metadataMenuOpen)}
                            disabled={selectedItems.size === 0}
                            className="p-2 hover:bg-background rounded-md flex items-center gap-2 disabled:cursor-not-allowed"
                            title="Metadata Actions"
                        >
                            <Database size={16} />
                            <span className="hidden sm:inline">Metadata</span>
                            <ChevronDown size={14} className={`transition-transform ${metadataMenuOpen ? 'rotate-180' : ''}`} />
                        </button>

                        {metadataMenuOpen && (
                            <div className="absolute top-full left-0 w-48 pt-1 z-50">
                                <div className="bg-popover border rounded-md shadow-md py-1">
                                    <button
                                        onClick={() => { setMetadataModalOpen(true); setMetadataMenuOpen(false); }}
                                        disabled={selectedItems.size !== 1}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                    >
                                        <Database size={14} /> Edit Metadata
                                    </button>
                                    <button
                                        onClick={() => { setRemoveMetadataModal(true); setMetadataMenuOpen(false); }}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 text-destructive hover:text-destructive"
                                    >
                                        <XCircle size={14} /> Remove Metadata
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>

                    <div className="h-4 w-px bg-border mx-1" />

                    <button
                        onClick={() => setDeleteModal({ isOpen: true })}
                        disabled={selectedItems.size === 0}
                        className="p-2 hover:bg-destructive/10 text-destructive rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Delete"
                    >
                        <Trash2 size={16} /> <span className="hidden sm:inline">Delete</span>
                    </button>
                </div>
            </div>

            {/* Content */}
            <main className="flex-1 overflow-auto p-4">
                {loading ? (
                    <div className="flex justify-center p-12">
                        <Loader2 className="animate-spin text-primary" size={32} />
                    </div>
                ) : error ? (
                    <div className="text-red-500 p-4 border border-red-200 rounded-md bg-red-50">
                        Error: {error}
                    </div>
                ) : files.length === 0 ? (
                    <div className="text-center p-12 text-muted-foreground">
                        {searchQuery ? `No results for "${searchQuery}"` : 'This folder is empty.'}
                    </div>
                ) : (
                    <div className="border rounded-lg overflow-hidden bg-card select-none">
                        <div className="grid grid-cols-[40px_40px_1fr_120px_180px] gap-4 p-3 border-b bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider items-center">
                            <div className="flex justify-center items-center">
                                <button onClick={toggleSelectAll} className="hover:text-foreground">
                                    {selectedItems.size === files.length && files.length > 0 ? <CheckSquare size={16} /> : <Square size={16} />}
                                </button>
                            </div>
                            <div className="text-center"></div>
                            <div>Name</div>
                            <div className="text-right">Size</div>
                            <div className="text-right">Modified</div>
                        </div>

                        <div className="divide-y">
                            {sortedFiles.map((file, index) => {
                                const isFolder = file.item_type === 'folder';
                                const isSelected = selectedItems.has(file.id);
                                return (
                                    <div
                                        key={file.id}
                                        className={`group grid grid-cols-[40px_40px_1fr_120px_180px] gap-4 p-3 items-center hover:bg-muted/30 transition-colors ${isSelected ? 'bg-muted/40' : ''}`}
                                        onClick={(e) => toggleSelection(file.id, index, !e.altKey, e.shiftKey)}
                                    >
                                        <div className="flex justify-center items-center">
                                            <div className={`cursor-pointer ${isSelected ? 'text-primary' : 'text-muted-foreground/50'}`}>
                                                {isSelected ? <CheckSquare size={16} /> : <Square size={16} />}
                                            </div>
                                        </div>

                                        <div className="text-muted-foreground flex justify-center">
                                            {isFolder ? <Folder className="text-blue-500 fill-blue-500/20" size={20} /> : <File className="text-gray-400" size={20} />}
                                        </div>

                                        <div className="min-w-0 truncate font-medium">
                                            {isFolder ? (
                                                <Link
                                                    to={`/drive/${accountId}/${file.id}`}
                                                    className="hover:underline cursor-pointer text-foreground"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    {file.name}
                                                </Link>
                                            ) : (
                                                <span className="text-foreground">
                                                    {file.name}
                                                </span>
                                            )}
                                        </div>

                                        <div className="text-right text-sm text-muted-foreground tabular-nums">
                                            {formatSize(file.size)}
                                        </div>

                                        <div className="text-right text-sm text-muted-foreground tabular-nums">
                                            {formatDate(file.modified_at)}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
            </main>

            {/* Modals */}
            <Modal
                isOpen={deleteModal.isOpen}
                onClose={() => setDeleteModal({ isOpen: false })}
                title={`Delete ${selectedItems.size} item(s)?`}
            >
                <div className="space-y-4">
                    <p>Are you sure you want to delete the selected items? This action cannot be undone.</p>
                    <div className="flex justify-end gap-2">
                        <button onClick={() => setDeleteModal({ isOpen: false })} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">
                            Cancel
                        </button>
                        <button onClick={executeDelete} disabled={actionLoading} className="px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50 flex items-center gap-2">
                            {actionLoading && <Loader2 className="animate-spin" size={14} />}
                            Delete
                        </button>
                    </div>
                </div>
            </Modal>

            <Modal
                isOpen={removeMetadataModal}
                onClose={() => setRemoveMetadataModal(false)}
                title={`Remove Metadata from ${selectedItems.size} item(s)?`}
            >
                <div className="space-y-4">
                    <p>Are you sure you want to remove metadata from the selected items? The file content will remain unchanged.</p>
                    <div className="flex justify-end gap-2">
                        <button onClick={() => setRemoveMetadataModal(false)} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">
                            Cancel
                        </button>
                        <button onClick={executeRemoveMetadata} disabled={actionLoading} className="px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50 flex items-center gap-2">
                            {actionLoading && <Loader2 className="animate-spin" size={14} />}
                            Remove
                        </button>
                    </div>
                </div>
            </Modal>

            <Modal
                isOpen={createFolderModal}
                onClose={() => setCreateFolderModal(false)}
                title="Create New Folder"
            >
                <form onSubmit={executeCreateFolder} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">Folder Name</label>
                        <input
                            type="text"
                            className="w-full border rounded-md p-2 bg-background"
                            value={newFolderName}
                            onChange={e => setNewFolderName(e.target.value)}
                            placeholder="My Folder"
                            autoFocus
                        />
                    </div>
                    <div className="flex justify-end gap-2">
                        <button type="button" onClick={() => setCreateFolderModal(false)} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">
                            Cancel
                        </button>
                        <button type="submit" disabled={actionLoading || !newFolderName.trim()} className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2">
                            {actionLoading && <Loader2 className="animate-spin" size={14} />}
                            Create
                        </button>
                    </div>
                </form>
            </Modal>

            <MetadataModal
                isOpen={metadataModalOpen}
                onClose={() => setMetadataModalOpen(false)}
                item={singleSelectedItem}
                accountId={accountId}
                onSuccess={() => {
                    // Optional: refresh metadata indicator if we had one
                }}
            />

            <MoveModal
                isOpen={moveModal.isOpen}
                onClose={() => setMoveModal({ isOpen: false })}
                item={singleSelectedItem} // Pass single item if only one, or modal handles multiple? Modal currently handles one.
                // TODO: Update MoveModal to handle multiple items if needed, for now might need loop or disable multi-move
                sourceAccountId={accountId}
                onSuccess={() => {
                    setMoveModal({ isOpen: false });
                    setSelectedItems(new Set());
                    refresh();
                }}
            />
        </div>
    );
}
