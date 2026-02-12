import React, { useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useDrive } from '../hooks/useDrive';
import { useUpload } from '../hooks/useUpload';
import { getDownloadUrl } from '../services/api';
import {
    Folder, File, MoreVertical, Download, Trash2,
    UploadCloud, FolderPlus, ArrowLeft, Loader2, Home
} from 'lucide-react';

export default function FileBrowser() {
    const { accountId, folderId } = useParams();
    const { files, breadcrumbs, loading, error, refresh, handleDelete, handleCreateFolder } = useDrive(accountId, folderId);
    const { upload, uploading, progress: uploadProgress } = useUpload(accountId, folderId, refresh);

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
                        onClick={() => {
                            const name = prompt("Folder Name:");
                            if (name) handleCreateFolder(name);
                        }}
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
                                                onClick={() => handleDelete(file.id)}
                                                className="p-1.5 hover:bg-destructive/10 hover:text-destructive rounded-md text-muted-foreground transition-colors"
                                                title="Delete"
                                            >
                                                <Trash2 size={16} />
                                            </button>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}
