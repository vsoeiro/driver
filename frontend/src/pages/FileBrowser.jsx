import React, { useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useDrive } from '../hooks/useDrive';
import { useUpload } from '../hooks/useUpload';
import { driveService } from '../services/drive';
const { getDownloadUrl } = driveService;
import {
    Folder, File, MoreVertical, Download, Trash2,
    UploadCloud, FolderPlus, ArrowLeft, Loader2, Home, ArrowRightLeft
} from 'lucide-react';
import Modal from '../components/Modal';
import MoveModal from '../components/MoveModal';

export default function FileBrowser() {
    const { accountId, folderId } = useParams();
    const { files, breadcrumbs, loading, error, refresh, handleDelete, handleCreateFolder } = useDrive(accountId, folderId);
    const { upload, uploading, progress: uploadProgress } = useUpload(accountId, folderId, refresh);

    // Listen for job completion to auto-refresh
    React.useEffect(() => {
        const handleJobCompleted = (event) => {
            // We could filter by job type or account if needed, but for now refreshing on any job is safe
            console.log('Job completed, refreshing file list...');
            refresh();
        };

        window.addEventListener('job-completed', handleJobCompleted);
        return () => window.removeEventListener('job-completed', handleJobCompleted);
    }, [refresh]);

    // Modal State
    const [deleteModal, setDeleteModal] = useState({ isOpen: false, item: null });
    const [moveModal, setMoveModal] = useState({ isOpen: false, item: null });
    const [createFolderModal, setCreateFolderModal] = useState(false);
    const [newFolderName, setNewFolderName] = useState('');
    const [actionLoading, setActionLoading] = useState(false);

    // Helper to format date
    const formatDate = (dateString) => {
        if (!dateString) return '-';
        return new Date(dateString).toLocaleDateString('en-GB', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    };

    // Helper to format size
    const formatSize = (bytes) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const handleFileClick = async (file) => {
        if (file.item_type === 'file') {
            try {
                const url = await getDownloadUrl(accountId, file.id);
                window.open(url, '_blank');
            } catch (e) {
                alert('Download failed');
            }
        }
    };

    const confirmDelete = (item) => {
        setDeleteModal({ isOpen: true, item });
    };

    const executeDelete = async () => {
        if (!deleteModal.item) return;
        setActionLoading(true);
        try {
            await handleDelete(deleteModal.item.id);
            setDeleteModal({ isOpen: false, item: null });
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

    const fileInputRef = useRef(null);

    return (
        <div className="flex flex-col h-screen">
            {/* Header */}
            <header className="p-4 border-b flex items-center justify-between bg-background z-10 sticky top-0 h-16">
                <div className="flex items-center gap-4 overflow-hidden">
                    <nav className="flex items-center text-sm text-muted-foreground overflow-x-auto whitespace-nowrap scrollbar-hide">
                        <Link
                            to={`/drive/${accountId}`}
                            className="hover:text-foreground hover:underline px-1 font-medium"
                        >
                            Root
                        </Link>
                        {breadcrumbs.map((crumb) => (
                            <React.Fragment key={crumb.id}>
                                <span className="mx-1">/</span>
                                <Link
                                    to={`/drive/${accountId}/${crumb.id}`}
                                    className="hover:text-foreground hover:underline px-1 font-medium text-foreground"
                                >
                                    {crumb.name}
                                </Link>
                            </React.Fragment>
                        ))}
                    </nav>
                </div>

                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setCreateFolderModal(true)}
                        className="flex items-center gap-2 px-3 py-2 text-sm font-medium hover:bg-accent rounded-md"
                    >
                        <FolderPlus size={16} />
                        New Folder
                    </button>
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploading}
                        className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50"
                    >
                        {uploading ? <Loader2 className="animate-spin" size={16} /> : <UploadCloud size={16} />}
                        {uploading ? `Uploading ${uploadProgress}%` : 'Upload'}
                    </button>
                    <input
                        type="file"
                        ref={fileInputRef}
                        className="hidden"
                        onChange={(e) => upload(e.target.files[0])}
                    />
                </div>
            </header>

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
                        This folder is empty.
                    </div>
                ) : (
                    <div className="border rounded-lg overflow-hidden bg-card">
                        <div className="grid grid-cols-[40px_1fr_120px_180px_100px] gap-4 p-3 border-b bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider items-center">
                            <div className="text-center"></div>
                            <div>Name</div>
                            <div className="text-right">Size</div>
                            <div className="text-right">Modified</div>
                            <div className="text-center">Actions</div>
                        </div>

                        <div className="divide-y">
                            {[...files].sort((a, b) => { // Sort folders first
                                if (a.item_type === b.item_type) return a.name.localeCompare(b.name);
                                return a.item_type === 'folder' ? -1 : 1;
                            }).map(file => {
                                const isFolder = file.item_type === 'folder';
                                return (
                                    <div key={file.id} className="group grid grid-cols-[40px_1fr_120px_180px_100px] gap-4 p-3 items-center hover:bg-muted/30 transition-colors">
                                        <div className="text-muted-foreground flex justify-center">
                                            {isFolder ? <Folder className="text-blue-500 fill-blue-500/20" size={20} /> : <File className="text-gray-400" size={20} />}
                                        </div>

                                        <div className="min-w-0 truncate font-medium">
                                            {isFolder ? (
                                                <Link to={`/drive/${accountId}/${file.id}`} className="hover:underline cursor-pointer text-foreground">
                                                    {file.name}
                                                </Link>
                                            ) : (
                                                <span onClick={() => handleFileClick(file)} className="cursor-pointer hover:underline text-foreground">
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

                                        <div className="flex justify-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                            {!isFolder && (
                                                <button
                                                    onClick={() => handleFileClick(file)}
                                                    className="p-1.5 hover:bg-accent rounded-md text-muted-foreground hover:text-foreground"
                                                    title="Download"
                                                >
                                                    <Download size={16} />
                                                </button>
                                            )}
                                            <button
                                                onClick={() => confirmDelete(file)}
                                                className="p-1.5 hover:bg-destructive/10 hover:text-destructive rounded-md text-muted-foreground transition-colors"
                                                title="Delete"
                                            >
                                                <Trash2 size={16} />
                                            </button>
                                            <button
                                                onClick={() => setMoveModal({ isOpen: true, item: file })}
                                                className="p-1.5 hover:bg-accent rounded-md text-muted-foreground hover:text-foreground"
                                                title="Move"
                                            >
                                                <ArrowRightLeft size={16} />
                                            </button>
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
                onClose={() => setDeleteModal({ ...deleteModal, isOpen: false })}
                title="Confirm Deletion"
            >
                <div className="space-y-4">
                    <p>Are you sure you want to delete <strong>{deleteModal.item?.name}</strong>?</p>
                    <div className="flex justify-end gap-2">
                        <button
                            onClick={() => setDeleteModal({ ...deleteModal, isOpen: false })}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={executeDelete}
                            disabled={actionLoading}
                            className="px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50 flex items-center gap-2"
                        >
                            {actionLoading && <Loader2 className="animate-spin" size={14} />}
                            Delete
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
                        <button
                            type="button"
                            onClick={() => setCreateFolderModal(false)}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={actionLoading || !newFolderName.trim()}
                            className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                        >
                            {actionLoading && <Loader2 className="animate-spin" size={14} />}
                            Create
                        </button>
                    </div>
                </form>
            </Modal>
            <MoveModal
                isOpen={moveModal.isOpen}
                onClose={() => setMoveModal({ isOpen: false, item: null })}
                item={moveModal.item}
                sourceAccountId={accountId}
                onSuccess={() => {
                    setMoveModal({ isOpen: false, item: null });
                    refresh();
                }}
            />
        </div>
    );
}
