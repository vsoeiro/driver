import { Fragment, useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Suspense, lazy } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { useToast } from '../contexts/ToastContext';
import { useWorkspacePage } from '../contexts/WorkspaceContext';
import {
    File, Folder, FolderOpen, Search, Filter, Database, CheckSquare, Square,
    Loader2, ChevronLeft, ChevronRight, ArrowUpDown, ArrowUp, ArrowDown, X, Trash2, ChevronDown, BookOpen, Pencil, Columns3, GripVertical,
    Download, ArrowRightLeft, XCircle, UploadCloud, Image as ImageIcon, Archive
} from 'lucide-react';
import Modal from '../components/Modal';
import ProviderIcon from '../components/ProviderIcon';
import { useAccountsQuery, useItemsListQuery, useMetadataCategoriesQuery, useMetadataLibrariesQuery } from '../hooks/useAppQueries';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { isPreviewableFileName } from '../utils/imagePreview';
import { formatDateTime } from '../utils/dateTime';
import { useDriveActions } from '../features/drive/hooks/useDriveData';
import { useItemsCacheActions } from '../features/items/hooks/useItemsData';
import { useJobsActions } from '../features/jobs/hooks/useJobsData';

const MetadataModal = lazy(() => import('../components/MetadataModal'));
const BatchMetadataModal = lazy(() => import('../components/BatchMetadataModal'));
const RemoveMetadataModal = lazy(() => import('../components/RemoveMetadataModal'));
const MoveModal = lazy(() => import('../components/MoveModal'));
const ExtractZipModal = lazy(() => import('../components/ExtractZipModal'));
const SimilarFilesReportTab = lazy(() => import('../components/SimilarFilesReportTab'));
const ImagePreviewModal = lazy(() => import('../components/ImagePreviewModal'));

const COMIC_MAPPABLE_EXTS = new Set(['cbz', 'zip', 'cbw', 'pdf', 'epub', 'cbr', 'rar', 'cb7', '7z', 'cbt', 'tar']);
const BOOK_MAPPABLE_EXTS = new Set(['pdf', 'epub']);
const IMAGE_ANALYZABLE_EXTS = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tiff', 'tif', 'heic', 'avif']);
const ZIP_EXTRACTABLE_EXTS = new Set(['zip']);
const ALL_FILES_COLUMNS_STORAGE_KEY = 'driver-all-files-columns-v1';
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200];
const ALL_FILES_COLUMNS = [
    { id: 'name', label: 'Name', width: 280, minWidth: 180, sortKey: 'name' },
    { id: 'account', label: 'Account', width: 190, minWidth: 150, sortKey: null },
    { id: 'size', label: 'Size', width: 110, minWidth: 90, sortKey: 'size', align: 'right' },
    { id: 'category', label: 'Category', width: 110, minWidth: 90, sortKey: null },
    { id: 'modified', label: 'Modified', width: 160, minWidth: 130, sortKey: 'modified_at' },
    { id: 'path', label: 'Path', width: 280, minWidth: 150, sortKey: null },
];

const getDefaultAllFilesColumnPreferences = () => ({
    order: ALL_FILES_COLUMNS.map((column) => column.id),
    visibility: ALL_FILES_COLUMNS.reduce((acc, column) => ({ ...acc, [column.id]: true }), {}),
    widths: ALL_FILES_COLUMNS.reduce((acc, column) => ({ ...acc, [column.id]: column.width }), {}),
});

const loadAllFilesColumnPreferences = () => {
    const defaults = getDefaultAllFilesColumnPreferences();
    if (typeof window === 'undefined') return defaults;

    try {
        const raw = window.localStorage.getItem(ALL_FILES_COLUMNS_STORAGE_KEY);
        if (!raw) return defaults;

        const parsed = JSON.parse(raw);
        const validIds = new Set(defaults.order);
        const loadedOrder = Array.isArray(parsed.order)
            ? parsed.order.filter((id) => validIds.has(id))
            : [];
        const nextOrder = [...loadedOrder, ...defaults.order.filter((id) => !loadedOrder.includes(id))];
        const nextVisibility = { ...defaults.visibility };
        const nextWidths = { ...defaults.widths };

        if (parsed.visibility && typeof parsed.visibility === 'object') {
            defaults.order.forEach((id) => {
                if (Object.prototype.hasOwnProperty.call(parsed.visibility, id)) {
                    nextVisibility[id] = Boolean(parsed.visibility[id]);
                }
            });
        }

        if (parsed.widths && typeof parsed.widths === 'object') {
            ALL_FILES_COLUMNS.forEach((column) => {
                const candidate = Number(parsed.widths[column.id]);
                if (Number.isFinite(candidate)) {
                    nextWidths[column.id] = Math.max(column.minWidth, candidate);
                }
            });
        }

        return {
            order: nextOrder,
            visibility: nextVisibility,
            widths: nextWidths,
        };
    } catch {
        return defaults;
    }
};

const getExtractZipParentPath = (itemPath) => {
    if (!itemPath || itemPath === '/') return '/';
    const normalized = String(itemPath).replace(/\/+$/, '');
    const lastSlash = normalized.lastIndexOf('/');
    if (lastSlash <= 0) return '/';
    return normalized.slice(0, lastSlash);
};

const normalizeFolderPath = (value) => {
    if (!value || value === '/') return '/';

    const normalized = String(value)
        .replace(/\\/g, '/')
        .replace(/\/+/g, '/')
        .replace(/^\/+/, '')
        .replace(/\/+$/, '');

    return normalized ? `/${normalized}` : '/';
};

const hasFolderTargetIdentity = (target) => Boolean(target?.account_id && target?.item_id);

const inferFolderTargetFromItems = (pathPrefix, items, preferredAccountId) => {
    const normalizedPath = normalizeFolderPath(pathPrefix);
    if (normalizedPath === '/' || !Array.isArray(items) || items.length === 0) return null;

    const candidates = items.reduce((acc, item) => {
        if (!item?.account_id || !item?.parent_id) return acc;
        const key = `${item.account_id}:${item.parent_id}`;
        if (!acc.some((candidate) => candidate.key === key)) {
            acc.push({
                key,
                account_id: item.account_id,
                item_id: item.parent_id,
                path: normalizedPath,
            });
        }
        return acc;
    }, []);

    if (candidates.length === 0) return null;

    const preferredCandidates = preferredAccountId
        ? candidates.filter((candidate) => candidate.account_id === preferredAccountId)
        : candidates;

    const resolved = preferredCandidates.length === 1
        ? preferredCandidates[0]
        : candidates.length === 1
            ? candidates[0]
            : null;

    if (!resolved) return null;

    return {
        account_id: resolved.account_id,
        item_id: resolved.item_id,
        path: resolved.path,
    };
};

const getColumnAlignmentClasses = (align) => {
    if (align === 'right') return 'justify-end pr-2 text-right';
    if (align === 'center') return 'justify-center px-2 text-center';
    return 'justify-start pl-2 text-left';
};

// Filter Component
const FilterBar = ({ onFilter, filters, accounts, categories }) => {
    const { t } = useTranslation();
    const [localFilters, setLocalFilters] = useState(filters);
    const [isOpen, setIsOpen] = useState(false);
    const [extensionsInput, setExtensionsInput] = useState((filters.extensions || []).join(', '));

    useEffect(() => {
        setLocalFilters(filters);
        setExtensionsInput((filters.extensions || []).join(', '));
    }, [filters]);

    const handleChange = (key, value) => {
        setLocalFilters(prev => ({ ...prev, [key]: value }));
    };

    const applyFilters = () => {
        onFilter(localFilters);
        setIsOpen(false);
    };

    const clearFilters = () => {
        const cleared = {
            extensions: [],
            size_min: '',
            size_max: '',
            item_type: '',
            account_id: '',
            category_id: '',
            has_metadata: ''
        };
        setLocalFilters(cleared);
        setExtensionsInput('');
        onFilter(cleared);
    };

    return (
        <div className="relative layer-dropdown">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className={`flex items-center gap-2 px-3 py-2 border rounded-md text-sm font-medium ${isOpen ? 'bg-accent text-accent-foreground' : 'hover:bg-accent'}`}
            >
                <Filter size={16} /> {t('allFiles.filters')}
            </button>

            {isOpen && (
                <div className="menu-popover absolute right-0 top-full mt-2 w-72 p-4 layer-popover space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">{t('allFiles.account')}</label>
                        <select
                            className="w-full border rounded-md p-2 text-sm bg-background"
                            value={localFilters.account_id || ''}
                            onChange={(e) => handleChange('account_id', e.target.value)}
                        >
                            <option value="">{t('allFiles.allAccounts')}</option>
                            {accounts?.map(acc => (
                                <option key={acc.id} value={acc.id}>{acc.email || acc.display_name}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">{t('allFiles.category')}</label>
                        <select
                            className="w-full border rounded-md p-2 text-sm bg-background"
                            value={localFilters.category_id || ''}
                            onChange={(e) => handleChange('category_id', e.target.value)}
                        >
                            <option value="">{t('allFiles.allCategories')}</option>
                            {categories?.map(cat => (
                                <option key={cat.id} value={cat.id}>{cat.name}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">{t('allFiles.hasMetadata')}</label>
                        <select
                            className="w-full border rounded-md p-2 text-sm bg-background"
                            value={localFilters.has_metadata ?? ''}
                            onChange={(e) => handleChange('has_metadata', e.target.value)}
                        >
                            <option value="">{t('allFiles.all')}</option>
                            <option value="true">{t('allFiles.withMetadata')}</option>
                            <option value="false">{t('allFiles.withoutMetadata')}</option>
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">{t('allFiles.type')}</label>
                        <select
                            className="w-full border rounded-md p-2 text-sm bg-background"
                            value={localFilters.item_type || ''}
                            onChange={(e) => handleChange('item_type', e.target.value)}
                        >
                            <option value="">{t('allFiles.all')}</option>
                            <option value="file">{t('allFiles.files')}</option>
                            <option value="folder">{t('allFiles.folders')}</option>
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">{t('allFiles.extensions')}</label>
                        <input
                            type="text"
                            className="w-full border rounded-md p-2 text-sm bg-background"
                            placeholder={t('allFiles.extensionsPlaceholder')}
                            value={extensionsInput}
                            onChange={(e) => {
                                const raw = e.target.value;
                                setExtensionsInput(raw);
                                const exts = raw.split(',').map((s) => s.trim()).filter(Boolean);
                                handleChange('extensions', exts);
                            }}
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">{t('allFiles.sizeBytes')}</label>
                        <div className="flex gap-2">
                            <input
                                type="number"
                                placeholder={t('allFiles.min')}
                                className="w-full border rounded-md p-2 text-sm bg-background"
                                value={localFilters.size_min || ''}
                                onChange={(e) => handleChange('size_min', e.target.value)}
                            />
                            <input
                                type="number"
                                placeholder={t('allFiles.max')}
                                className="w-full border rounded-md p-2 text-sm bg-background"
                                value={localFilters.size_max || ''}
                                onChange={(e) => handleChange('size_max', e.target.value)}
                            />
                        </div>
                    </div>

                    <div className="flex justify-between pt-2">
                        <button onClick={clearFilters} className="text-sm text-muted-foreground hover:text-foreground">{t('allFiles.clear')}</button>
                        <button onClick={applyFilters} className="bg-primary text-primary-foreground px-3 py-1.5 rounded-md text-sm font-medium">{t('allFiles.apply')}</button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default function AllFiles() {
    const { t, i18n } = useTranslation();
    const location = useLocation();
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(50);
    const [activeTab, setActiveTab] = useState('library');

    const [filters, setFilters] = useState({
        extensions: [],
        size_min: '',
        size_max: '',
        item_type: '',
        account_id: '',
        category_id: '',
        has_metadata: ''
    });

    const [sort, setSort] = useState({ by: 'modified_at', order: 'desc' });
    const [searchTerm, setSearchTerm] = useState('');
    const debouncedSearchTerm = useDebouncedValue(searchTerm, 300);
    const [searchScope, setSearchScope] = useState('both');
    const [pathPrefix, setPathPrefix] = useState('');
    const [selectedItems, setSelectedItems] = useState(new Set());
    const [lastSelectedIndex, setLastSelectedIndex] = useState(null);

    const [batchModalOpen, setBatchModalOpen] = useState(false);
    const [metadataModalOpen, setMetadataModalOpen] = useState(false);
    const [removeModalOpen, setRemoveModalOpen] = useState(false);
    const [deleteModalOpen, setDeleteModalOpen] = useState(false);
    const [moveModalOpen, setMoveModalOpen] = useState(false);
    const [extractZipModalOpen, setExtractZipModalOpen] = useState(false);
    const [metadataMenuOpen, setMetadataMenuOpen] = useState(false);
    const [actionLoading, setActionLoading] = useState(false);
    const [extractZipSubmitting, setExtractZipSubmitting] = useState(false);
    const [mapLibraryLoading, setMapLibraryLoading] = useState(false);
    const [mapLibraryConfirmOpen, setMapLibraryConfirmOpen] = useState(false);
    const [mapLibraryMode, setMapLibraryMode] = useState('comics');
    const [analyzeLibraryMenuOpen, setAnalyzeLibraryMenuOpen] = useState(false);
    const [mapLibraryChunkSize, setMapLibraryChunkSize] = useState(1000);
    const [renameModalOpen, setRenameModalOpen] = useState(false);
    const [renameValue, setRenameValue] = useState('');
    const [renameSaving, setRenameSaving] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [currentFolderTarget, setCurrentFolderTarget] = useState(null);
    const [folderTargetsByPath, setFolderTargetsByPath] = useState({});
    const [imagePreviewItem, setImagePreviewItem] = useState(null);
    const fileInputRef = useRef(null);
    const metadataMenuRef = useRef(null);
    const analyzeLibraryMenuRef = useRef(null);
    const [columnsMenuOpen, setColumnsMenuOpen] = useState(false);
    const columnsMenuRef = useRef(null);
    const resizeStateRef = useRef(null);
    const [draggingColumnId, setDraggingColumnId] = useState(null);
    const initialColumnPreferencesRef = useRef(null);
    if (initialColumnPreferencesRef.current === null) {
        initialColumnPreferencesRef.current = loadAllFilesColumnPreferences();
    }
    const initialColumnPreferences = initialColumnPreferencesRef.current;
    const [columnOrder, setColumnOrder] = useState(() => initialColumnPreferences.order);
    const [columnVisibility, setColumnVisibility] = useState(() => initialColumnPreferences.visibility);
    const [columnWidths, setColumnWidths] = useState(() => initialColumnPreferences.widths);

    const { showToast } = useToast();
    const { batchDeleteItems, getDownloadUrl, updateItem } = useDriveActions();
    const { invalidateItemsList } = useItemsCacheActions();
    const {
        createAnalyzeImageAssetsJob,
        createAnalyzeLibraryImageAssetsJob,
        createExtractBookAssetsJob,
        createExtractComicAssetsJob,
        createExtractLibraryComicAssetsJob,
        createExtractZipJob,
        createMapLibraryBooksJob,
        uploadFileBackground,
    } = useJobsActions();
    const { data: accounts = [] } = useAccountsQuery();
    const { data: metaCategories = [] } = useMetadataCategoriesQuery();
    const { data: metadataLibraries = [] } = useMetadataLibrariesQuery();
    const isComicsLibraryActive = Boolean(metadataLibraries.find((library) => library.key === 'comics_core')?.is_active);
    const isImagesLibraryActive = Boolean(metadataLibraries.find((library) => library.key === 'images_core')?.is_active);
    const isBooksLibraryActive = Boolean(metadataLibraries.find((library) => library.key === 'books_core')?.is_active);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (metadataMenuRef.current && !metadataMenuRef.current.contains(event.target)) {
                setMetadataMenuOpen(false);
            }
            if (analyzeLibraryMenuRef.current && !analyzeLibraryMenuRef.current.contains(event.target)) {
                setAnalyzeLibraryMenuOpen(false);
            }
            if (columnsMenuRef.current && !columnsMenuRef.current.contains(event.target)) {
                setColumnsMenuOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    useEffect(() => {
        if (location.state?.focusTab === 'similar') {
            setActiveTab('similar');
        }
    }, [location.state]);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        const payload = {
            order: columnOrder,
            visibility: columnVisibility,
            widths: columnWidths,
        };
        window.localStorage.setItem(ALL_FILES_COLUMNS_STORAGE_KEY, JSON.stringify(payload));
    }, [columnOrder, columnVisibility, columnWidths]);

    const itemsQueryParams = useMemo(() => {
        const isSearching = debouncedSearchTerm.trim().length > 0;
        return {
            page,
            page_size: pageSize,
            sort_by: sort.by,
            sort_order: sort.order,
            q: debouncedSearchTerm,
            search_fields: searchScope,
            path_prefix: pathPrefix,
            direct_children_only: !!pathPrefix && !isSearching,
            ...filters,
        };
    }, [debouncedSearchTerm, filters, page, pageSize, pathPrefix, searchScope, sort.by, sort.order]);

    const {
        data: itemsResponse,
        isPending: loading,
    } = useItemsListQuery(itemsQueryParams, {
        staleTime: 30000,
    });
    const items = useMemo(() => itemsResponse?.items || [], [itemsResponse?.items]);
    const total = itemsResponse?.total || 0;
    const totalPages = itemsResponse?.total_pages || 1;
    const normalizedPathPrefix = useMemo(() => normalizeFolderPath(pathPrefix), [pathPrefix]);

    const invalidateItems = useCallback(async () => {
        await invalidateItemsList();
    }, [invalidateItemsList]);

    // Selection Logic (copied from FileBrowser)
    const toggleSelection = (id, index, multiSelect, rangeSelect) => {
        const newSelection = new Set(multiSelect ? selectedItems : []);
        if (rangeSelect && lastSelectedIndex !== null) {
            const start = Math.min(lastSelectedIndex, index);
            const end = Math.max(lastSelectedIndex, index);
            for (let i = start; i <= end; i++) {
                newSelection.add(items[i].id);
            }
        } else {
            if (newSelection.has(id)) newSelection.delete(id);
            else newSelection.add(id);
        }
        setSelectedItems(newSelection);
        setLastSelectedIndex(index);
    };

    const toggleSelectAll = () => {
        if (selectedItems.size === items.length) setSelectedItems(new Set());
        else setSelectedItems(new Set(items.map(f => f.id)));
    };

    const handleSort = (column) => {
        if (sort.by === column) {
            setSort(prev => ({ ...prev, order: prev.order === 'asc' ? 'desc' : 'asc' }));
        } else {
            setSort({ by: column, order: 'desc' });
        }
    };

    const renderSortIcon = (column) => {
        if (sort.by !== column) return <ArrowUpDown size={14} className="opacity-50" />;
        return sort.order === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />;
    };

    const formatSize = (bytes) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const formatDate = (dateString) => {
        return formatDateTime(dateString, i18n.language);
    };

    const getSelectedObjects = useCallback(
        () => items.filter((item) => selectedItems.has(item.id)),
        [items, selectedItems],
    );

    const singleSelectedItem = useMemo(() => {
        if (selectedItems.size !== 1) return null;
        const selectedId = Array.from(selectedItems)[0];
        return items.find((i) => i.id === selectedId) || null;
    }, [selectedItems, items]);
    const selectedItemsForZipExtraction = useMemo(
        () => getSelectedObjects().filter((item) => {
            if (item.item_type !== 'file') return false;
            const dotIndex = item.name.lastIndexOf('.');
            if (dotIndex < 0) return false;
            const ext = item.name.slice(dotIndex + 1).toLowerCase();
            return ZIP_EXTRACTABLE_EXTS.has(ext);
        }),
        [getSelectedObjects],
    );
    const moveTargetItem = singleSelectedItem
        ? { ...singleSelectedItem, id: singleSelectedItem.item_id }
        : null;
    const selectedFolderTarget = singleSelectedItem?.item_type === 'folder'
        ? singleSelectedItem
        : null;
    const contextualFolderTarget = useMemo(() => {
        if (!pathPrefix) return null;

        const explicitTarget = currentFolderTarget?.path
            && normalizeFolderPath(currentFolderTarget.path) === normalizedPathPrefix
            ? { ...currentFolderTarget, path: normalizedPathPrefix }
            : null;
        if (hasFolderTargetIdentity(explicitTarget)) {
            return explicitTarget;
        }

        const cachedTarget = folderTargetsByPath[normalizedPathPrefix];
        if (hasFolderTargetIdentity(cachedTarget)) {
            return { ...cachedTarget, path: normalizedPathPrefix };
        }

        return inferFolderTargetFromItems(
            normalizedPathPrefix,
            items,
            explicitTarget?.account_id || cachedTarget?.account_id || filters.account_id || null,
        );
    }, [currentFolderTarget, filters.account_id, folderTargetsByPath, items, normalizedPathPrefix, pathPrefix]);
    const uploadTargetFolder = selectedFolderTarget || contextualFolderTarget;
    const canUploadToFolder = Boolean(uploadTargetFolder?.account_id && uploadTargetFolder?.item_id);

    useEffect(() => {
        if (!pathPrefix || !contextualFolderTarget) return;

        const normalizedTargetPath = normalizeFolderPath(contextualFolderTarget.path);
        const sameCurrentTarget = currentFolderTarget
            && normalizeFolderPath(currentFolderTarget.path) === normalizedTargetPath
            && currentFolderTarget.account_id === contextualFolderTarget.account_id
            && currentFolderTarget.item_id === contextualFolderTarget.item_id;

        if (!sameCurrentTarget) {
            setCurrentFolderTarget(contextualFolderTarget);
        }

        setFolderTargetsByPath((prev) => {
            const cachedTarget = prev[normalizedTargetPath];
            if (
                cachedTarget
                && cachedTarget.account_id === contextualFolderTarget.account_id
                && cachedTarget.item_id === contextualFolderTarget.item_id
                && normalizeFolderPath(cachedTarget.path) === normalizedTargetPath
            ) {
                return prev;
            }

            return {
                ...prev,
                [normalizedTargetPath]: { ...contextualFolderTarget, path: normalizedTargetPath },
            };
        });
    }, [contextualFolderTarget, currentFolderTarget, pathPrefix]);

    const canMapComics = useMemo(() => {
        if (selectedItems.size === 0) return false;
        const selected = items.filter((item) => selectedItems.has(item.id));
        return selected.every((item) => {
            if (item.item_type === 'folder') return true;
            const dotIndex = item.name.lastIndexOf('.');
            if (dotIndex < 0) return false;
            const ext = item.name.slice(dotIndex + 1).toLowerCase();
            return COMIC_MAPPABLE_EXTS.has(ext);
        });
    }, [selectedItems, items]);

    const canAnalyzeImages = useMemo(() => {
        if (selectedItems.size === 0) return false;
        const selected = items.filter((item) => selectedItems.has(item.id));
        return selected.every((item) => {
            if (item.item_type === 'folder') return true;
            const dotIndex = item.name.lastIndexOf('.');
            if (dotIndex < 0) return false;
            const ext = item.name.slice(dotIndex + 1).toLowerCase();
            return IMAGE_ANALYZABLE_EXTS.has(ext);
        });
    }, [selectedItems, items]);

    const canMapBooks = useMemo(() => {
        if (selectedItems.size === 0) return false;
        const selected = items.filter((item) => selectedItems.has(item.id));
        return selected.every((item) => {
            if (item.item_type === 'folder') return true;
            const dotIndex = item.name.lastIndexOf('.');
            if (dotIndex < 0) return false;
            const ext = item.name.slice(dotIndex + 1).toLowerCase();
            return BOOK_MAPPABLE_EXTS.has(ext);
        });
    }, [selectedItems, items]);
    const canExtractZips = useMemo(() => {
        if (selectedItems.size === 0) return false;
        const selected = items.filter((item) => selectedItems.has(item.id));
        return selected.every((item) => {
            if (item.item_type !== 'file') return false;
            const dotIndex = item.name.lastIndexOf('.');
            if (dotIndex < 0) return false;
            const ext = item.name.slice(dotIndex + 1).toLowerCase();
            return ZIP_EXTRACTABLE_EXTS.has(ext);
        });
    }, [selectedItems, items]);
    const extractZipInitialTarget = useMemo(() => {
        if (selectedItemsForZipExtraction.length > 0) {
            const [firstItem] = selectedItemsForZipExtraction;
            const parentPath = getExtractZipParentPath(firstItem.path);
            const folderId = firstItem.parent_id || 'root';
            const hasDeterministicFolder = folderId === 'root' || Boolean(firstItem.parent_id);
            const sameLocation = selectedItemsForZipExtraction.every((item) => (
                item.account_id === firstItem.account_id
                && (item.parent_id || 'root') === folderId
                && getExtractZipParentPath(item.path) === parentPath
            ));

            if (sameLocation && hasDeterministicFolder) {
                return {
                    account_id: firstItem.account_id,
                    folder_id: folderId,
                    folder_path: parentPath === '/'
                        ? t('folderPicker.root')
                        : `${t('folderPicker.root')}${parentPath}`,
                };
            }
        }

        if (!contextualFolderTarget?.account_id || !contextualFolderTarget?.item_id) {
            return null;
        }
        return {
            account_id: contextualFolderTarget.account_id,
            folder_id: contextualFolderTarget.item_id,
            folder_path: contextualFolderTarget.path || t('folderPicker.root'),
        };
    }, [contextualFolderTarget, selectedItemsForZipExtraction, t]);

    const orderedColumns = useMemo(() => {
        const map = new Map(ALL_FILES_COLUMNS.map((col) => [col.id, col]));
        return columnOrder.map((id) => map.get(id)).filter(Boolean);
    }, [columnOrder]);

    const visibleColumns = useMemo(
        () => orderedColumns.filter((col) => columnVisibility[col.id] !== false),
        [orderedColumns, columnVisibility]
    );

    const dataGridTemplate = useMemo(() => {
        const dynamicCols = visibleColumns.map((col) => `${Math.max(col.minWidth, columnWidths[col.id] ?? col.width)}px`);
        return `40px 40px ${dynamicCols.join(' ')}`;
    }, [visibleColumns, columnWidths]);

    const tableMinWidth = useMemo(() => {
        const base = 80;
        const totalColumns = 2 + visibleColumns.length;
        const gapPx = Math.max(0, totalColumns - 1) * 16; // gap-4
        const dynamic = visibleColumns.reduce(
            (sum, col) => sum + Math.max(col.minWidth, columnWidths[col.id] ?? col.width),
            0
        );
        return base + dynamic + gapPx;
    }, [visibleColumns, columnWidths]);

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

    const handleColumnDrop = (targetId) => {
        if (!draggingColumnId || draggingColumnId === targetId) return;
        setColumnOrder((prev) => {
            const withoutDragged = prev.filter((id) => id !== draggingColumnId);
            const targetIndex = withoutDragged.indexOf(targetId);
            if (targetIndex < 0) return prev;
            const next = [...withoutDragged];
            next.splice(targetIndex, 0, draggingColumnId);
            return next;
        });
        setDraggingColumnId(null);
    };

    const getAccountName = (accountId) => {
        const acc = accounts.find(a => a.id === accountId);
        return acc ? acc.email : (accountId ? accountId.slice(0, 8) : '-');
    };

    const getAccountById = (accountId) => accounts.find((a) => a.id === accountId);

    const getParentPath = (path) => {
        if (!path || path === '/') return '/';
        const normalized = String(path).replace(/\/+$/, '');
        const lastSlash = normalized.lastIndexOf('/');
        if (lastSlash <= 0) return '/';
        return normalized.slice(0, lastSlash);
    };

    const openFolderFromPath = (item, event) => {
        event.stopPropagation();
        const targetPath = normalizeFolderPath(
            item.item_type === 'folder' ? (item.path || `/${item.name}`) : getParentPath(item.path || '')
        );
        const targetFolder = {
            account_id: item.account_id,
            item_id: item.item_type === 'folder' ? item.item_id : (item.parent_id || null),
            path: targetPath,
        };
        setCurrentFolderTarget(targetFolder);
        setFolderTargetsByPath((prev) => ({ ...prev, [targetPath]: targetFolder }));
        setSearchTerm('');
        setPathPrefix(targetPath);
        setPage(1);
    };

    const renderColumnCell = (item, column) => {
        switch (column.id) {
            case 'name':
                return (
                    <div className="min-w-0 truncate font-medium" title={item.name}>
                        {item.item_type === 'file' && isPreviewableFileName(item.name) ? (
                            <button
                                type="button"
                                className="truncate text-left hover:underline"
                                onClick={(event) => {
                                    event.stopPropagation();
                                    setImagePreviewItem({
                                        accountId: item.account_id,
                                        itemId: item.item_id,
                                        filename: item.name,
                                    });
                                }}
                                title={t('allFiles.previewFile')}
                            >
                                {item.name}
                            </button>
                        ) : (
                            item.name
                        )}
                    </div>
                );
            case 'account':
                return (
                    <div className="flex items-center gap-1 text-sm text-foreground min-w-0">
                        <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                            <ProviderIcon provider={getAccountById(item.account_id)?.provider} className="w-3 h-3" />
                        </div>
                        <span className="truncate" title={getAccountName(item.account_id)}>
                            {getAccountName(item.account_id)}
                        </span>
                    </div>
                );
            case 'size':
                return <div className="text-sm text-muted-foreground tabular-nums">{formatSize(item.size ?? 0)}</div>;
            case 'category':
                return (
                    <div className="min-w-0 text-sm text-muted-foreground truncate">
                        {item.metadata
                            ? (
                                <span className="status-badge status-badge-info" title={item.metadata.category_name}>
                                    {item.metadata.category_name || 'N/A'}
                                </span>
                            )
                            : '-'}
                    </div>
                );
            case 'modified':
                return <div className="text-sm text-muted-foreground tabular-nums">{formatDate(item.modified_at)}</div>;
            case 'path':
                return (
                    <div className="min-w-0 text-xs text-muted-foreground truncate">
                        <button
                            type="button"
                            className="max-w-full truncate text-left hover:text-foreground hover:underline"
                            onClick={(event) => openFolderFromPath(item, event)}
                            title={t('allFiles.showFolderContents')}
                        >
                            {item.path}
                        </button>
                    </div>
                );
            default:
                return null;
        }
    };

    const handleFolderClick = (item) => {
        const folderPath = normalizeFolderPath(item.path || `/${item.name}`);
        const folderTarget = {
            account_id: item.account_id,
            item_id: item.item_id,
            path: folderPath,
        };
        setCurrentFolderTarget(folderTarget);
        setFolderTargetsByPath((prev) => ({ ...prev, [folderPath]: folderTarget }));
        setSearchTerm('');
        setPathPrefix(folderPath);
        setPage(1);
    };

    const clearPathPrefix = () => {
        setSearchTerm('');
        setCurrentFolderTarget(null);
        setPathPrefix('');
        setPage(1);
    };

    const executeMapComics = async () => {
        if (!isComicsLibraryActive) return;
        if (selectedItems.size === 0) return;
        if (!canMapComics) {
            showToast(t('allFiles.mapComicsAvailability'), 'error');
            return;
        }
        setActionLoading(true);
        try {
            const selected = getSelectedObjects();
            const byAccount = {};
            for (const item of selected) {
                if (!byAccount[item.account_id]) byAccount[item.account_id] = [];
                byAccount[item.account_id].push(item.item_id);
            }

            const entries = Object.entries(byAccount);
            await Promise.all(
                entries.map(([accountId, itemIds]) =>
                    createExtractComicAssetsJob(accountId, itemIds)
                )
            );

            showToast(t('allFiles.comicJobsCreated', { count: entries.length }), 'success');
            setMetadataMenuOpen(false);
        } catch (error) {
            showToast(`${t('allFiles.failedCreateComicJob')}: ${error.message}`, 'error');
        } finally {
            setActionLoading(false);
        }
    };

    const executeAnalyzeImages = async () => {
        if (!isImagesLibraryActive) return;
        if (selectedItems.size === 0) return;
        if (!canAnalyzeImages) {
            showToast(t('allFiles.analyzeImagesAvailability'), 'error');
            return;
        }
        setActionLoading(true);
        try {
            const selected = getSelectedObjects();
            const byAccount = {};
            for (const item of selected) {
                if (!byAccount[item.account_id]) byAccount[item.account_id] = [];
                byAccount[item.account_id].push(item.item_id);
            }

            const entries = Object.entries(byAccount);
            await Promise.all(
                entries.map(([accountId, itemIds]) =>
                    createAnalyzeImageAssetsJob(accountId, itemIds, false, false)
                )
            );

            showToast(t('allFiles.imageAnalysisJobsCreated', { count: entries.length }), 'success');
            setMetadataMenuOpen(false);
        } catch (error) {
            showToast(`${t('allFiles.failedCreateImageAnalysisJob')}: ${error.message}`, 'error');
        } finally {
            setActionLoading(false);
        }
    };

    const executeMapBooks = async () => {
        if (!isBooksLibraryActive) return;
        if (selectedItems.size === 0) return;
        if (!canMapBooks) {
            showToast(t('allFiles.mapBooksAvailability'), 'error');
            return;
        }
        setActionLoading(true);
        try {
            const selected = getSelectedObjects();
            const byAccount = {};
            for (const item of selected) {
                if (!byAccount[item.account_id]) byAccount[item.account_id] = [];
                byAccount[item.account_id].push(item.item_id);
            }

            const entries = Object.entries(byAccount);
            await Promise.all(
                entries.map(([accountId, itemIds]) =>
                    createExtractBookAssetsJob(accountId, itemIds)
                )
            );

            showToast(t('allFiles.bookJobsCreated', { count: entries.length }), 'success');
            setMetadataMenuOpen(false);
        } catch (error) {
            showToast(`${t('allFiles.failedCreateBookJob')}: ${error.message}`, 'error');
        } finally {
            setActionLoading(false);
        }
    };

    const handleDownload = async () => {
        const selectedFiles = getSelectedObjects().filter((item) => item.item_type === 'file');
        for (const file of selectedFiles) {
            try {
                const url = await getDownloadUrl(file.account_id, file.item_id);
                window.open(url, '_blank');
            } catch (error) {
                showToast(`${t('allFiles.failedDownload')} ${file.name}`, 'error');
            }
        }
    };

    const handleUploadToSelectedFolder = async (input) => {
        if (!uploadTargetFolder) return;
        const NativeFile = typeof globalThis !== 'undefined' ? globalThis.File : undefined;
        const files = NativeFile && input instanceof NativeFile
            ? [input]
            : Array.isArray(input)
                ? input.filter(Boolean)
                : Array.from(input || []).filter(Boolean);
        if (files.length === 0) return;

        setUploading(true);
        setUploadProgress(0);
        showToast(t('allFiles.uploadingFiles', { count: files.length }), 'info');

        let failed = 0;
        try {
            for (let index = 0; index < files.length; index += 1) {
                const file = files[index];
                try {
                    await uploadFileBackground(
                        uploadTargetFolder.account_id,
                        uploadTargetFolder.item_id,
                        file,
                        (pct) => {
                            const overall = ((index + (pct / 100)) / files.length) * 100;
                            setUploadProgress(Math.max(0, Math.min(100, Math.round(overall))));
                        }
                    );
                    setUploadProgress(Math.round(((index + 1) / files.length) * 100));
                } catch (error) {
                    failed += 1;
                    console.error(error);
                }
            }

            if (failed > 0) {
                showToast(t('allFiles.uploadFailedCount', { count: failed }), 'error');
            } else {
                showToast(t('allFiles.uploadQueued', { count: files.length }), 'success');
            }

            await invalidateItems();
        } finally {
            setUploading(false);
            setUploadProgress(0);
        }
    };

    const queueExtractZipJobs = async ({ target, deleteSourceAfterExtract }) => {
        if (!canExtractZips || selectedItemsForZipExtraction.length === 0) {
            showToast(t('allFiles.extractZipAvailability'), 'error');
            return;
        }

        setExtractZipSubmitting(true);
        try {
            const results = await Promise.allSettled(
                selectedItemsForZipExtraction.map((item) =>
                    createExtractZipJob(
                        item.account_id,
                        item.item_id,
                        target.account_id,
                        target.folder_id,
                        deleteSourceAfterExtract,
                    )
                )
            );
            const successCount = results.filter((result) => result.status === 'fulfilled').length;
            if (successCount === selectedItemsForZipExtraction.length) {
                showToast(t('allFiles.zipJobsQueued', { count: successCount }), 'success');
                setExtractZipModalOpen(false);
                setSelectedItems(new Set());
                return;
            }
            if (successCount > 0) {
                showToast(
                    t('allFiles.zipJobsQueuedPartial', {
                        success: successCount,
                        total: selectedItemsForZipExtraction.length,
                    }),
                    'warning',
                );
                setExtractZipModalOpen(false);
                setSelectedItems(new Set());
                return;
            }
            showToast(t('allFiles.failedQueueZipJobs'), 'error');
        } catch (error) {
            showToast(`${t('allFiles.failedQueueZipJobs')}: ${error.message}`, 'error');
        } finally {
            setExtractZipSubmitting(false);
        }
    };

    const executeDelete = async () => {
        const selected = getSelectedObjects();
        if (selected.length === 0) return;

        setActionLoading(true);
        try {
            const byAccount = selected.reduce((acc, item) => {
                const key = item.account_id;
                if (!acc[key]) acc[key] = [];
                acc[key].push(item.item_id);
                return acc;
            }, {});

            await Promise.all(
                Object.entries(byAccount).map(([accountId, itemIds]) =>
                    batchDeleteItems(accountId, itemIds)
                )
            );

            showToast(t('allFiles.selectedDeleted'), 'success');
            setDeleteModalOpen(false);
            setSelectedItems(new Set());
            await invalidateItems();
        } catch (error) {
            showToast(error?.response?.data?.detail || t('allFiles.failedDeleteSelected'), 'error');
        } finally {
            setActionLoading(false);
        }
    };

    const openRenameModal = () => {
        if (!singleSelectedItem) return;
        setRenameValue(singleSelectedItem.name || '');
        setRenameModalOpen(true);
    };

    const confirmRenameItem = async () => {
        if (!singleSelectedItem) return;
        const nextName = renameValue.trim();
        if (!nextName) {
            showToast(t('allFiles.nameCannotBeEmpty'), 'error');
            return;
        }
        if (nextName === singleSelectedItem.name) {
            setRenameModalOpen(false);
            return;
        }

        setRenameSaving(true);
        try {
            await updateItem(singleSelectedItem.account_id, singleSelectedItem.item_id, { name: nextName });
            showToast(t('allFiles.renamedSuccessfully'), 'success');
            setRenameModalOpen(false);
            setMetadataMenuOpen(false);
            await invalidateItems();
        } catch (error) {
            showToast(`${t('allFiles.failedRename')}: ${error.message}`, 'error');
        } finally {
            setRenameSaving(false);
        }
    };

    const executeMapLibraryComics = async () => {
        if (!isComicsLibraryActive) return;
        setMapLibraryMode('comics');
        setMapLibraryConfirmOpen(true);
        setAnalyzeLibraryMenuOpen(false);
    };

    const confirmMapLibraryComics = async () => {
        const selectedAccountId = filters.account_id ? String(filters.account_id) : null;
        const accountScope = selectedAccountId ? [selectedAccountId] : null;
        const parsedChunkSize = Number(mapLibraryChunkSize);
        const safeChunkSize = Number.isFinite(parsedChunkSize)
            ? Math.max(1, Math.min(5000, Math.floor(parsedChunkSize)))
            : 1000;

        setMapLibraryLoading(true);
        try {
            const summary = await createExtractLibraryComicAssetsJob(accountScope, safeChunkSize);
            if (!summary?.total_jobs) {
                showToast(t('allFiles.noUnmappedComics'), 'success');
                return;
            }
            showToast(
                selectedAccountId
                    ? t('allFiles.createdComicsJobForAccount', { jobs: summary.total_jobs, items: summary.total_items, chunk: summary.chunk_size })
                    : t('allFiles.createdComicsJobsAllAccounts', { jobs: summary.total_jobs, items: summary.total_items, chunk: summary.chunk_size }),
                'success',
            );
        } catch (error) {
            showToast(`${t('allFiles.failedLibraryComicJob')}: ${error.message}`, 'error');
        } finally {
            setMapLibraryLoading(false);
            setMapLibraryConfirmOpen(false);
        }
    };

    const executeMapLibraryImages = async () => {
        if (!isImagesLibraryActive) return;
        setMapLibraryMode('images');
        setMapLibraryConfirmOpen(true);
        setAnalyzeLibraryMenuOpen(false);
    };

    const executeMapLibraryBooks = async () => {
        if (!isBooksLibraryActive) return;
        setMapLibraryMode('books');
        setMapLibraryConfirmOpen(true);
        setAnalyzeLibraryMenuOpen(false);
    };

    const confirmMapLibraryImages = async () => {
        const selectedAccountId = filters.account_id ? String(filters.account_id) : null;
        const accountScope = selectedAccountId ? [selectedAccountId] : null;
        const parsedChunkSize = Number(mapLibraryChunkSize);
        const safeChunkSize = Number.isFinite(parsedChunkSize)
            ? Math.max(1, Math.min(5000, Math.floor(parsedChunkSize)))
            : 1000;

        setMapLibraryLoading(true);
        try {
            const summary = await createAnalyzeLibraryImageAssetsJob(accountScope, safeChunkSize, false);
            if (!summary?.total_jobs) {
                showToast(t('allFiles.noUnmappedImages'), 'success');
                return;
            }
            showToast(
                selectedAccountId
                    ? t('allFiles.createdImagesJobForAccount', { jobs: summary.total_jobs, items: summary.total_items, chunk: summary.chunk_size })
                    : t('allFiles.createdImagesJobsAllAccounts', { jobs: summary.total_jobs, items: summary.total_items, chunk: summary.chunk_size }),
                'success',
            );
        } catch (error) {
            showToast(`${t('allFiles.failedLibraryImageJob')}: ${error.message}`, 'error');
        } finally {
            setMapLibraryLoading(false);
            setMapLibraryConfirmOpen(false);
        }
    };

    const confirmMapLibraryBooks = async () => {
        const selectedAccountId = filters.account_id ? String(filters.account_id) : null;
        const accountScope = selectedAccountId ? [selectedAccountId] : null;
        const parsedChunkSize = Number(mapLibraryChunkSize);
        const safeChunkSize = Number.isFinite(parsedChunkSize)
            ? Math.max(1, Math.min(5000, Math.floor(parsedChunkSize)))
            : 500;

        setMapLibraryLoading(true);
        try {
            const summary = await createMapLibraryBooksJob(accountScope, safeChunkSize);
            if (!summary?.total_jobs) {
                showToast(t('allFiles.noUnmappedBooks'), 'success');
                return;
            }
            showToast(
                selectedAccountId
                    ? t('allFiles.createdBooksJobForAccount', { jobs: summary.total_jobs, items: summary.total_items, chunk: summary.chunk_size })
                    : t('allFiles.createdBooksJobsAllAccounts', { jobs: summary.total_jobs, items: summary.total_items, chunk: summary.chunk_size }),
                'success',
            );
        } catch (error) {
            showToast(`${t('allFiles.failedLibraryBooksJob')}: ${error.message}`, 'error');
        } finally {
            setMapLibraryLoading(false);
            setMapLibraryConfirmOpen(false);
        }
    };



    const breadcrumbSegments = useMemo(() => {
        if (!pathPrefix) return [];
        const cleaned = pathPrefix.replace(/^\/+/, '');
        const parts = cleaned.split('/').filter(Boolean);
        return parts.map((part, idx) => ({
            label: part,
            path: '/' + parts.slice(0, idx + 1).join('/')
        }));
    }, [pathPrefix]);

    const searchPlaceholders = {
        name: t('allFiles.searchByTitle'),
        path: t('allFiles.searchByPath'),
        both: t('allFiles.searchByTitlePath'),
    };

    const workspaceFilters = useMemo(() => {
        const labels = [];
        if (debouncedSearchTerm) {
            labels.push(t('workspace.filterSearch', { value: debouncedSearchTerm, defaultValue: `Busca: ${debouncedSearchTerm}` }));
        }
        if (pathPrefix) {
            labels.push(t('workspace.filterPath', { value: pathPrefix, defaultValue: `Caminho: ${pathPrefix}` }));
        }
        if (filters.account_id) {
            const accountLabel = accounts.find((account) => account.id === filters.account_id)?.email || filters.account_id;
            labels.push(t('workspace.filterAccount', { value: accountLabel, defaultValue: `Conta: ${accountLabel}` }));
        }
        if (filters.category_id) {
            const categoryLabel = metaCategories.find((category) => category.id === filters.category_id)?.name || filters.category_id;
            labels.push(t('workspace.filterCategory', { value: categoryLabel, defaultValue: `Categoria: ${categoryLabel}` }));
        }
        if (filters.has_metadata === 'true') labels.push(t('workspace.filterMetadataOnly', { defaultValue: 'Com metadata' }));
        if (filters.has_metadata === 'false') labels.push(t('workspace.filterWithoutMetadata', { defaultValue: 'Sem metadata' }));
        return labels;
    }, [accounts, debouncedSearchTerm, filters.account_id, filters.category_id, filters.has_metadata, metaCategories, pathPrefix, t]);

    useWorkspacePage(useMemo(() => ({
        title: activeTab === 'similar' ? t('allFiles.similarFiles') : t('allFiles.fileLibrary'),
        subtitle: activeTab === 'similar'
            ? t('workspace.librarySimilarSubtitle', { defaultValue: 'Priorize duplicados, economia potencial e decisoes em lote.' })
            : pathPrefix
                ? t('workspace.libraryPathSubtitle', { value: pathPrefix, defaultValue: `Explorando o escopo ${pathPrefix} com contexto compartilhado.` })
                : t('workspace.librarySubtitle', { defaultValue: 'Biblioteca central com filtros, selecao e automacoes cruzadas.' }),
        entityType: 'library',
        entityId: activeTab,
        sourceRoute: location.pathname,
        selectedIds: Array.from(selectedItems),
        activeFilters: workspaceFilters,
        metrics: [
            t('allFiles.itemsCount', { count: total }),
            t('workspace.pageMetric', { page, total: totalPages, defaultValue: `Pagina ${page} de ${totalPages}` }),
        ],
        suggestedPrompts: activeTab === 'similar'
            ? [
                t('workspace.aiPrompts.duplicates', { defaultValue: 'Quais grupos de duplicados devo priorizar primeiro?' }),
                t('workspace.aiPrompts.recommend', { defaultValue: 'Sugira as proximas acoes com maior impacto.' }),
            ]
            : [
                t('workspace.aiPrompts.metadataCoverage', { defaultValue: 'Onde a cobertura de metadata esta fraca?' }),
                t('workspace.aiPrompts.summarize', { defaultValue: 'Resuma o contexto atual e destaque riscos.' }),
            ],
    }), [activeTab, location.pathname, page, pathPrefix, selectedItems, t, total, totalPages, workspaceFilters]));

    return (
        <div className="app-page density-compact">
            <div className="mb-4 inline-flex items-center gap-1 rounded-lg border border-border/70 bg-card p-1">
                <button
                    type="button"
                    onClick={() => setActiveTab('library')}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${activeTab === 'library'
                            ? 'bg-primary text-primary-foreground'
                            : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                        }`}
                >
                    {t('allFiles.fileLibrary')}
                </button>
                <button
                    type="button"
                    onClick={() => setActiveTab('similar')}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${activeTab === 'similar'
                            ? 'bg-primary text-primary-foreground'
                            : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                        }`}
                >
                    {t('allFiles.similarFiles')}
                </button>
            </div>

            {activeTab === 'library' ? (
                <>
                    {/* Unified command bar */}
                    <div className="surface-card relative layer-dropdown mb-4 overflow-visible">
                        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={clearPathPrefix}
                                    className={`page-title appearance-none border-0 bg-transparent p-0 hover:text-primary transition-colors ${!pathPrefix ? 'text-foreground' : 'text-muted-foreground'}`}
                                >
                                    {t('allFiles.fileLibrary')}
                                </button>
                                {breadcrumbSegments.map((seg) => (
                                    <Fragment key={seg.path}>
                                        <ChevronRight size={16} className="text-muted-foreground" />
                                        <button
                                            onClick={() => {
                                                setSearchTerm('');
                                                const nextPath = normalizeFolderPath(seg.path);
                                                setCurrentFolderTarget(folderTargetsByPath[nextPath] || null);
                                                setPathPrefix(nextPath);
                                                setPage(1);
                                            }}
                                            className={`page-title hover:text-primary transition-colors ${pathPrefix === seg.path ? 'text-foreground' : 'text-muted-foreground'}`}
                                        >
                                            {seg.label}
                                        </button>
                                    </Fragment>
                                ))}
                                <span className="text-xs text-muted-foreground font-normal bg-muted px-2 py-0.5 rounded-full ml-2">{t('allFiles.itemsCount', { count: total })}</span>
                            </div>

                            <div className="flex items-center gap-2">
                                <select
                                    className="input-shell px-2 py-1.5 text-sm"
                                    value={searchScope}
                                    onChange={(e) => setSearchScope(e.target.value)}
                                >
                                    <option value="both">{t('allFiles.titlePath')}</option>
                                    <option value="name">{t('allFiles.title')}</option>
                                    <option value="path">{t('allFiles.path')}</option>
                                </select>
                                <div className="relative">
                                    <Search className="absolute left-2 top-1.5 text-muted-foreground" size={16} />
                                    <input
                                        type="text"
                                        placeholder={searchPlaceholders[searchScope]}
                                        className="input-shell pl-8 pr-4 py-1.5 text-sm w-64"
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                        onKeyDown={(e) => { if (e.key === 'Enter') { setPage(1); } }}
                                    />
                                </div>
                                <FilterBar onFilter={setFilters} filters={filters} accounts={accounts} categories={metaCategories} />
                                <div className="relative" ref={columnsMenuRef}>
                                    <button
                                        onClick={() => setColumnsMenuOpen((prev) => !prev)}
                                        className="flex items-center gap-2 px-3 py-2 border rounded-md text-sm font-medium hover:bg-accent"
                                        title={t('allFiles.chooseColumns')}
                                    >
                                        <Columns3 size={16} />
                                        {t('allFiles.columnsTitle')}
                                    </button>
                                    {columnsMenuOpen && (
                                        <div className="menu-popover absolute right-0 top-full mt-2 w-56 p-2 layer-popover space-y-1">
                                            {orderedColumns.map((column) => (
                                                <label key={column.id} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-accent cursor-pointer text-sm">
                                                    <input
                                                        type="checkbox"
                                                        checked={columnVisibility[column.id] !== false}
                                                        onChange={(event) => {
                                                            const nextChecked = event.target.checked;
                                                            setColumnVisibility((prev) => {
                                                                const next = { ...prev, [column.id]: nextChecked };
                                                                const visibleCount = Object.values(next).filter(Boolean).length;
                                                                if (visibleCount === 0) {
                                                                    next[column.id] = true;
                                                                }
                                                                return next;
                                                            });
                                                        }}
                                                    />
                                                    <span>{t(`allFiles.columns.${column.id}`)}</span>
                                                </label>
                                            ))}
                                        </div>
                                    )}
                                </div>
                                {(isComicsLibraryActive || isImagesLibraryActive || isBooksLibraryActive) && (
                                    <div className="relative layer-dropdown" ref={analyzeLibraryMenuRef}>
                                        <button
                                            onClick={() => setAnalyzeLibraryMenuOpen((prev) => !prev)}
                                            disabled={mapLibraryLoading}
                                            className="flex items-center gap-2 px-3 py-2 border rounded-md text-sm font-medium hover:bg-accent disabled:opacity-50"
                                            title={t('allFiles.mapAllHelp')}
                                        >
                                            {mapLibraryLoading ? <Loader2 size={16} className="animate-spin" /> : <BookOpen size={16} />}
                                            {t('allFiles.mapAllAs')}
                                            <ChevronDown size={14} className={`transition-transform ${analyzeLibraryMenuOpen ? 'rotate-180' : ''}`} />
                                        </button>
                                        {analyzeLibraryMenuOpen && (
                                            <div className="menu-popover absolute right-0 top-full mt-2 w-52 py-1 layer-popover">
                                                {isComicsLibraryActive && (
                                                    <button
                                                        onClick={executeMapLibraryComics}
                                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2"
                                                        disabled={mapLibraryLoading}
                                                    >
                                                        <BookOpen size={14} />
                                                        {t('allFiles.mapAllComics')}
                                                    </button>
                                                )}
                                                {isImagesLibraryActive && (
                                                    <button
                                                        onClick={executeMapLibraryImages}
                                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2"
                                                        disabled={mapLibraryLoading}
                                                    >
                                                        <ImageIcon size={14} />
                                                        {t('allFiles.mapAllImages')}
                                                    </button>
                                                )}
                                                {isBooksLibraryActive && (
                                                    <button
                                                        onClick={executeMapLibraryBooks}
                                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2"
                                                        disabled={mapLibraryLoading}
                                                    >
                                                        <BookOpen size={14} />
                                                        {t('allFiles.mapAllBooks')}
                                                    </button>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                        <div className="px-4 py-2 flex items-center justify-between gap-2 text-sm">
                            <div className="flex items-center gap-2">
                                <span className="font-medium mr-2 whitespace-nowrap w-24 text-right tabular-nums">{t('allFiles.selectedCount', { count: selectedItems.size })}</span>
                                <div className="h-4 w-px bg-border mx-2" />
                                <button
                                    onClick={handleDownload}
                                    disabled={selectedItems.size === 0}
                                    className="p-2 hover:bg-background rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                    title={t('allFiles.download')}
                                >
                                    <Download size={16} /> <span className="hidden sm:inline">{t('allFiles.download')}</span>
                                </button>
                                <button
                                    onClick={() => setMoveModalOpen(true)}
                                    disabled={selectedItems.size !== 1}
                                    className="p-2 hover:bg-background rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                    title={t('allFiles.move')}
                                >
                                    <ArrowRightLeft size={16} /> <span className="hidden sm:inline">{t('allFiles.move')}</span>
                                </button>
                                <button
                                    onClick={() => fileInputRef.current?.click()}
                                    disabled={!canUploadToFolder || uploading}
                                    className="p-2 hover:bg-background rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                    title={canUploadToFolder ? t('allFiles.upload') : t('allFiles.selectFolderOrOpenFolderToUpload')}
                                >
                                    {uploading ? <Loader2 className="animate-spin" size={16} /> : <UploadCloud size={16} />}
                                    <span className="hidden sm:inline">
                                        {uploading ? t('allFiles.uploadingProgress', { progress: uploadProgress }) : t('allFiles.upload')}
                                    </span>
                                </button>
                                <input
                                    type="file"
                                    ref={fileInputRef}
                                    className="hidden"
                                    multiple
                                    onChange={(event) => {
                                        handleUploadToSelectedFolder(event.target.files);
                                        event.target.value = '';
                                    }}
                                />
                                <button
                                    onClick={() => setExtractZipModalOpen(true)}
                                    disabled={!canExtractZips || extractZipSubmitting}
                                    className="p-2 hover:bg-background rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                    title={canExtractZips ? t('allFiles.extractZip') : t('allFiles.extractZipAvailability')}
                                >
                                    <Archive size={16} />
                                    <span className="hidden sm:inline">{t('allFiles.extractZip')}</span>
                                </button>
                                <div
                                    className={`relative ${selectedItems.size === 0 ? 'pointer-events-none opacity-50' : ''}`}
                                    ref={metadataMenuRef}
                                >
                                    <button
                                        onClick={() => setMetadataMenuOpen(!metadataMenuOpen)}
                                        disabled={selectedItems.size === 0}
                                        className="p-2 hover:bg-background rounded-md flex items-center gap-2 disabled:cursor-not-allowed"
                                        title={t('allFiles.metadataActions')}
                                    >
                                        <Database size={16} />
                                        <span className="hidden sm:inline">{t('allFiles.metadata')}</span>
                                        <ChevronDown size={14} className={`transition-transform ${metadataMenuOpen ? 'rotate-180' : ''}`} />
                                    </button>

                                    {metadataMenuOpen && (
                                        <div className="absolute top-full left-0 w-52 pt-1 layer-dropdown">
                                            <div className="bg-popover border rounded-md shadow-md py-1">
                                                <button
                                                    onClick={() => {
                                                        if (selectedItems.size === 1) {
                                                            setMetadataModalOpen(true);
                                                        } else {
                                                            setBatchModalOpen(true);
                                                        }
                                                        setMetadataMenuOpen(false);
                                                    }}
                                                    disabled={selectedItems.size === 0}
                                                    className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                                >
                                                    <Database size={14} /> {t('allFiles.editMetadata')}
                                                </button>
                                                <button
                                                    onClick={openRenameModal}
                                                    disabled={selectedItems.size !== 1 || actionLoading}
                                                    className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                                >
                                                    <Pencil size={14} /> {t('allFiles.rename')}
                                                </button>
                                                <button
                                                    onClick={() => {
                                                        setRemoveModalOpen(true);
                                                        setMetadataMenuOpen(false);
                                                    }}
                                                    disabled={selectedItems.size === 0}
                                                    className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 text-destructive hover:text-destructive disabled:opacity-50"
                                                >
                                                    <XCircle size={14} /> {t('allFiles.removeMetadata')}
                                                </button>
                                                {(isComicsLibraryActive || isImagesLibraryActive || isBooksLibraryActive) && (
                                                    <>
                                                        <div className="px-4 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                                                            {t('allFiles.analyzeAs')}
                                                        </div>
                                                        {isComicsLibraryActive && (
                                                            <button
                                                                onClick={executeMapComics}
                                                                disabled={!canMapComics || actionLoading}
                                                                className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                                            >
                                                                {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <BookOpen size={14} />}
                                                                {t('allFiles.comics')}
                                                            </button>
                                                        )}
                                                        {isImagesLibraryActive && (
                                                            <button
                                                                onClick={executeAnalyzeImages}
                                                                disabled={!canAnalyzeImages || actionLoading}
                                                                className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                                            >
                                                                {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <ImageIcon size={14} />}
                                                                {t('allFiles.images')}
                                                            </button>
                                                        )}
                                                        {isBooksLibraryActive && (
                                                            <button
                                                                onClick={executeMapBooks}
                                                                disabled={!canMapBooks || actionLoading}
                                                                className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                                            >
                                                                {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <BookOpen size={14} />}
                                                                {t('allFiles.books')}
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
                                    onClick={() => setDeleteModalOpen(true)}
                                    disabled={selectedItems.size === 0}
                                    className="p-2 hover:bg-destructive/10 text-destructive rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                    title={t('allFiles.delete')}
                                >
                                    <Trash2 size={16} /> <span className="hidden sm:inline">{t('allFiles.delete')}</span>
                                </button>

                            </div>

                            {/* Pagination */}
                            <div className="flex items-center gap-2">
                                <label className="flex items-center gap-2 text-muted-foreground">
                                    <span>{t('allFiles.resultsPerPage')}</span>
                                    <select
                                        value={pageSize}
                                        onChange={(event) => {
                                            setPageSize(Number(event.target.value));
                                            setPage(1);
                                        }}
                                        className="rounded-md border bg-background px-2 py-1 text-sm text-foreground"
                                    >
                                        {PAGE_SIZE_OPTIONS.map((option) => (
                                            <option key={option} value={option}>{option}</option>
                                        ))}
                                    </select>
                                </label>
                                <span className="text-muted-foreground">{t('allFiles.pageOf', { page, total: totalPages })}</span>
                                <div className="flex gap-1">
                                    <button
                                        disabled={page <= 1}
                                        onClick={() => setPage(p => p - 1)}
                                        className="p-1 hover:bg-background rounded disabled:opacity-50"
                                    >
                                        <ChevronLeft size={16} />
                                    </button>
                                    <button
                                        disabled={page >= totalPages}
                                        onClick={() => setPage(p => p + 1)}
                                        className="p-1 hover:bg-background rounded disabled:opacity-50"
                                    >
                                        <ChevronRight size={16} />
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Path Prefix Breadcrumb */}
                    {pathPrefix && (
                        <div className="mb-4 flex items-center gap-2 rounded-sm border border-border/90 bg-muted/20 px-4 py-2 text-sm">
                            <FolderOpen size={16} className="text-primary" />
                            <span className="text-muted-foreground">{t('allFiles.showingFilesIn')}</span>
                            <span className="font-medium text-foreground">{pathPrefix}</span>
                            <button onClick={clearPathPrefix} className="ml-auto flex items-center gap-1 text-muted-foreground hover:text-foreground text-xs">
                                <X size={14} /> {t('allFiles.clear')}
                            </button>
                        </div>
                    )}

                    {/* Content */}
                    <main className="flex-1 overflow-auto">
                        {loading ? (
                            <div className="flex justify-center p-12">
                                <Loader2 className="animate-spin text-primary" size={32} />
                            </div>
                        ) : items.length === 0 ? (
                            <div className="empty-state">
                                <div className="empty-state-icon">
                                    <Folder size={26} />
                                </div>
                                <div className="empty-state-title">{t('allFiles.noItemsFound')}</div>
                                <p className="empty-state-text">{t('allFiles.noItemsHelp')}</p>
                            </div>
                        ) : (
                            <div className="surface-card overflow-hidden select-none">
                                <div className="overflow-x-auto">
                                    {/* Header */}
                                    <div
                                        className="sticky top-0 z-20 gap-4 border-b border-border/70 bg-muted/95 p-3 text-xs font-medium uppercase tracking-wider text-muted-foreground shadow-sm backdrop-blur supports-[backdrop-filter]:bg-muted/80 items-center"
                                        style={{ display: 'grid', gridTemplateColumns: dataGridTemplate, minWidth: `${tableMinWidth}px` }}
                                    >
                                        <div className="flex justify-center">
                                            <button onClick={toggleSelectAll}>
                                                {selectedItems.size === items.length && items.length > 0 ? <CheckSquare size={16} /> : <Square size={16} />}
                                            </button>
                                        </div>
                                        <div />
                                        {visibleColumns.map((column) => (
                                            <div
                                                key={column.id}
                                                draggable
                                                onDragStart={() => setDraggingColumnId(column.id)}
                                                onDragEnd={() => setDraggingColumnId(null)}
                                                onDragOver={(event) => event.preventDefault()}
                                                onDrop={() => handleColumnDrop(column.id)}
                                                className={`relative flex min-w-0 items-center gap-1 ${getColumnAlignmentClasses(column.align)}`}
                                            >
                                                <div className="pointer-events-none absolute bottom-0 right-0 top-0 w-px bg-border/80" />
                                                <button
                                                    type="button"
                                                    className={`inline-flex min-w-0 items-center gap-1 hover:text-foreground ${column.sortKey ? '' : 'cursor-default'}`}
                                                    onClick={() => column.sortKey && handleSort(column.sortKey)}
                                                >
                                                    <GripVertical size={12} className="opacity-45" />
                                                    {t(`allFiles.columns.${column.id}`)}
                                                    {column.sortKey ? renderSortIcon(column.sortKey) : null}
                                                </button>
                                                <div
                                                    className="absolute right-[-8px] top-0 h-full w-3 cursor-col-resize"
                                                    onMouseDown={(event) => beginResize(event, column)}
                                                />
                                            </div>
                                        ))}
                                    </div>

                                    {/* List */}
                                    <div className="divide-y">
                                        {items.map((item, index) => {
                                            const isFolder = item.item_type === 'folder';
                                            const isSelected = selectedItems.has(item.id);
                                            return (
                                                <div
                                                    key={item.id}
                                                    className={`group gap-4 p-3 items-center hover:bg-accent/35 transition-colors ${isSelected ? 'bg-muted/45' : ''}`}
                                                    style={{ display: 'grid', gridTemplateColumns: dataGridTemplate, minWidth: `${tableMinWidth}px` }}
                                                    onClick={(e) => toggleSelection(item.id, index, !e.altKey, e.shiftKey)}
                                                >
                                                    <div className="flex justify-center">
                                                        <div className={`cursor-pointer ${isSelected ? 'text-primary' : 'text-muted-foreground/50'}`}>
                                                            {isSelected ? <CheckSquare size={16} /> : <Square size={16} />}
                                                        </div>
                                                    </div>
                                                    <div className="flex justify-center text-muted-foreground">
                                                        {isFolder ? (
                                                            <button
                                                                onClick={(e) => { e.stopPropagation(); handleFolderClick(item); }}
                                                                className="hover:scale-110 transition-transform"
                                                                title={t('allFiles.showFolderContents')}
                                                            >
                                                                <Folder className="text-primary fill-primary/15" size={20} />
                                                            </button>
                                                        ) : (
                                                            <File className="text-gray-400" size={20} />
                                                        )}
                                                    </div>
                                                    {visibleColumns.map((column) => (
                                                        <div
                                                            key={column.id}
                                                            className={`relative flex min-w-0 items-center ${getColumnAlignmentClasses(column.align)}`}
                                                        >
                                                            <div className="pointer-events-none absolute bottom-[-12px] right-0 top-[-12px] w-px bg-border/50" />
                                                            {renderColumnCell(item, column)}
                                                        </div>
                                                    ))}
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            </div>
                        )}
                    </main>

                    {batchModalOpen && (
                        <Suspense fallback={null}>
                            <BatchMetadataModal
                                isOpen={batchModalOpen}
                                onClose={() => setBatchModalOpen(false)}
                                selectedItems={getSelectedObjects()}
                                showToast={showToast}
                                onSuccess={() => {
                                    void invalidateItems();
                                    setSelectedItems(new Set());
                                }}
                            />
                        </Suspense>
                    )}

                    {metadataModalOpen && (
                        <Suspense fallback={null}>
                            <MetadataModal
                                isOpen={metadataModalOpen}
                                onClose={() => setMetadataModalOpen(false)}
                                item={singleSelectedItem}
                                accountId={singleSelectedItem?.account_id}
                                onSuccess={() => {
                                    void invalidateItems();
                                }}
                            />
                        </Suspense>
                    )}

                    {removeModalOpen && (
                        <Suspense fallback={null}>
                            <RemoveMetadataModal
                                isOpen={removeModalOpen}
                                onClose={() => setRemoveModalOpen(false)}
                                selectedItems={getSelectedObjects()}
                                showToast={showToast}
                                onSuccess={() => {
                                    void invalidateItems();
                                    setSelectedItems(new Set());
                                }}
                            />
                        </Suspense>
                    )}

                    <Modal
                        isOpen={deleteModalOpen}
                        onClose={() => !actionLoading && setDeleteModalOpen(false)}
                        title={t('allFiles.deleteTitle', { count: selectedItems.size })}
                        maxWidthClass="max-w-md"
                    >
                        <div className="space-y-4">
                            <p className="text-sm text-muted-foreground">
                                {t('allFiles.deleteConfirm')}
                            </p>
                            <div className="flex justify-end gap-2">
                                <button
                                    type="button"
                                    onClick={() => setDeleteModalOpen(false)}
                                    disabled={actionLoading}
                                    className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent disabled:opacity-50"
                                >
                                    {t('common.cancel')}
                                </button>
                                <button
                                    type="button"
                                    onClick={executeDelete}
                                    disabled={actionLoading}
                                    className="px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50 flex items-center gap-2"
                                >
                                    {actionLoading && <Loader2 className="animate-spin" size={14} />}
                                    {t('allFiles.delete')}
                                </button>
                            </div>
                        </div>
                    </Modal>

                    {moveModalOpen && (
                        <Suspense fallback={null}>
                            <MoveModal
                                isOpen={moveModalOpen}
                                onClose={() => setMoveModalOpen(false)}
                                item={moveTargetItem}
                                sourceAccountId={moveTargetItem?.account_id}
                                onSuccess={() => {
                                    setMoveModalOpen(false);
                                    setSelectedItems(new Set());
                                    void invalidateItems();
                                }}
                            />
                        </Suspense>
                    )}

                    {extractZipModalOpen && (
                        <Suspense fallback={null}>
                            <ExtractZipModal
                                isOpen={extractZipModalOpen}
                                onClose={() => !extractZipSubmitting && setExtractZipModalOpen(false)}
                                onConfirm={queueExtractZipJobs}
                                selectedItems={selectedItemsForZipExtraction}
                                initialTarget={extractZipInitialTarget}
                                submitting={extractZipSubmitting}
                            />
                        </Suspense>
                    )}

                    <Modal
                        isOpen={renameModalOpen}
                        onClose={() => !renameSaving && setRenameModalOpen(false)}
                        title={t('allFiles.renameItem')}
                        maxWidthClass="max-w-md"
                    >
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">{t('allFiles.newName')}</label>
                                <input
                                    type="text"
                                    value={renameValue}
                                    onChange={(e) => setRenameValue(e.target.value)}
                                    disabled={renameSaving}
                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                    autoFocus
                                />
                            </div>
                            <div className="flex justify-end gap-2">
                                <button
                                    type="button"
                                    onClick={() => setRenameModalOpen(false)}
                                    disabled={renameSaving}
                                    className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent disabled:opacity-50"
                                >
                                    {t('common.cancel')}
                                </button>
                                <button
                                    type="button"
                                    onClick={confirmRenameItem}
                                    disabled={renameSaving}
                                    className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                                >
                                    {renameSaving && <Loader2 className="animate-spin" size={14} />}
                                    {t('allFiles.rename')}
                                </button>
                            </div>
                        </div>
                    </Modal>

                    <Modal
                        isOpen={mapLibraryConfirmOpen}
                        onClose={() => !mapLibraryLoading && setMapLibraryConfirmOpen(false)}
                        title={
                            mapLibraryMode === 'images'
                                ? t('allFiles.mapAllImages')
                                : mapLibraryMode === 'books'
                                    ? t('allFiles.mapAllBooks')
                                    : t('allFiles.mapAllComics')
                        }
                        maxWidthClass="max-w-lg"
                    >
                        <p className="text-sm text-muted-foreground mb-4">
                            {mapLibraryMode === 'images'
                                ? (
                                    filters.account_id
                                        ? t('allFiles.mapAllImagesSelectedAccount')
                                        : t('allFiles.mapAllImagesAllAccounts')
                                )
                                : mapLibraryMode === 'books'
                                    ? (
                                        filters.account_id
                                            ? t('allFiles.mapAllBooksSelectedAccount')
                                            : t('allFiles.mapAllBooksAllAccounts')
                                    )
                                    : (
                                        filters.account_id
                                            ? t('allFiles.mapAllComicsSelectedAccount')
                                            : t('allFiles.mapAllComicsAllAccounts')
                                    )}
                        </p>
                        <div className="mb-4">
                            <label className="block text-sm font-medium mb-1">{t('allFiles.chunkSizePerJob')}</label>
                            <input
                                type="number"
                                min={1}
                                max={5000}
                                step={1}
                                value={mapLibraryChunkSize}
                                onChange={(e) => setMapLibraryChunkSize(e.target.value)}
                                disabled={mapLibraryLoading}
                                className="w-full border rounded-md p-2 text-sm bg-background"
                            />
                            <p className="mt-1 text-xs text-muted-foreground">
                                {t('allFiles.chunkSizeHelp')}
                            </p>
                        </div>
                        <div className="flex justify-end gap-2">
                            <button
                                type="button"
                                onClick={() => setMapLibraryConfirmOpen(false)}
                                disabled={mapLibraryLoading}
                                className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent disabled:opacity-50"
                            >
                                {t('common.cancel')}
                            </button>
                            <button
                                type="button"
                                onClick={
                                    mapLibraryMode === 'images'
                                        ? confirmMapLibraryImages
                                        : mapLibraryMode === 'books'
                                            ? confirmMapLibraryBooks
                                            : confirmMapLibraryComics
                                }
                                disabled={mapLibraryLoading}
                                className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                            >
                                {mapLibraryLoading && <Loader2 className="animate-spin" size={14} />}
                                {t('common.confirm')}
                            </button>
                        </div>
                    </Modal>

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
                </>
            ) : (
                <Suspense fallback={<div className="surface-card p-4 text-sm text-muted-foreground">{t('common.loading')}</div>}>
                    <SimilarFilesReportTab accounts={accounts} />
                </Suspense>
            )}
        </div>
    );
}

