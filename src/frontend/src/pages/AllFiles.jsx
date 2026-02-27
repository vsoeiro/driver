import { Fragment, useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { itemsService } from '../services/items';
import { metadataService } from '../services/metadata';
import { accountsService } from '../services/accounts';
import { jobsService } from '../services/jobs';
import { driveService } from '../services/drive';
import { useToast } from '../contexts/ToastContext';
import {
    getSelectOptions,
    parseTagsInput,
    READ_ONLY_COMIC_FIELD_KEYS,
    sortAttributesForCategory,
    tagsToInputValue,
} from '../utils/metadata';
import {
    File, Folder, FolderOpen, Search, Filter, Database, CheckSquare, Square,
    Loader2, ChevronLeft, ChevronRight, ArrowUpDown, ArrowUp, ArrowDown, X, Trash2, ChevronDown, BookOpen, Pencil, Columns3, GripVertical,
    Download, ArrowRightLeft, XCircle, UploadCloud
} from 'lucide-react';
import Modal from '../components/Modal';
import ProviderIcon from '../components/ProviderIcon';
import MetadataModal from '../components/MetadataModal';
import MoveModal from '../components/MoveModal';
import SimilarFilesReportTab from '../components/SimilarFilesReportTab';
import ImagePreviewModal from '../components/ImagePreviewModal';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { isPreviewableFileName } from '../utils/imagePreview';
import { formatDateTime } from '../utils/dateTime';

const COMIC_MAPPABLE_EXTS = new Set(['cbz', 'zip', 'cbw', 'pdf', 'epub', 'cbr', 'rar', 'cb7', '7z', 'cbt', 'tar']);
const ALL_FILES_COLUMNS_STORAGE_KEY = 'driver-all-files-columns-v1';
const ALL_FILES_COLUMNS = [
    { id: 'name', label: 'Name', width: 280, minWidth: 180, sortKey: 'name' },
    { id: 'account', label: 'Account', width: 190, minWidth: 150, sortKey: null },
    { id: 'size', label: 'Size', width: 110, minWidth: 90, sortKey: 'size', align: 'right' },
    { id: 'category', label: 'Category', width: 110, minWidth: 90, sortKey: null, align: 'right' },
    { id: 'modified', label: 'Modified', width: 160, minWidth: 130, sortKey: 'modified_at', align: 'right' },
    { id: 'path', label: 'Path', width: 280, minWidth: 150, sortKey: null, align: 'right' },
];

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
        <div className="relative z-[90]">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className={`flex items-center gap-2 px-3 py-2 border rounded-md text-sm font-medium ${isOpen ? 'bg-accent text-accent-foreground' : 'hover:bg-accent'}`}
            >
                <Filter size={16} /> {t('allFiles.filters')}
            </button>

            {isOpen && (
                <div className="absolute right-0 top-full mt-2 w-72 bg-popover border rounded-md shadow-lg p-4 z-[120] space-y-4">
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

// Batch Metadata Modal
const BatchMetadataModal = ({ isOpen, onClose, selectedItems, onSuccess, showToast }) => {
    const { t } = useTranslation();
    const [categories, setCategories] = useState([]);
    const [selectedCategory, setSelectedCategory] = useState('');
    const [attributeValues, setAttributeValues] = useState({});
    const [applyRecursive, setApplyRecursive] = useState(false);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);

    const hasFolders = selectedItems.some(i => i.item_type === 'folder');

    const prefillFromSelection = useCallback(() => {
        const itemsWithMeta = selectedItems.filter(i => i.metadata);

        if (itemsWithMeta.length === 0) {
            setSelectedCategory('');
            setAttributeValues({});
            return;
        }

        const firstCatId = itemsWithMeta[0].metadata.category_id;
        const allSameCategory = itemsWithMeta.every(
            i => i.metadata.category_id === firstCatId
        );

        if (!allSameCategory) {
            setSelectedCategory('');
            setAttributeValues({});
            return;
        }

        setSelectedCategory(firstCatId);

        if (itemsWithMeta.length === 1) {
            setAttributeValues(itemsWithMeta[0].metadata.values || {});
            return;
        }

        const commonValues = {};
        const firstValues = itemsWithMeta[0].metadata.values || {};
        for (const [key, val] of Object.entries(firstValues)) {
            const allMatch = itemsWithMeta.every(
                i => (i.metadata.values || {})[key] === val
            );
            if (allMatch) {
                commonValues[key] = val;
            }
        }
        setAttributeValues(commonValues);
    }, [selectedItems]);

    const loadCategories = useCallback(async () => {
        setLoading(true);
        try {
            const data = await metadataService.listCategories();
            setCategories(data);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (isOpen) {
            loadCategories();
            setApplyRecursive(false);
        }
    }, [isOpen, loadCategories]);

    useEffect(() => {
        if (!isOpen || categories.length === 0 || selectedItems.length === 0) return;
        prefillFromSelection();
    }, [isOpen, categories, selectedItems, prefillFromSelection]);

    const handleSave = async () => {
        if (!selectedCategory) return;
        setSaving(true);
        try {
            const promises = [];
            const groupedByAccount = {};

            for (const item of selectedItems) {
                if (!groupedByAccount[item.account_id]) {
                    groupedByAccount[item.account_id] = [];
                }
                groupedByAccount[item.account_id].push(item);
            }

            let recursiveJobs = 0;
            for (const [accountId, accountItems] of Object.entries(groupedByAccount)) {
                const folders = accountItems.filter(i => i.item_type === 'folder');
                const files = accountItems.filter(i => i.item_type !== 'folder');

                if (files.length > 0) {
                    promises.push(
                        itemsService.batchUpdateMetadata(
                            accountId,
                            files.map(i => i.item_id),
                            selectedCategory,
                            attributeValues
                        )
                    );
                }

                if (applyRecursive && folders.length > 0) {
                    recursiveJobs += folders.length;
                    for (const folder of folders) {
                        promises.push(
                            jobsService.applyMetadataRecursive(
                                accountId,
                                folder.path,
                                selectedCategory,
                                attributeValues
                            )
                        );
                    }
                }
            }

            await Promise.all(promises);

            if (applyRecursive && recursiveJobs > 0) {
                showToast(t('allFiles.recursiveJobsCreated', { count: recursiveJobs }), 'success');
            } else {
                showToast(t('allFiles.metadataUpdated'), 'success');
            }

            onSuccess();
            onClose();
        } catch (error) {
            showToast(`${t('allFiles.failedUpdateMetadata')}: ${error.message}`, 'error');
        } finally {
            setSaving(false);
        }
    };

    const currentCategory = categories.find(c => c.id === selectedCategory);
    const orderedAttributes = sortAttributesForCategory(currentCategory);

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={t('allFiles.editMetadataTitle', { count: selectedItems.length })}>
            <div className="space-y-4">
                {loading ? (
                    <div className="flex justify-center"><Loader2 className="animate-spin" /></div>
                ) : (
                    <>
                        <div>
                            <label className="block text-sm font-medium mb-1">{t('allFiles.category')}</label>
                            <select
                                className="w-full border rounded-md p-2 bg-background"
                                value={selectedCategory}
                                onChange={(e) => {
                                    setSelectedCategory(e.target.value);
                                    setAttributeValues({});
                                }}
                            >
                                <option value="">{t('allFiles.selectCategory')}</option>
                                {categories.map(c => (
                                    <option key={c.id} value={c.id}>{c.name}</option>
                                ))}
                            </select>
                        </div>

                        {currentCategory && (
                            <div className="space-y-3 border p-3 rounded-md bg-muted/20">
                                {orderedAttributes.map(attr => (
                                    <div key={attr.id}>
                                        {(() => {
                                            const isReadOnlyComputed = currentCategory?.plugin_key === 'comics_core'
                                                && READ_ONLY_COMIC_FIELD_KEYS.has(attr.plugin_field_key);
                                            return (
                                                <>
                                        <label className="block text-xs font-medium mb-1 uppercase text-muted-foreground">{attr.name} {attr.is_required && '*'}</label>
                                        {attr.data_type === 'select' ? (
                                            <select
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={attributeValues[attr.id] ?? ''}
                                                disabled={isReadOnlyComputed}
                                                onChange={e => setAttributeValues(prev => ({ ...prev, [attr.id]: e.target.value }))}
                                            >
                                                <option value="">{t('allFiles.select')}</option>
                                                {getSelectOptions(attr.options).map(opt => (
                                                    <option key={opt} value={opt}>{opt}</option>
                                                ))}
                                            </select>
                                        ) : attr.data_type === 'boolean' ? (
                                            <select
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={attributeValues[attr.id] ?? ''}
                                                disabled={isReadOnlyComputed}
                                                onChange={e => setAttributeValues(prev => ({ ...prev, [attr.id]: e.target.value === 'true' }))}
                                            >
                                                <option value="">{t('allFiles.select')}</option>
                                                <option value="true">{t('common.yes')}</option>
                                                <option value="false">{t('common.no')}</option>
                                            </select>
                                        ) : attr.data_type === 'tags' ? (
                                            <input
                                                type="text"
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={tagsToInputValue(attributeValues[attr.id] ?? [])}
                                                placeholder={t('allFiles.tagsPlaceholder')}
                                                disabled={isReadOnlyComputed}
                                                onChange={e => setAttributeValues(prev => ({ ...prev, [attr.id]: parseTagsInput(e.target.value) }))}
                                            />
                                        ) : (
                                            <input
                                                type={attr.data_type === 'number' ? 'number' : attr.data_type === 'date' ? 'date' : 'text'}
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={attributeValues[attr.id] ?? ''}
                                                disabled={isReadOnlyComputed}
                                                onChange={e => setAttributeValues(prev => ({ ...prev, [attr.id]: e.target.value }))}
                                            />
                                        )}
                                        {isReadOnlyComputed && (
                                            <div className="mt-1 text-xs text-muted-foreground">
                                                {t('allFiles.mappedReadonly')}
                                            </div>
                                        )}
                                                </>
                                            );
                                        })()}
                                    </div>
                                ))}
                            </div>
                        )}

                        {hasFolders && (
                            <label className="flex items-center gap-2 text-sm border p-3 rounded-md bg-amber-50 text-amber-800">
                                <input
                                    type="checkbox"
                                    checked={applyRecursive}
                                    onChange={(e) => setApplyRecursive(e.target.checked)}
                                />
                                {t('allFiles.applyRecursive')}
                            </label>
                        )}
                    </>
                )}

                <div className="flex justify-end gap-2 pt-2">
                    <button onClick={onClose} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">{t('common.cancel')}</button>
                    <button
                        onClick={handleSave}
                        disabled={saving || !selectedCategory}
                        className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                    >
                        {saving && <Loader2 className="animate-spin" size={14} />}
                        {t('allFiles.saveChanges')}
                    </button>
                </div>
            </div>
        </Modal>
    );
};


// Remove Metadata Modal
const RemoveMetadataModal = ({ isOpen, onClose, selectedItems, onSuccess, showToast }) => {
    const { t } = useTranslation();
    const [removing, setRemoving] = useState(false);

    const folders = selectedItems.filter(i => i.item_type === 'folder');
    const filesWithMeta = selectedItems.filter(i => i.item_type !== 'folder' && i.metadata);
    const foldersWithMeta = folders.filter(i => i.metadata);
    const hasAnything = filesWithMeta.length > 0 || folders.length > 0;

    const handleRemove = async () => {
        setRemoving(true);
        try {
            const promises = [];

            const directDeleteItems = [...filesWithMeta, ...foldersWithMeta];
            if (directDeleteItems.length > 0) {
                const byAccount = {};
                for (const item of directDeleteItems) {
                    if (!byAccount[item.account_id]) byAccount[item.account_id] = [];
                    byAccount[item.account_id].push(item.item_id);
                }
                for (const [accountId, itemIds] of Object.entries(byAccount)) {
                    promises.push(metadataService.batchDeleteMetadata(accountId, itemIds));
                }
            }

            for (const folder of folders) {
                promises.push(
                    jobsService.removeMetadataRecursive(folder.account_id, folder.path)
                );
            }

            await Promise.all(promises);

            const parts = [];
            if (directDeleteItems.length > 0) parts.push(t('allFiles.itemsCleared', { count: directDeleteItems.length }));
            if (folders.length > 0) parts.push(t('allFiles.foldersQueued', { count: folders.length }));
            showToast(parts.join(', ') + '.', 'success');

            onSuccess();
            onClose();
        } catch (error) {
            showToast(`${t('allFiles.failedRemoveMetadata')}: ${error.message}`, 'error');
        } finally {
            setRemoving(false);
        }
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={t('allFiles.removeMetadataTitle', { count: selectedItems.length })}>
            <div className="space-y-4">
                {!hasAnything ? (
                    <p className="text-sm text-muted-foreground">{t('allFiles.noMetadataToRemove')}</p>
                ) : (
                    <>
                        {filesWithMeta.length > 0 && (
                            <div>
                                <p className="text-sm font-medium mb-2">{t('allFiles.filesCount', { count: filesWithMeta.length })}</p>
                                <div className="border rounded-md divide-y max-h-40 overflow-y-auto">
                                    {filesWithMeta.map(item => (
                                        <div key={item.id} className="flex items-center gap-2 px-3 py-1.5 text-sm">
                                            <File size={14} className="text-gray-400 shrink-0" />
                                            <span className="truncate">{item.name}</span>
                                            <span className="ml-auto text-xs text-muted-foreground shrink-0">
                                                {item.metadata?.category_name}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {folders.length > 0 && (
                            <div>
                                <p className="text-sm font-medium mb-2">{t('allFiles.foldersRecursiveTitle', { count: folders.length })}</p>
                                <div className="border rounded-md divide-y max-h-40 overflow-y-auto">
                                    {folders.map(item => (
                                        <div key={item.id} className="flex items-center gap-2 px-3 py-1.5 text-sm">
                                            <Folder size={14} className="text-blue-500 shrink-0" />
                                            <span className="truncate">{item.name}</span>
                                            <span className="ml-auto text-xs text-muted-foreground shrink-0">{t('allFiles.plusAllContents')}</span>
                                        </div>
                                    ))}
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    {t('allFiles.foldersRecursiveHelp')}
                                </p>
                            </div>
                        )}
                    </>
                )}

                <div className="flex justify-end gap-2 pt-2">
                    <button onClick={onClose} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">{t('common.cancel')}</button>
                    {hasAnything && (
                        <button
                            onClick={handleRemove}
                            disabled={removing}
                            className="px-4 py-2 text-sm font-medium bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 flex items-center gap-2"
                        >
                            {removing && <Loader2 className="animate-spin" size={14} />}
                            {t('allFiles.confirmRemoval')}
                        </button>
                    )}
                </div>
            </div>
        </Modal>
    );
};


export default function AllFiles() {
    const { t, i18n } = useTranslation();
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);
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
    const [isComicsLibraryActive, setIsComicsLibraryActive] = useState(false);

    const [batchModalOpen, setBatchModalOpen] = useState(false);
    const [metadataModalOpen, setMetadataModalOpen] = useState(false);
    const [removeModalOpen, setRemoveModalOpen] = useState(false);
    const [deleteModalOpen, setDeleteModalOpen] = useState(false);
    const [moveModalOpen, setMoveModalOpen] = useState(false);
    const [metadataMenuOpen, setMetadataMenuOpen] = useState(false);
    const [actionLoading, setActionLoading] = useState(false);
    const [mapLibraryLoading, setMapLibraryLoading] = useState(false);
    const [mapLibraryConfirmOpen, setMapLibraryConfirmOpen] = useState(false);
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
    const [columnsMenuOpen, setColumnsMenuOpen] = useState(false);
    const columnsMenuRef = useRef(null);
    const resizeStateRef = useRef(null);
    const [draggingColumnId, setDraggingColumnId] = useState(null);
    const [columnOrder, setColumnOrder] = useState(() => ALL_FILES_COLUMNS.map((col) => col.id));
    const [columnVisibility, setColumnVisibility] = useState(() =>
        ALL_FILES_COLUMNS.reduce((acc, col) => ({ ...acc, [col.id]: true }), {})
    );
    const [columnWidths, setColumnWidths] = useState(() =>
        ALL_FILES_COLUMNS.reduce((acc, col) => ({ ...acc, [col.id]: col.width }), {})
    );

    const { showToast } = useToast();

    const { data: accounts = [] } = useQuery({
        queryKey: ['accounts'],
        queryFn: accountsService.getAccounts,
        staleTime: 60000,
    });
    const { data: metaCategories = [] } = useQuery({
        queryKey: ['metadata-categories'],
        queryFn: metadataService.listCategories,
        staleTime: 30000,
    });
    const { data: metadataLibraries = [] } = useQuery({
        queryKey: ['metadata-libraries'],
        queryFn: metadataService.listMetadataLibraries,
        staleTime: 30000,
    });

    useEffect(() => {
        const comicsLibrary = (metadataLibraries || []).find((library) => library.key === 'comics_core');
        setIsComicsLibraryActive(Boolean(comicsLibrary?.is_active));
    }, [metadataLibraries]);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (metadataMenuRef.current && !metadataMenuRef.current.contains(event.target)) {
                setMetadataMenuOpen(false);
            }
            if (columnsMenuRef.current && !columnsMenuRef.current.contains(event.target)) {
                setColumnsMenuOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    useEffect(() => {
        try {
            const raw = window.localStorage.getItem(ALL_FILES_COLUMNS_STORAGE_KEY);
            if (!raw) return;
            const parsed = JSON.parse(raw);
            const validIds = new Set(ALL_FILES_COLUMNS.map((col) => col.id));
            const nextOrder = Array.isArray(parsed.order)
                ? parsed.order.filter((id) => validIds.has(id))
                : [];
            const mergedOrder = [
                ...nextOrder,
                ...ALL_FILES_COLUMNS.map((col) => col.id).filter((id) => !nextOrder.includes(id)),
            ];
            setColumnOrder(mergedOrder);
            if (parsed.visibility && typeof parsed.visibility === 'object') {
                setColumnVisibility((prev) => {
                    const next = { ...prev };
                    ALL_FILES_COLUMNS.forEach((col) => {
                        if (Object.prototype.hasOwnProperty.call(parsed.visibility, col.id)) {
                            next[col.id] = Boolean(parsed.visibility[col.id]);
                        }
                    });
                    return next;
                });
            }
            if (parsed.widths && typeof parsed.widths === 'object') {
                setColumnWidths((prev) => {
                    const next = { ...prev };
                    ALL_FILES_COLUMNS.forEach((col) => {
                        const candidate = Number(parsed.widths[col.id]);
                        if (Number.isFinite(candidate)) {
                            next[col.id] = Math.max(col.minWidth, candidate);
                        }
                    });
                    return next;
                });
            }
        } catch {
            // Ignore malformed preferences
        }
    }, []);

    useEffect(() => {
        const payload = {
            order: columnOrder,
            visibility: columnVisibility,
            widths: columnWidths,
        };
        window.localStorage.setItem(ALL_FILES_COLUMNS_STORAGE_KEY, JSON.stringify(payload));
    }, [columnOrder, columnVisibility, columnWidths]);

    const fetchItems = useCallback(async (overridePage) => {
        setLoading(true);
        try {
            const effectivePage = overridePage ?? page;
            const isSearching = debouncedSearchTerm.trim().length > 0;
            const params = {
                page: effectivePage,
                page_size: 50,
                sort_by: sort.by,
                sort_order: sort.order,
                q: debouncedSearchTerm,
                search_fields: searchScope,
                path_prefix: pathPrefix,
                direct_children_only: !!pathPrefix && !isSearching,
                ...filters
            };
            const data = await itemsService.listItems(params);
            setItems(data.items);
            setTotal(data.total);
            setTotalPages(data.total_pages);
        } catch (error) {
            console.error("Failed to fetch items:", error);
        } finally {
            setLoading(false);
        }
    }, [page, debouncedSearchTerm, sort.by, sort.order, searchScope, pathPrefix, filters]);

    useEffect(() => {
        fetchItems();
    }, [fetchItems]);

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

    const getSelectedObjects = () => {
        return items.filter(i => selectedItems.has(i.id));
    };

    const singleSelectedItem = useMemo(() => {
        if (selectedItems.size !== 1) return null;
        const selectedId = Array.from(selectedItems)[0];
        return items.find((i) => i.id === selectedId) || null;
    }, [selectedItems, items]);
    const moveTargetItem = singleSelectedItem
        ? { ...singleSelectedItem, id: singleSelectedItem.item_id }
        : null;
    const selectedFolderTarget = singleSelectedItem?.item_type === 'folder'
        ? singleSelectedItem
        : null;
    const contextualFolderTarget = pathPrefix && currentFolderTarget?.path === pathPrefix
        ? currentFolderTarget
        : null;
    const uploadTargetFolder = selectedFolderTarget || contextualFolderTarget;
    const canUploadToFolder = Boolean(uploadTargetFolder?.account_id && uploadTargetFolder?.item_id);

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
        const dynamic = visibleColumns.reduce(
            (sum, col) => sum + Math.max(col.minWidth, columnWidths[col.id] ?? col.width),
            0
        );
        return base + dynamic;
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
                return <div className="text-right text-sm text-muted-foreground tabular-nums">{formatSize(item.size ?? 0)}</div>;
            case 'category':
                return (
                    <div className="text-right text-sm text-muted-foreground truncate">
                        {item.metadata
                            ? (
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800" title={item.metadata.category_name}>
                                    {item.metadata.category_name || 'N/A'}
                                </span>
                            )
                            : '-'}
                    </div>
                );
            case 'modified':
                return <div className="text-right text-sm text-muted-foreground tabular-nums">{formatDate(item.modified_at)}</div>;
            case 'path':
                return <div className="text-right text-xs text-muted-foreground truncate" title={item.path}>{item.path}</div>;
            default:
                return null;
        }
    };

    const handleFolderClick = (item) => {
        const folderPath = item.path || `/${item.name}`;
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
                    jobsService.createExtractComicAssetsJob(accountId, itemIds)
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

    const handleDownload = async () => {
        const selectedFiles = getSelectedObjects().filter((item) => item.item_type === 'file');
        for (const file of selectedFiles) {
            try {
                const url = await driveService.getDownloadUrl(file.account_id, file.item_id);
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
                    await jobsService.uploadFileBackground(
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

            await fetchItems();
        } finally {
            setUploading(false);
            setUploadProgress(0);
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
                    driveService.batchDeleteItems(accountId, itemIds)
                )
            );

            showToast(t('allFiles.selectedDeleted'), 'success');
            setDeleteModalOpen(false);
            setSelectedItems(new Set());
            fetchItems();
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
            await driveService.updateItem(singleSelectedItem.account_id, singleSelectedItem.item_id, { name: nextName });
            showToast(t('allFiles.renamedSuccessfully'), 'success');
            setRenameModalOpen(false);
            setMetadataMenuOpen(false);
            await fetchItems();
        } catch (error) {
            showToast(`${t('allFiles.failedRename')}: ${error.message}`, 'error');
        } finally {
            setRenameSaving(false);
        }
    };

    const executeMapLibraryComics = async () => {
        if (!isComicsLibraryActive) return;
        setMapLibraryConfirmOpen(true);
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
            const summary = await jobsService.createExtractLibraryComicAssetsJob(accountScope, safeChunkSize);
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

    return (
        <div className="app-page">
            <div className="mb-4 inline-flex items-center gap-1 rounded-lg border border-border/70 bg-card p-1">
                <button
                    type="button"
                    onClick={() => setActiveTab('library')}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                        activeTab === 'library'
                            ? 'bg-primary text-primary-foreground'
                            : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                    }`}
                >
                    {t('allFiles.fileLibrary')}
                </button>
                <button
                    type="button"
                    onClick={() => setActiveTab('similar')}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                        activeTab === 'similar'
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
            <div className="surface-card relative z-[80] mb-4 overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
                <div className="flex items-center gap-2">
                    <button
                        onClick={clearPathPrefix}
                        className={`text-lg font-semibold hover:text-primary transition-colors ${!pathPrefix ? 'text-foreground' : 'text-muted-foreground'}`}
                    >
                        {t('allFiles.fileLibrary')}
                    </button>
                    {breadcrumbSegments.map((seg) => (
                        <Fragment key={seg.path}>
                            <ChevronRight size={16} className="text-muted-foreground" />
                            <button
                                onClick={() => {
                                    setSearchTerm('');
                                    setCurrentFolderTarget(folderTargetsByPath[seg.path] || null);
                                    setPathPrefix(seg.path);
                                    setPage(1);
                                }}
                                className={`text-lg font-semibold hover:text-primary transition-colors ${pathPrefix === seg.path ? 'text-foreground' : 'text-muted-foreground'}`}
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
                            <div className="absolute right-0 top-full mt-2 w-56 bg-popover border rounded-md shadow-lg p-2 z-[120] space-y-1">
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
                    {isComicsLibraryActive && (
                        <button
                            onClick={executeMapLibraryComics}
                            disabled={mapLibraryLoading}
                            className="flex items-center gap-2 px-3 py-2 border rounded-md text-sm font-medium hover:bg-accent disabled:opacity-50"
                            title={t('allFiles.mapAllComicsHelp')}
                        >
                            {mapLibraryLoading ? <Loader2 size={16} className="animate-spin" /> : <BookOpen size={16} />}
                            {t('allFiles.mapAllComics')}
                        </button>
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
                            <div className="absolute top-full left-0 w-52 pt-1 z-[90]">
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
                                    {isComicsLibraryActive && (
                                        <button
                                            onClick={executeMapComics}
                                            disabled={!canMapComics || actionLoading}
                                            className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                        >
                                            {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <BookOpen size={14} />}
                                            {t('allFiles.mapComics')}
                                        </button>
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
                <div className="mb-4 rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-2 flex items-center gap-2 text-sm">
                    <FolderOpen size={16} className="text-blue-500" />
                    <span className="text-muted-foreground">{t('allFiles.showingFilesIn')}</span>
                    <span className="font-medium text-blue-700">{pathPrefix}</span>
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
                                className="gap-4 p-3 border-b border-border/70 bg-muted/45 text-xs font-medium text-muted-foreground uppercase tracking-wider items-center sticky top-0 z-10"
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
                                        onDragOver={(event) => event.preventDefault()}
                                        onDrop={() => handleColumnDrop(column.id)}
                                        className={`relative flex items-center gap-1 ${column.align === 'right' ? 'justify-end text-right' : ''}`}
                                    >
                                        <button
                                            type="button"
                                            className={`inline-flex items-center gap-1 hover:text-foreground ${column.sortKey ? '' : 'cursor-default'}`}
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
                                                        <Folder className="text-blue-500 fill-blue-500/20" size={20} />
                                                    </button>
                                                ) : (
                                                    <File className="text-gray-400" size={20} />
                                                )}
                                            </div>
                                            {visibleColumns.map((column) => (
                                                <div key={column.id}>
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

            <BatchMetadataModal
                isOpen={batchModalOpen}
                onClose={() => setBatchModalOpen(false)}
                selectedItems={getSelectedObjects()}
                showToast={showToast}
                onSuccess={() => {
                    fetchItems();
                    setSelectedItems(new Set());
                }}
            />

            <MetadataModal
                isOpen={metadataModalOpen}
                onClose={() => setMetadataModalOpen(false)}
                item={singleSelectedItem}
                accountId={singleSelectedItem?.account_id}
                onSuccess={() => {
                    fetchItems();
                }}
            />

            <RemoveMetadataModal
                isOpen={removeModalOpen}
                onClose={() => setRemoveModalOpen(false)}
                selectedItems={getSelectedObjects()}
                showToast={showToast}
                onSuccess={() => {
                    fetchItems();
                    setSelectedItems(new Set());
                }}
            />

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

            <MoveModal
                isOpen={moveModalOpen}
                onClose={() => setMoveModalOpen(false)}
                item={moveTargetItem}
                sourceAccountId={moveTargetItem?.account_id}
                onSuccess={() => {
                    setMoveModalOpen(false);
                    setSelectedItems(new Set());
                    fetchItems();
                }}
            />

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
                title={t('allFiles.mapAllComics')}
                maxWidthClass="max-w-lg"
            >
                <p className="text-sm text-muted-foreground mb-4">
                    {filters.account_id
                        ? t('allFiles.mapAllComicsSelectedAccount')
                        : t('allFiles.mapAllComicsAllAccounts')}
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
                        onClick={confirmMapLibraryComics}
                        disabled={mapLibraryLoading}
                        className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                    >
                        {mapLibraryLoading && <Loader2 className="animate-spin" size={14} />}
                        {t('common.confirm')}
                    </button>
                </div>
            </Modal>

            <ImagePreviewModal
                isOpen={Boolean(imagePreviewItem)}
                onClose={() => setImagePreviewItem(null)}
                accountId={imagePreviewItem?.accountId}
                itemId={imagePreviewItem?.itemId}
                filename={imagePreviewItem?.filename}
            />
                </>
            ) : (
                <SimilarFilesReportTab accounts={accounts} />
            )}
        </div>
    );
}

