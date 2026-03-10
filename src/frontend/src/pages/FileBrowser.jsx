import React, { Suspense, lazy, useRef, useState, useMemo, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useDrive } from '../hooks/useDrive';
import { useUpload } from '../hooks/useUpload';
import { driveService } from '../services/drive';
import { batchDeleteMetadata } from '../services/metadata';
import { jobsService } from '../services/jobs';
import {
    Folder, File, Download, Trash2,
    UploadCloud, FolderPlus, Loader2, ArrowRightLeft, Database, XCircle, CheckSquare, Square, Search, X, ChevronDown, BookOpen, RefreshCw, ChevronLeft, ChevronRight, ArrowUp, ArrowDown, GripVertical, Image as ImageIcon
} from 'lucide-react';
import Modal from '../components/Modal';
import { useToast } from '../contexts/ToastContext';
import { useMetadataLibrariesQuery } from '../hooks/useAppQueries';
import { isPreviewableFileName } from '../utils/imagePreview';
import { formatDateTime } from '../utils/dateTime';

const { getDownloadUrl } = driveService;
const MetadataModal = lazy(() => import('../components/MetadataModal'));
const BatchMetadataModal = lazy(() => import('../components/BatchMetadataModal'));
const MoveModal = lazy(() => import('../components/MoveModal'));
const ImagePreviewModal = lazy(() => import('../components/ImagePreviewModal'));
let metadataModulePromise;
let batchMetadataModulePromise;
let moveModalModulePromise;
let imagePreviewModulePromise;
const COMIC_MAPPABLE_EXTS = new Set(['cbz', 'zip', 'cbw', 'pdf', 'epub', 'cbr', 'rar', 'cb7', '7z', 'cbt', 'tar']);
const BOOK_MAPPABLE_EXTS = new Set(['pdf', 'epub']);
const IMAGE_ANALYZABLE_EXTS = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tiff', 'tif', 'heic', 'avif']);
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200];
const FILE_BROWSER_COLUMNS = [
    { id: 'name', width: 320, minWidth: 180, align: 'left' },
    { id: 'size', width: 120, minWidth: 90, align: 'right' },
    { id: 'modified', width: 180, minWidth: 140, align: 'right' },
];
const FILE_BROWSER_COLUMN_WIDTHS_STORAGE_KEY = 'driver-file-browser-column-widths-v1';

function preloadMetadataModal() {
    metadataModulePromise ||= import('../components/MetadataModal');
}

function preloadBatchMetadataModal() {
    batchMetadataModulePromise ||= import('../components/BatchMetadataModal');
}

function preloadMoveModal() {
    moveModalModulePromise ||= import('../components/MoveModal');
}

function preloadImagePreviewModal() {
    imagePreviewModulePromise ||= import('../components/ImagePreviewModal');
}

export default function FileBrowser() {
    const { t, i18n } = useTranslation();
    const { showToast } = useToast();
    const { accountId, folderId } = useParams();
    const [pageSize, setPageSize] = useState(50);
    const {
        files,
        breadcrumbs,
        loading,
        error,
        refresh,
        handleBatchDelete,
        handleCreateFolder,
        searchQuery,
        setSearchQuery,
        page,
        canNextPage,
        canPrevPage,
        goToNextPage,
        goToPrevPage,
        resetPagination,
    } = useDrive(accountId, folderId, { pageSize });
    const { upload, uploading, progress: uploadProgress } = useUpload(
        accountId,
        folderId,
        refresh,
        (failed) => showToast(t('allFiles.uploadFailedCount', { count: failed }), 'error'),
    );

    // Listen for job completion to auto-refresh
    React.useEffect(() => {
        const handleJobCompleted = () => {
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
    const [batchMetadataModalOpen, setBatchMetadataModalOpen] = useState(false);
    const [removeMetadataModal, setRemoveMetadataModal] = useState(false);
    const [createFolderModal, setCreateFolderModal] = useState(false);
    const [metadataMenuOpen, setMetadataMenuOpen] = useState(false);
    const metadataMenuRef = useRef(null);
    const navDragCounterRef = useRef(0);
    const [newFolderName, setNewFolderName] = useState('');
    const [actionLoading, setActionLoading] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const [sortBy, setSortBy] = useState('name');
    const [sortOrder, setSortOrder] = useState('asc');
    const [isNavDropActive, setIsNavDropActive] = useState(false);
    const [imagePreviewItem, setImagePreviewItem] = useState(null);
    const resizeStateRef = useRef(null);
    const [columnWidths, setColumnWidths] = useState(() => {
        const defaults = FILE_BROWSER_COLUMNS.reduce((acc, column) => ({ ...acc, [column.id]: column.width }), {});
        if (typeof window === 'undefined') return defaults;
        try {
            const raw = window.localStorage.getItem(FILE_BROWSER_COLUMN_WIDTHS_STORAGE_KEY);
            if (!raw) return defaults;
            const parsed = JSON.parse(raw);
            return FILE_BROWSER_COLUMNS.reduce((acc, column) => {
                const candidate = Number(parsed?.[column.id]);
                acc[column.id] = Number.isFinite(candidate)
                    ? Math.max(column.minWidth, candidate)
                    : column.width;
                return acc;
            }, {});
        } catch {
            return defaults;
        }
    });
    const { data: metadataLibraries = [] } = useMetadataLibrariesQuery();
    const isComicsLibraryActive = Boolean(metadataLibraries.find((library) => library.key === 'comics_core')?.is_active);
    const isImagesLibraryActive = Boolean(metadataLibraries.find((library) => library.key === 'images_core')?.is_active);
    const isBooksLibraryActive = Boolean(metadataLibraries.find((library) => library.key === 'books_core')?.is_active);

    // Reset selection on folder change
    React.useEffect(() => {
        setSelectedItems(new Set());
        setLastSelectedIndex(null);
    }, [folderId, accountId]);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        window.localStorage.setItem(FILE_BROWSER_COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify(columnWidths));
    }, [columnWidths]);

    // Helper to format date
    const formatDate = (dateString) => {
        return formatDateTime(dateString, i18n.language);
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
        const direction = sortOrder === 'asc' ? 1 : -1;
        return [...files].sort((a, b) => {
            if (a.item_type !== b.item_type) return a.item_type === 'folder' ? -1 : 1;

            if (sortBy === 'modified_at') {
                const aTs = Date.parse(String(a.modified_at || '')) || 0;
                const bTs = Date.parse(String(b.modified_at || '')) || 0;
                if (aTs !== bTs) return (aTs - bTs) * direction;
            } else if (sortBy === 'size') {
                const aSize = Number(a.size || 0);
                const bSize = Number(b.size || 0);
                if (aSize !== bSize) return (aSize - bSize) * direction;
            }

            return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }) * direction;
        });
    }, [files, sortBy, sortOrder]);

    const tableGridTemplate = useMemo(() => {
        const dynamicColumns = FILE_BROWSER_COLUMNS.map(
            (column) => `${Math.max(column.minWidth, columnWidths[column.id] ?? column.width)}px`
        );
        return `40px 40px ${dynamicColumns.join(' ')}`;
    }, [columnWidths]);

    const tableMinWidth = useMemo(() => {
        const fixedWidth = 80;
        const dynamicWidth = FILE_BROWSER_COLUMNS.reduce(
            (sum, column) => sum + Math.max(column.minWidth, columnWidths[column.id] ?? column.width),
            0
        );
        return fixedWidth + dynamicWidth;
    }, [columnWidths]);

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

    const beginResize = (event, column) => {
        event.preventDefault();
        event.stopPropagation();
        const startX = event.clientX;
        const initialWidth = Math.max(column.minWidth, columnWidths[column.id] ?? column.width);
        resizeStateRef.current = { columnId: column.id, startX, initialWidth, minWidth: column.minWidth };

        const onMouseMove = (moveEvent) => {
            if (!resizeStateRef.current) return;
            const nextWidth = resizeStateRef.current.initialWidth + (moveEvent.clientX - resizeStateRef.current.startX);
            setColumnWidths((prev) => ({
                ...prev,
                [resizeStateRef.current.columnId]: Math.max(resizeStateRef.current.minWidth, nextWidth),
            }));
        };
        const onMouseUp = () => {
            resizeStateRef.current = null;
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
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
            showToast(e.message, 'error');
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
            showToast(e.message, 'error');
        } finally {
            setActionLoading(false);
        }
    };

    const executeMapComics = async () => {
        if (!isComicsLibraryActive) return;
        if (selectedItems.size === 0) return;
        if (!canMapComics) {
            showToast(t('fileBrowser.mapComicsAvailability'), 'error');
            return;
        }
        setActionLoading(true);
        try {
            await jobsService.createExtractComicAssetsJob(accountId, Array.from(selectedItems));
            showToast(t('fileBrowser.comicsJobCreated'), 'success');
            setMetadataMenuOpen(false);
        } catch (e) {
            showToast(`${t('fileBrowser.failedComicsJob')}: ${e.message}`, 'error');
        } finally {
            setActionLoading(false);
        }
    };

    const executeAnalyzeImages = async () => {
        if (!isImagesLibraryActive) return;
        if (selectedItems.size === 0) return;
        if (!canAnalyzeImages) {
            showToast(t('fileBrowser.analyzeImagesAvailability'), 'error');
            return;
        }
        setActionLoading(true);
        try {
            await jobsService.createAnalyzeImageAssetsJob(accountId, Array.from(selectedItems), false, false);
            showToast(t('fileBrowser.imageAnalysisJobCreated'), 'success');
            setMetadataMenuOpen(false);
        } catch (e) {
            showToast(`${t('fileBrowser.failedImageAnalysisJob')}: ${e.message}`, 'error');
        } finally {
            setActionLoading(false);
        }
    };

    const executeMapBooks = async () => {
        if (!isBooksLibraryActive) return;
        if (selectedItems.size === 0) return;
        if (!canMapBooks) {
            showToast(t('fileBrowser.mapBooksAvailability'), 'error');
            return;
        }
        setActionLoading(true);
        try {
            await jobsService.createExtractBookAssetsJob(accountId, Array.from(selectedItems));
            showToast(t('fileBrowser.booksJobCreated'), 'success');
            setMetadataMenuOpen(false);
        } catch (e) {
            showToast(`${t('fileBrowser.failedBooksJob')}: ${e.message}`, 'error');
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
            showToast(e.message, 'error');
        } finally {
            setActionLoading(false);
        }
    };

    const executeSync = async () => {
        if (!accountId || syncing) return;
        setSyncing(true);
        try {
            await jobsService.createSyncJob(accountId);
            showToast(t('fileBrowser.syncCreated'), 'success');
        } catch (e) {
            showToast(`${t('fileBrowser.failedSync')}: ${e.message}`, 'error');
        } finally {
            setSyncing(false);
        }
    };

    const handleSearchSubmit = (e) => {
        if (e.key === 'Enter') {
            resetPagination();
            setSearchQuery(searchTerm);
        }
    }

    const clearSearch = () => {
        resetPagination();
        setSearchTerm('');
        setSearchQuery('');
    };

    const hasFilesInDragEvent = (event) => {
        const types = Array.from(event?.dataTransfer?.types || []);
        return types.includes('Files');
    };

    const handleNavDragEnter = (event) => {
        if (!accountId || !hasFilesInDragEvent(event)) return;
        event.preventDefault();
        navDragCounterRef.current += 1;
        setIsNavDropActive(true);
    };

    const handleNavDragOver = (event) => {
        if (!accountId || !hasFilesInDragEvent(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'copy';
        if (!isNavDropActive) {
            setIsNavDropActive(true);
        }
    };

    const handleNavDragLeave = (event) => {
        if (!accountId || !hasFilesInDragEvent(event)) return;
        event.preventDefault();
        navDragCounterRef.current = Math.max(0, navDragCounterRef.current - 1);
        if (navDragCounterRef.current === 0) {
            setIsNavDropActive(false);
        }
    };

    const handleNavDrop = (event) => {
        if (!accountId || !hasFilesInDragEvent(event)) return;
        event.preventDefault();
        navDragCounterRef.current = 0;
        setIsNavDropActive(false);
        const droppedFiles = Array.from(event.dataTransfer?.files || []).filter(Boolean);
        if (droppedFiles.length === 0) return;
        showToast(t('fileBrowser.uploadingFiles', { count: droppedFiles.length }), 'info');
        upload(droppedFiles);
    };

    const fileInputRef = useRef(null);

    // Get single selected item for singular actions
    const singleSelectedItem = selectedItems.size === 1
        ? files.find(f => f.id === Array.from(selectedItems)[0])
        : null;
    const canMoveSelected = selectedItems.size === 1;

    const currentFolderPath = breadcrumbs.length > 0
        ? `/${breadcrumbs.map((crumb) => crumb.name).join('/')}`
        : '';

    const selectedItemsForBatchEdit = sortedFiles
        .filter((file) => selectedItems.has(file.id))
        .map((file) => ({
            ...file,
            account_id: accountId,
            item_id: file.id,
            path: file.path || `${currentFolderPath}/${file.name}`.replace('//', '/'),
        }));

    const canMapComics = useMemo(() => {
        if (selectedItems.size === 0) return false;
        const selected = sortedFiles.filter((file) => selectedItems.has(file.id));
        return selected.every((item) => {
            if (item.item_type === 'folder') return true;
            const dotIndex = item.name.lastIndexOf('.');
            if (dotIndex < 0) return false;
            const ext = item.name.slice(dotIndex + 1).toLowerCase();
            return COMIC_MAPPABLE_EXTS.has(ext);
        });
    }, [selectedItems, sortedFiles]);

    const canAnalyzeImages = useMemo(() => {
        if (selectedItems.size === 0) return false;
        const selected = sortedFiles.filter((file) => selectedItems.has(file.id));
        return selected.every((item) => {
            if (item.item_type === 'folder') return true;
            const dotIndex = item.name.lastIndexOf('.');
            if (dotIndex < 0) return false;
            const ext = item.name.slice(dotIndex + 1).toLowerCase();
            return IMAGE_ANALYZABLE_EXTS.has(ext);
        });
    }, [selectedItems, sortedFiles]);

    const canMapBooks = useMemo(() => {
        if (selectedItems.size === 0) return false;
        const selected = sortedFiles.filter((file) => selectedItems.has(file.id));
        return selected.every((item) => {
            if (item.item_type === 'folder') return true;
            const dotIndex = item.name.lastIndexOf('.');
            if (dotIndex < 0) return false;
            const ext = item.name.slice(dotIndex + 1).toLowerCase();
            return BOOK_MAPPABLE_EXTS.has(ext);
        });
    }, [selectedItems, sortedFiles]);

    return (
        <div className="app-page density-compact">
            {/* Unified command bar */}
            <div className="surface-card mb-4 overflow-hidden">
            <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
                <div
                    className={`flex flex-wrap items-center gap-4 overflow-hidden rounded-lg border px-2 py-1.5 transition-colors ${
                        isNavDropActive
                            ? 'border-primary/45 bg-primary/10'
                            : 'border-transparent'
                    }`}
                    onDragEnter={handleNavDragEnter}
                    onDragOver={handleNavDragOver}
                    onDragLeave={handleNavDragLeave}
                    onDrop={handleNavDrop}
                >
                    <nav className="flex items-center text-sm text-muted-foreground overflow-x-auto whitespace-nowrap scrollbar-hide">
                        <Link to={`/drive/${accountId}`} className="hover:text-foreground hover:underline px-1 font-medium">
                            {t('fileBrowser.root')}
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
                    <span className="text-xs text-muted-foreground font-normal bg-muted px-2 py-0.5 rounded-full shrink-0">
                        {t('fileBrowser.items', { count: files.length })}
                    </span>
                    {!searchQuery && (
                        <div className="flex items-center gap-1 text-xs text-muted-foreground">
                            <label className="mr-2 inline-flex items-center gap-1">
                                <span>{t('allFiles.resultsPerPage')}</span>
                                <select
                                    value={pageSize}
                                    onChange={(event) => {
                                        setPageSize(Number(event.target.value));
                                        resetPagination();
                                    }}
                                    className="rounded-md border bg-background px-1.5 py-1 text-xs text-foreground"
                                >
                                    {PAGE_SIZE_OPTIONS.map((option) => (
                                        <option key={option} value={option}>{option}</option>
                                    ))}
                                </select>
                            </label>
                            <span>{t('jobs.page', { page })}</span>
                            <button
                                onClick={goToPrevPage}
                                disabled={!canPrevPage || loading}
                                className="p-1 rounded hover:bg-accent disabled:opacity-50"
                                title={t('jobs.previousPage')}
                            >
                                <ChevronLeft size={14} />
                            </button>
                            <button
                                onClick={goToNextPage}
                                disabled={!canNextPage || loading}
                                className="p-1 rounded hover:bg-accent disabled:opacity-50"
                                title={t('jobs.nextPage')}
                            >
                                <ChevronRight size={14} />
                            </button>
                        </div>
                    )}
                    {isNavDropActive && (
                        <span className="status-chip border-primary/35 bg-primary/12 text-primary whitespace-nowrap">
                            {t('fileBrowser.dropUpload')}
                        </span>
                    )}
                </div>

                <div className="flex flex-wrap items-center justify-end gap-2">
                    <button
                        onClick={executeSync}
                        disabled={!accountId || syncing}
                        className="flex items-center gap-2 px-3 py-2 text-sm font-medium hover:bg-accent rounded-md disabled:opacity-50"
                        title={t('fileBrowser.syncAccount')}
                    >
                        {syncing ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />}
                        {syncing ? t('fileBrowser.syncing') : t('fileBrowser.sync')}
                    </button>
                    <button onClick={() => setCreateFolderModal(true)} className="flex items-center gap-2 px-3 py-2 text-sm font-medium hover:bg-accent rounded-md">
                        <FolderPlus size={16} />
                        {t('fileBrowser.newFolder')}
                    </button>
                    <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50">
                        {uploading ? <Loader2 className="animate-spin" size={16} /> : <UploadCloud size={16} />}
                        {uploading ? t('fileBrowser.uploadingProgress', { progress: uploadProgress }) : t('fileBrowser.upload')}
                    </button>
                    <input
                        type="file"
                        ref={fileInputRef}
                        className="hidden"
                        multiple
                        onChange={(e) => {
                            upload(e.target.files);
                            e.target.value = '';
                        }}
                    />
                </div>
            </header>

            <div className="flex flex-wrap items-center gap-3 px-4 py-2 text-sm">
                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                    <div className="flex items-center w-full max-w-sm relative">
                        <Search className="absolute left-2 text-muted-foreground" size={16} />
                        <input
                            type="text"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            onKeyDown={handleSearchSubmit}
                            placeholder={t('fileBrowser.searchFiles')}
                            className="input-shell pl-8 pr-8 py-1.5 text-sm w-full"
                        />
                        {searchTerm && (
                            <button onClick={clearSearch} className="absolute right-2 text-muted-foreground hover:text-foreground">
                                <X size={14} />
                            </button>
                        )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <select
                            value={sortBy}
                            onChange={(e) => setSortBy(e.target.value)}
                            className="border rounded-md p-1.5 text-xs bg-background"
                            title={t('fileBrowser.orderBy')}
                        >
                            <option value="name">{t('fileBrowser.sort.name')}</option>
                            <option value="modified_at">{t('fileBrowser.sort.modified')}</option>
                            <option value="size">{t('fileBrowser.sort.size')}</option>
                        </select>
                        <button
                            type="button"
                            className="p-1.5 text-xs border rounded-md hover:bg-accent"
                            onClick={() => setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'))}
                            title={t('fileBrowser.sortOrder')}
                            aria-label={t('fileBrowser.sortOrder')}
                        >
                            {sortOrder === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
                        </button>
                    </div>
                </div>

                <div className="flex w-full flex-wrap items-center justify-between gap-2 sm:ml-auto sm:w-auto sm:justify-end">
                    <div className="h-4 w-px bg-border mx-2" />
                    <span className="font-medium mr-2 whitespace-nowrap w-24 text-right tabular-nums">{t('similarFiles.selected', { count: selectedItems.size })}</span>

                    {/* Actions */}
                    <button
                        onClick={handleDownload}
                        disabled={selectedItems.size === 0}
                        className="p-2 hover:bg-background rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        title={t('fileBrowser.download')}
                    >
                        <Download size={16} /> <span className="hidden sm:inline">{t('fileBrowser.download')}</span>
                    </button>

                    <button
                        onClick={() => {
                            if (!canMoveSelected) {
                                showToast(t('fileBrowser.moveSingleOnly'), 'warning');
                                return;
                            }
                            preloadMoveModal();
                            setMoveModal({ isOpen: true });
                        }}
                        disabled={!canMoveSelected}
                        className="p-2 hover:bg-background rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        title={t('fileBrowser.move')}
                    >
                        <ArrowRightLeft size={16} /> <span className="hidden sm:inline">{t('fileBrowser.move')}</span>
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
                            title={t('fileBrowser.metadataActions')}
                        >
                            <Database size={16} />
                            <span className="hidden sm:inline">{t('fileBrowser.metadata')}</span>
                            <ChevronDown size={14} className={`transition-transform ${metadataMenuOpen ? 'rotate-180' : ''}`} />
                        </button>

                        {metadataMenuOpen && (
                            <div className="absolute top-full left-0 w-48 pt-1 layer-dropdown">
                                <div className="bg-popover border rounded-md shadow-md py-1">
                                    <button
                                        onClick={() => {
                                            if (selectedItems.size === 1) {
                                                preloadMetadataModal();
                                                setMetadataModalOpen(true);
                                            } else if (selectedItems.size > 1) {
                                                preloadBatchMetadataModal();
                                                setBatchMetadataModalOpen(true);
                                            }
                                            setMetadataMenuOpen(false);
                                        }}
                                        disabled={selectedItems.size === 0}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                    >
                                        <Database size={14} /> {t('fileBrowser.editMetadata')}
                                    </button>
                                    <button
                                        onClick={() => { setRemoveMetadataModal(true); setMetadataMenuOpen(false); }}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 text-destructive hover:text-destructive"
                                    >
                                        <XCircle size={14} /> {t('fileBrowser.removeMetadata')}
                                    </button>
                                    {(isComicsLibraryActive || isImagesLibraryActive || isBooksLibraryActive) && (
                                        <>
                                            <div className="px-4 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                                                {t('fileBrowser.analyzeAs')}
                                            </div>
                                            {isComicsLibraryActive && (
                                                <button
                                                    onClick={executeMapComics}
                                                    disabled={!canMapComics || actionLoading}
                                                    className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                                >
                                                    {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <BookOpen size={14} />}
                                                    {t('fileBrowser.comics')}
                                                </button>
                                            )}
                                            {isImagesLibraryActive && (
                                                <button
                                                    onClick={executeAnalyzeImages}
                                                    disabled={!canAnalyzeImages || actionLoading}
                                                    className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                                >
                                                    {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <ImageIcon size={14} />}
                                                    {t('fileBrowser.images')}
                                                </button>
                                            )}
                                            {isBooksLibraryActive && (
                                                <button
                                                    onClick={executeMapBooks}
                                                    disabled={!canMapBooks || actionLoading}
                                                    className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                                >
                                                    {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <BookOpen size={14} />}
                                                    {t('fileBrowser.books')}
                                                </button>
                                            )}
                                        </>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    <div className="h-4 w-px bg-border mx-1" />

                    <button
                        onClick={() => setDeleteModal({ isOpen: true })}
                        disabled={selectedItems.size === 0}
                        className="btn-minimal-danger px-2 py-2 disabled:cursor-not-allowed"
                        title={t('fileBrowser.delete')}
                    >
                        <Trash2 size={16} /> <span className="hidden sm:inline">{t('fileBrowser.delete')}</span>
                    </button>
                </div>
            </div>
            </div>

            {/* Content */}
            <main className="flex-1 overflow-auto">
                {loading ? (
                    <div className="flex justify-center p-12">
                        <Loader2 className="animate-spin text-primary" size={32} />
                    </div>
                ) : error ? (
                    <div className="status-badge status-badge-danger block p-4">
                        {t('fileBrowser.errorPrefix')}: {error}
                    </div>
                ) : files.length === 0 ? (
                    <div className="empty-state">
                        <div className="empty-state-icon">
                            <Folder size={26} />
                        </div>
                        <div className="empty-state-title">
                            {searchQuery ? t('fileBrowser.noMatching') : t('fileBrowser.emptyFolder')}
                        </div>
                        <p className="empty-state-text">
                            {searchQuery ? t('fileBrowser.noResults', { query: searchQuery }) : t('fileBrowser.emptyHelp')}
                        </p>
                    </div>
                ) : (
                    <div className="surface-card overflow-hidden select-none">
                        <div className="overflow-x-auto">
                            <div style={{ minWidth: `${tableMinWidth}px` }}>
                                <div
                                    className="sticky top-0 z-20 grid items-center gap-4 border-b border-border/70 bg-muted/95 p-3 text-xs font-medium uppercase tracking-wider text-muted-foreground shadow-sm backdrop-blur supports-[backdrop-filter]:bg-muted/80"
                                    style={{ display: 'grid', gridTemplateColumns: tableGridTemplate, minWidth: `${tableMinWidth}px` }}
                                >
                                    <div className="flex items-center justify-center">
                                        <button onClick={toggleSelectAll} className="hover:text-foreground">
                                            {selectedItems.size === files.length && files.length > 0 ? <CheckSquare size={16} /> : <Square size={16} />}
                                        </button>
                                    </div>
                                    <div className="text-center" />
                                    {FILE_BROWSER_COLUMNS.map((column) => (
                                        <div
                                            key={column.id}
                                            className={`relative flex items-center gap-1 ${column.align === 'right' ? 'justify-end text-right' : ''}`}
                                        >
                                            <div className="pointer-events-none absolute bottom-0 right-0 top-0 w-px bg-border/80" />
                                            <span className="inline-flex items-center gap-1">
                                                <GripVertical size={12} className="opacity-45" />
                                                {column.id === 'size' ? t('similarFiles.size') : t(`fileBrowser.${column.id}`)}
                                            </span>
                                            <div
                                                className="absolute right-[-8px] top-0 h-full w-3 cursor-col-resize"
                                                onMouseDown={(event) => beginResize(event, column)}
                                            />
                                        </div>
                                    ))}
                                </div>

                                <div className="divide-y">
                                    {sortedFiles.map((file, index) => {
                                        const isFolder = file.item_type === 'folder';
                                        const isSelected = selectedItems.has(file.id);
                                        return (
                                            <div
                                                key={file.id}
                                                className={`group gap-4 p-3 items-center hover:bg-accent/35 transition-colors ${isSelected ? 'bg-muted/45' : ''}`}
                                                style={{ display: 'grid', gridTemplateColumns: tableGridTemplate, minWidth: `${tableMinWidth}px` }}
                                                onClick={(e) => toggleSelection(file.id, index, !e.altKey, e.shiftKey)}
                                            >
                                                <div className="flex items-center justify-center">
                                                    <div className={`cursor-pointer ${isSelected ? 'text-primary' : 'text-muted-foreground/50'}`}>
                                                        {isSelected ? <CheckSquare size={16} /> : <Square size={16} />}
                                                    </div>
                                                </div>

                                                <div className="flex justify-center text-muted-foreground">
                                                    {isFolder ? <Folder className="text-primary fill-primary/15" size={20} /> : <File className="text-muted-foreground" size={20} />}
                                                </div>

                                                <div className="relative min-w-0 truncate font-medium">
                                                    <div className="pointer-events-none absolute bottom-[-12px] right-[-8px] top-[-12px] w-px bg-border/50" />
                                                    {isFolder ? (
                                                        <Link
                                                            to={`/drive/${accountId}/${file.id}`}
                                                            className="cursor-pointer text-foreground hover:underline"
                                                            onClick={(e) => e.stopPropagation()}
                                                        >
                                                            {file.name}
                                                        </Link>
                                                    ) : (
                                                        isPreviewableFileName(file.name) ? (
                                                            <button
                                                                type="button"
                                                                className="truncate text-left text-foreground hover:underline"
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    preloadImagePreviewModal();
                                                                    setImagePreviewItem({
                                                                        accountId,
                                                                        itemId: file.id,
                                                                        filename: file.name,
                                                                    });
                                                                }}
                                                                title={t('fileBrowser.previewFile')}
                                                            >
                                                                {file.name}
                                                            </button>
                                                        ) : (
                                                            <span className="text-foreground">
                                                                {file.name}
                                                            </span>
                                                        )
                                                    )}
                                                </div>

                                                <div className="relative text-right text-sm tabular-nums text-muted-foreground">
                                                    <div className="pointer-events-none absolute bottom-[-12px] right-[-8px] top-[-12px] w-px bg-border/50" />
                                                    {formatSize(file.size ?? 0)}
                                                </div>

                                                <div className="relative text-right text-sm tabular-nums text-muted-foreground">
                                                    <div className="pointer-events-none absolute bottom-[-12px] right-0 top-[-12px] w-px bg-border/50" />
                                                    {formatDate(file.modified_at)}
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </main>

            {/* Modals */}
            <Modal
                isOpen={deleteModal.isOpen}
                onClose={() => setDeleteModal({ isOpen: false })}
                title={t('fileBrowser.deleteTitle', { count: selectedItems.size })}
            >
                <div className="space-y-4">
                    <p>{t('fileBrowser.deleteConfirm')}</p>
                    <div className="flex justify-end gap-2">
                        <button onClick={() => setDeleteModal({ isOpen: false })} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">
                            {t('common.cancel')}
                        </button>
                        <button onClick={executeDelete} disabled={actionLoading} className="px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50 flex items-center gap-2">
                            {actionLoading && <Loader2 className="animate-spin" size={14} />}
                            {t('fileBrowser.delete')}
                        </button>
                    </div>
                </div>
            </Modal>

            <Modal
                isOpen={removeMetadataModal}
                onClose={() => setRemoveMetadataModal(false)}
                title={t('fileBrowser.removeMetadataTitle', { count: selectedItems.size })}
            >
                <div className="space-y-4">
                    <p>{t('fileBrowser.removeMetadataConfirm')}</p>
                    <div className="flex justify-end gap-2">
                        <button onClick={() => setRemoveMetadataModal(false)} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">
                            {t('common.cancel')}
                        </button>
                        <button onClick={executeRemoveMetadata} disabled={actionLoading} className="px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50 flex items-center gap-2">
                            {actionLoading && <Loader2 className="animate-spin" size={14} />}
                            {t('fileBrowser.remove')}
                        </button>
                    </div>
                </div>
            </Modal>

            <Modal
                isOpen={createFolderModal}
                onClose={() => setCreateFolderModal(false)}
                title={t('fileBrowser.createFolder')}
            >
                <form onSubmit={executeCreateFolder} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">{t('fileBrowser.folderName')}</label>
                        <input
                            type="text"
                            className="w-full border rounded-md p-2 bg-background"
                            value={newFolderName}
                            onChange={e => setNewFolderName(e.target.value)}
                            placeholder={t('fileBrowser.folderPlaceholder')}
                            autoFocus
                        />
                    </div>
                    <div className="flex justify-end gap-2">
                        <button type="button" onClick={() => setCreateFolderModal(false)} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">
                            {t('common.cancel')}
                        </button>
                        <button type="submit" disabled={actionLoading || !newFolderName.trim()} className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2">
                            {actionLoading && <Loader2 className="animate-spin" size={14} />}
                            {t('fileBrowser.create')}
                        </button>
                    </div>
                </form>
            </Modal>

            {metadataModalOpen && (
                <Suspense fallback={null}>
                    <MetadataModal
                        isOpen={metadataModalOpen}
                        onClose={() => setMetadataModalOpen(false)}
                        item={singleSelectedItem}
                        accountId={accountId}
                        onSuccess={() => {
                            void refresh();
                        }}
                    />
                </Suspense>
            )}

            {batchMetadataModalOpen && (
                <Suspense fallback={null}>
                    <BatchMetadataModal
                        isOpen={batchMetadataModalOpen}
                        onClose={() => setBatchMetadataModalOpen(false)}
                        selectedItems={selectedItemsForBatchEdit}
                        showToast={showToast}
                        onSuccess={() => {
                            setBatchMetadataModalOpen(false);
                            setSelectedItems(new Set());
                            void refresh();
                        }}
                    />
                </Suspense>
            )}

            {moveModal.isOpen && (
                <Suspense fallback={null}>
                    <MoveModal
                        isOpen={moveModal.isOpen}
                        onClose={() => setMoveModal({ isOpen: false })}
                        item={singleSelectedItem}
                        sourceAccountId={accountId}
                        onSuccess={() => {
                            setMoveModal({ isOpen: false });
                            setSelectedItems(new Set());
                            void refresh();
                        }}
                    />
                </Suspense>
            )}

            {imagePreviewItem && (
                <Suspense fallback={null}>
                    <ImagePreviewModal
                        isOpen={Boolean(imagePreviewItem)}
                        onClose={() => setImagePreviewItem(null)}
                        accountId={imagePreviewItem?.accountId}
                        itemId={imagePreviewItem?.itemId}
                        filename={imagePreviewItem?.filename}
                    />
                </Suspense>
            )}
        </div>
    );
}
