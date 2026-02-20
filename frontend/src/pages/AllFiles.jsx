import { Fragment, useState, useEffect, useMemo, useCallback, useRef } from 'react';
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
    Loader2, ChevronLeft, ChevronRight, ArrowUpDown, ArrowUp, ArrowDown, X, Trash2, ChevronDown, BookOpen, Pencil,
    Download, ArrowRightLeft, XCircle
} from 'lucide-react';
import Modal from '../components/Modal';
import ProviderIcon from '../components/ProviderIcon';
import MetadataModal from '../components/MetadataModal';
import MoveModal from '../components/MoveModal';

const COMIC_MAPPABLE_EXTS = new Set(['cbz', 'zip', 'cbw', 'pdf', 'epub', 'cbr', 'rar', 'cb7', '7z', 'cbt', 'tar']);

// Filter Component
const FilterBar = ({ onFilter, filters, accounts, categories }) => {
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
        <div className="relative">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className={`flex items-center gap-2 px-3 py-2 border rounded-md text-sm font-medium ${isOpen ? 'bg-accent text-accent-foreground' : 'hover:bg-accent'}`}
            >
                <Filter size={16} /> Filters
            </button>

            {isOpen && (
                <div className="absolute right-0 top-full mt-2 w-72 bg-popover border rounded-md shadow-lg p-4 z-50 space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">Account</label>
                        <select
                            className="w-full border rounded-md p-2 text-sm bg-background"
                            value={localFilters.account_id || ''}
                            onChange={(e) => handleChange('account_id', e.target.value)}
                        >
                            <option value="">All Accounts</option>
                            {accounts?.map(acc => (
                                <option key={acc.id} value={acc.id}>{acc.email || acc.display_name}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">Category</label>
                        <select
                            className="w-full border rounded-md p-2 text-sm bg-background"
                            value={localFilters.category_id || ''}
                            onChange={(e) => handleChange('category_id', e.target.value)}
                        >
                            <option value="">All Categories</option>
                            {categories?.map(cat => (
                                <option key={cat.id} value={cat.id}>{cat.name}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">Has Metadata</label>
                        <select
                            className="w-full border rounded-md p-2 text-sm bg-background"
                            value={localFilters.has_metadata ?? ''}
                            onChange={(e) => handleChange('has_metadata', e.target.value)}
                        >
                            <option value="">All</option>
                            <option value="true">With Metadata</option>
                            <option value="false">Without Metadata</option>
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">Type</label>
                        <select
                            className="w-full border rounded-md p-2 text-sm bg-background"
                            value={localFilters.item_type || ''}
                            onChange={(e) => handleChange('item_type', e.target.value)}
                        >
                            <option value="">All</option>
                            <option value="file">Files</option>
                            <option value="folder">Folders</option>
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">Extensions (comma separated)</label>
                        <input
                            type="text"
                            className="w-full border rounded-md p-2 text-sm bg-background"
                            placeholder="pdf, jpg, docx"
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
                        <label className="block text-sm font-medium mb-1">Size (Bytes)</label>
                        <div className="flex gap-2">
                            <input
                                type="number"
                                placeholder="Min"
                                className="w-full border rounded-md p-2 text-sm bg-background"
                                value={localFilters.size_min || ''}
                                onChange={(e) => handleChange('size_min', e.target.value)}
                            />
                            <input
                                type="number"
                                placeholder="Max"
                                className="w-full border rounded-md p-2 text-sm bg-background"
                                value={localFilters.size_max || ''}
                                onChange={(e) => handleChange('size_max', e.target.value)}
                            />
                        </div>
                    </div>

                    <div className="flex justify-between pt-2">
                        <button onClick={clearFilters} className="text-sm text-muted-foreground hover:text-foreground">Clear</button>
                        <button onClick={applyFilters} className="bg-primary text-primary-foreground px-3 py-1.5 rounded-md text-sm font-medium">Apply</button>
                    </div>
                </div>
            )}
        </div>
    );
};

// Batch Metadata Modal
const BatchMetadataModal = ({ isOpen, onClose, selectedItems, onSuccess, showToast }) => {
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
                showToast(`${recursiveJobs} recursive job(s) created for folder contents.`, 'success');
            } else {
                showToast('Metadata updated successfully.', 'success');
            }

            onSuccess();
            onClose();
        } catch (error) {
            showToast('Failed to update metadata: ' + error.message, 'error');
        } finally {
            setSaving(false);
        }
    };

    const currentCategory = categories.find(c => c.id === selectedCategory);
    const orderedAttributes = sortAttributesForCategory(currentCategory);

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={`Edit Metadata for ${selectedItems.length} item${selectedItems.length > 1 ? 's' : ''}`}>
            <div className="space-y-4">
                {loading ? (
                    <div className="flex justify-center"><Loader2 className="animate-spin" /></div>
                ) : (
                    <>
                        <div>
                            <label className="block text-sm font-medium mb-1">Category</label>
                            <select
                                className="w-full border rounded-md p-2 bg-background"
                                value={selectedCategory}
                                onChange={(e) => {
                                    setSelectedCategory(e.target.value);
                                    setAttributeValues({});
                                }}
                            >
                                <option value="">Select Category...</option>
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
                                            const isReadOnlyComputed = currentCategory?.plugin_key === 'comicrack_core'
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
                                                <option value="">Select...</option>
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
                                                <option value="">Select...</option>
                                                <option value="true">Yes</option>
                                                <option value="false">No</option>
                                            </select>
                                        ) : attr.data_type === 'tags' ? (
                                            <input
                                                type="text"
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={tagsToInputValue(attributeValues[attr.id] ?? [])}
                                                placeholder="tag1, tag2, tag3"
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
                                                Mapped field (read-only)
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
                                Apply recursively to folder contents (background job)
                            </label>
                        )}
                    </>
                )}

                <div className="flex justify-end gap-2 pt-2">
                    <button onClick={onClose} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">Cancel</button>
                    <button
                        onClick={handleSave}
                        disabled={saving || !selectedCategory}
                        className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                    >
                        {saving && <Loader2 className="animate-spin" size={14} />}
                        Save Changes
                    </button>
                </div>
            </div>
        </Modal>
    );
};


// Remove Metadata Modal
const RemoveMetadataModal = ({ isOpen, onClose, selectedItems, onSuccess, showToast }) => {
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
            if (directDeleteItems.length > 0) parts.push(`${directDeleteItems.length} item(s) cleared`);
            if (folders.length > 0) parts.push(`${folders.length} folder(s) queued for recursive removal`);
            showToast(parts.join(', ') + '.', 'success');

            onSuccess();
            onClose();
        } catch (error) {
            showToast('Failed to remove metadata: ' + error.message, 'error');
        } finally {
            setRemoving(false);
        }
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={`Remove Metadata from ${selectedItems.length} item${selectedItems.length > 1 ? 's' : ''}`}>
            <div className="space-y-4">
                {!hasAnything ? (
                    <p className="text-sm text-muted-foreground">None of the selected items have metadata to remove.</p>
                ) : (
                    <>
                        {filesWithMeta.length > 0 && (
                            <div>
                                <p className="text-sm font-medium mb-2">Files ({filesWithMeta.length})</p>
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
                                <p className="text-sm font-medium mb-2">Folders — recursive removal ({folders.length})</p>
                                <div className="border rounded-md divide-y max-h-40 overflow-y-auto">
                                    {folders.map(item => (
                                        <div key={item.id} className="flex items-center gap-2 px-3 py-1.5 text-sm">
                                            <Folder size={14} className="text-blue-500 shrink-0" />
                                            <span className="truncate">{item.name}</span>
                                            <span className="ml-auto text-xs text-muted-foreground shrink-0">+ all contents</span>
                                        </div>
                                    ))}
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    A background job will remove metadata from the folder and all items inside it.
                                </p>
                            </div>
                        )}
                    </>
                )}

                <div className="flex justify-end gap-2 pt-2">
                    <button onClick={onClose} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">Cancel</button>
                    {hasAnything && (
                        <button
                            onClick={handleRemove}
                            disabled={removing}
                            className="px-4 py-2 text-sm font-medium bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 flex items-center gap-2"
                        >
                            {removing && <Loader2 className="animate-spin" size={14} />}
                            Confirm Removal
                        </button>
                    )}
                </div>
            </div>
        </Modal>
    );
};


export default function AllFiles() {
    const [items, setItems] = useState([]);
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);

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
    const [searchScope, setSearchScope] = useState('both');
    const [pathPrefix, setPathPrefix] = useState('');
    const [selectedItems, setSelectedItems] = useState(new Set());
    const [lastSelectedIndex, setLastSelectedIndex] = useState(null);
    const [metaCategories, setMetaCategories] = useState([]);

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
    const metadataMenuRef = useRef(null);

    const { showToast } = useToast();

    useEffect(() => {
        accountsService.getAccounts().then(setAccounts).catch(console.error);
        metadataService.listCategories().then(setMetaCategories).catch(console.error);
    }, []);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (metadataMenuRef.current && !metadataMenuRef.current.contains(event.target)) {
                setMetadataMenuOpen(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const fetchItems = useCallback(async (overridePage) => {
        setLoading(true);
        try {
            const effectivePage = overridePage ?? page;
            const isSearching = searchTerm.trim().length > 0;
            const params = {
                page: effectivePage,
                page_size: 50,
                sort_by: sort.by,
                sort_order: sort.order,
                q: searchTerm,
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
    }, [page, searchTerm, sort.by, sort.order, searchScope, pathPrefix, filters]);

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
        if (!dateString) return '-';
        return new Date(dateString).toLocaleDateString('en-GB', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
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

    const getAccountName = (accountId) => {
        const acc = accounts.find(a => a.id === accountId);
        return acc ? acc.email : (accountId ? accountId.slice(0, 8) : '-');
    };

    const getAccountById = (accountId) => accounts.find((a) => a.id === accountId);

    const handleFolderClick = (item) => {
        const folderPath = item.path || `/${item.name}`;
        setSearchTerm('');
        setPathPrefix(folderPath);
        setPage(1);
    };

    const clearPathPrefix = () => {
        setSearchTerm('');
        setPathPrefix('');
        setPage(1);
    };

    const executeMapComics = async () => {
        if (selectedItems.size === 0) return;
        if (!canMapComics) {
            showToast('Map Comics is only available for folders or files with supported extensions (CBZ, ZIP, CBW, PDF, EPUB, CBR, RAR, CB7, 7Z, CBT, TAR).', 'error');
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

            showToast(`Comic mapping job(s) created for ${entries.length} account(s).`, 'success');
            setMetadataMenuOpen(false);
        } catch (error) {
            showToast(`Failed to create comic mapping job: ${error.message}`, 'error');
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
                showToast(`Failed to download ${file.name}`, 'error');
            }
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

            showToast('Selected items deleted successfully.', 'success');
            setDeleteModalOpen(false);
            setSelectedItems(new Set());
            fetchItems();
        } catch (error) {
            showToast(error?.response?.data?.detail || 'Failed to delete selected items', 'error');
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
            showToast('Name cannot be empty.', 'error');
            return;
        }
        if (nextName === singleSelectedItem.name) {
            setRenameModalOpen(false);
            return;
        }

        setRenameSaving(true);
        try {
            await driveService.updateItem(singleSelectedItem.account_id, singleSelectedItem.item_id, { name: nextName });
            showToast('Item renamed successfully.', 'success');
            setRenameModalOpen(false);
            setMetadataMenuOpen(false);
            await fetchItems();
        } catch (error) {
            showToast(`Failed to rename item: ${error.message}`, 'error');
        } finally {
            setRenameSaving(false);
        }
    };

    const executeMapLibraryComics = async () => {
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
                showToast('No unmapped .cbr/.cbz files found in current scope.', 'success');
                return;
            }
            showToast(
                selectedAccountId
                    ? `Created ${summary.total_jobs} comic mapping jobs (${summary.total_items} files, chunk=${summary.chunk_size}) for selected account.`
                    : `Created ${summary.total_jobs} comic mapping jobs (${summary.total_items} files, chunk=${summary.chunk_size}) for all accounts.`,
                'success',
            );
        } catch (error) {
            showToast(`Failed to create library comic mapping job: ${error.message}`, 'error');
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
        name: 'Search by title...',
        path: 'Search by path...',
        both: 'Search by title or path...'
    };

    return (
        <div className="flex flex-col h-screen">
            {/* Header */}
            <div className="p-4 border-b flex items-center justify-between bg-background">
                <div className="flex items-center gap-2">
                    <button
                        onClick={clearPathPrefix}
                        className={`text-lg font-semibold hover:text-primary transition-colors ${!pathPrefix ? 'text-foreground' : 'text-muted-foreground'}`}
                    >
                        File Library
                    </button>
                    {breadcrumbSegments.map((seg) => (
                        <Fragment key={seg.path}>
                            <ChevronRight size={16} className="text-muted-foreground" />
                            <button
                                onClick={() => { setSearchTerm(''); setPathPrefix(seg.path); setPage(1); }}
                                className={`text-lg font-semibold hover:text-primary transition-colors ${pathPrefix === seg.path ? 'text-foreground' : 'text-muted-foreground'}`}
                            >
                                {seg.label}
                            </button>
                        </Fragment>
                    ))}
                    <span className="text-xs text-muted-foreground font-normal bg-muted px-2 py-0.5 rounded-full ml-2">{total} items</span>
                </div>

                <div className="flex items-center gap-2">
                    <select
                        className="border rounded-md px-2 py-1.5 text-sm bg-background"
                        value={searchScope}
                        onChange={(e) => setSearchScope(e.target.value)}
                    >
                        <option value="both">Title + Path</option>
                        <option value="name">Title</option>
                        <option value="path">Path</option>
                    </select>
                    <div className="relative">
                        <Search className="absolute left-2 top-1.5 text-muted-foreground" size={16} />
                        <input
                            type="text"
                            placeholder={searchPlaceholders[searchScope]}
                            className="pl-8 pr-4 py-1.5 text-sm border rounded-md w-64 focus:outline-none focus:ring-1 focus:ring-primary"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') { setPage(1); fetchItems(1); } }}
                        />
                    </div>
                    <FilterBar onFilter={setFilters} filters={filters} accounts={accounts} categories={metaCategories} />
                    <button
                        onClick={executeMapLibraryComics}
                        disabled={mapLibraryLoading}
                        className="flex items-center gap-2 px-3 py-2 border rounded-md text-sm font-medium hover:bg-accent disabled:opacity-50"
                        title="Map all synced .cbr/.cbz items as comics"
                    >
                        {mapLibraryLoading ? <Loader2 size={16} className="animate-spin" /> : <BookOpen size={16} />}
                        Map All Comics
                    </button>
                </div>
            </div>

            {/* Toolbar */}
            <div className="bg-muted/50 border-b px-4 py-2 flex items-center justify-between gap-2 text-sm h-14">
                <div className="flex items-center gap-2">
                    <span className="font-medium mr-2 whitespace-nowrap w-24 text-right tabular-nums">{selectedItems.size} selected</span>
                    <div className="h-4 w-px bg-border mx-2" />
                    <button
                        onClick={handleDownload}
                        disabled={selectedItems.size === 0}
                        className="p-2 hover:bg-background rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Download"
                    >
                        <Download size={16} /> <span className="hidden sm:inline">Download</span>
                    </button>
                    <button
                        onClick={() => setMoveModalOpen(true)}
                        disabled={selectedItems.size !== 1}
                        className="p-2 hover:bg-background rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Move"
                    >
                        <ArrowRightLeft size={16} /> <span className="hidden sm:inline">Move</span>
                    </button>
                    <div
                        className={`relative ${selectedItems.size === 0 ? 'pointer-events-none opacity-50' : ''}`}
                        ref={metadataMenuRef}
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
                            <div className="absolute top-full left-0 w-52 pt-1 z-50">
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
                                        <Database size={14} /> Edit Metadata
                                    </button>
                                    <button
                                        onClick={openRenameModal}
                                        disabled={selectedItems.size !== 1 || actionLoading}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                    >
                                        <Pencil size={14} /> Rename
                                    </button>
                                    <button
                                        onClick={() => {
                                            setRemoveModalOpen(true);
                                            setMetadataMenuOpen(false);
                                        }}
                                        disabled={selectedItems.size === 0}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 text-destructive hover:text-destructive disabled:opacity-50"
                                    >
                                        <XCircle size={14} /> Remove Metadata
                                    </button>
                                    <button
                                        onClick={executeMapComics}
                                        disabled={!canMapComics || actionLoading}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                    >
                                        {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <BookOpen size={14} />}
                                        Map Comics
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                    <div className="h-4 w-px bg-border mx-1" />
                    <button
                        onClick={() => setDeleteModalOpen(true)}
                        disabled={selectedItems.size === 0}
                        className="p-2 hover:bg-destructive/10 text-destructive rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Delete"
                    >
                        <Trash2 size={16} /> <span className="hidden sm:inline">Delete</span>
                    </button>

                </div>

                {/* Pagination */}
                <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">Page {page} of {totalPages}</span>
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

            {/* Path Prefix Breadcrumb */}
            {pathPrefix && (
                <div className="bg-blue-50 border-b px-4 py-2 flex items-center gap-2 text-sm">
                    <FolderOpen size={16} className="text-blue-500" />
                    <span className="text-muted-foreground">Showing files in:</span>
                    <span className="font-medium text-blue-700">{pathPrefix}</span>
                    <button onClick={clearPathPrefix} className="ml-auto flex items-center gap-1 text-muted-foreground hover:text-foreground text-xs">
                        <X size={14} /> Clear
                    </button>
                </div>
            )}

            {/* Content */}
            <main className="flex-1 overflow-auto p-4">
                {loading ? (
                    <div className="flex justify-center p-12">
                        <Loader2 className="animate-spin text-primary" size={32} />
                    </div>
                ) : items.length === 0 ? (
                    <div className="text-center p-12 text-muted-foreground">
                        No items found.
                    </div>
                ) : (
                    <div className="border rounded-lg overflow-hidden bg-card select-none">
                        {/* Header */}
                        <div className="grid grid-cols-[40px_40px_2fr_170px_80px_80px_140px_minmax(150px,1fr)] gap-4 p-3 border-b bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider items-center sticky top-0">
                            <div className="flex justify-center">
                                <button onClick={toggleSelectAll}>
                                    {selectedItems.size === items.length && items.length > 0 ? <CheckSquare size={16} /> : <Square size={16} />}
                                </button>
                            </div>
                            <div></div>
                            <div className="cursor-pointer flex items-center gap-1 hover:text-foreground" onClick={() => handleSort('name')}>
                                Name {renderSortIcon('name')}
                            </div>
                            <div className="flex items-center gap-1 hover:text-foreground">
                                Account
                            </div>
                            <div className="cursor-pointer flex items-center gap-1 hover:text-foreground justify-end" onClick={() => handleSort('size')}>
                                Size {renderSortIcon('size')}
                            </div>
                            <div className="flex items-center gap-1 hover:text-foreground justify-end">
                                Category
                            </div>
                            <div className="cursor-pointer flex items-center gap-1 hover:text-foreground justify-end" onClick={() => handleSort('modified_at')}>
                                Modified {renderSortIcon('modified_at')}
                            </div>
                            <div className="text-right">Path</div>
                        </div>

                        {/* List */}
                        <div className="divide-y">
                            {items.map((item, index) => {
                                const isFolder = item.item_type === 'folder';
                                const isSelected = selectedItems.has(item.id);
                                return (
                                    <div
                                        key={item.id}
                                        className={`group grid grid-cols-[40px_40px_2fr_170px_80px_80px_140px_minmax(150px,1fr)] gap-4 p-3 items-center hover:bg-muted/30 transition-colors ${isSelected ? 'bg-muted/40' : ''}`}
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
                                                    title="Show files inside this folder"
                                                >
                                                    <Folder className="text-blue-500 fill-blue-500/20" size={20} />
                                                </button>
                                            ) : (
                                                <File className="text-gray-400" size={20} />
                                            )}
                                        </div>
                                        <div className="min-w-0 truncate font-medium">
                                            {item.name}
                                        </div>
                                        <div className="flex items-center gap-1 text-sm text-foreground">
                                            <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                                                <ProviderIcon provider={getAccountById(item.account_id)?.provider} className="w-3 h-3" />
                                            </div>
                                            <span className="truncate" title={getAccountName(item.account_id)}>
                                                {getAccountName(item.account_id)}
                                            </span>
                                        </div>
                                        <div className="text-right text-sm text-muted-foreground tabular-nums">
                                            {formatSize(item.size ?? 0)}
                                        </div>
                                        <div className="text-right text-sm text-muted-foreground truncate">
                                            {item.metadata ? <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800" title={item.metadata.category_name}>{item.metadata.category_name || 'N/A'}</span> : '-'}
                                        </div>
                                        <div className="text-right text-sm text-muted-foreground tabular-nums">
                                            {formatDate(item.modified_at)}
                                        </div>
                                        <div className="text-right text-xs text-muted-foreground truncate" title={item.path}>
                                            {item.path}
                                        </div>
                                    </div>
                                );
                            })}
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
                title={`Delete ${selectedItems.size} item(s)?`}
                maxWidthClass="max-w-md"
            >
                <div className="space-y-4">
                    <p className="text-sm text-muted-foreground">
                        Are you sure you want to delete the selected items? This action cannot be undone.
                    </p>
                    <div className="flex justify-end gap-2">
                        <button
                            type="button"
                            onClick={() => setDeleteModalOpen(false)}
                            disabled={actionLoading}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent disabled:opacity-50"
                        >
                            Cancel
                        </button>
                        <button
                            type="button"
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
                title="Rename Item"
                maxWidthClass="max-w-md"
            >
                <div className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">New name</label>
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
                            Cancel
                        </button>
                        <button
                            type="button"
                            onClick={confirmRenameItem}
                            disabled={renameSaving}
                            className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                        >
                            {renameSaving && <Loader2 className="animate-spin" size={14} />}
                            Rename
                        </button>
                    </div>
                </div>
            </Modal>

            <Modal
                isOpen={mapLibraryConfirmOpen}
                onClose={() => !mapLibraryLoading && setMapLibraryConfirmOpen(false)}
                title="Map All Comics"
                maxWidthClass="max-w-lg"
            >
                <p className="text-sm text-muted-foreground mb-4">
                    {filters.account_id
                        ? 'Create a job to map all synced .cbr/.cbz files for the selected account filter?'
                        : 'Create a job to map all synced .cbr/.cbz files across all accounts?'}
                </p>
                <div className="mb-4">
                    <label className="block text-sm font-medium mb-1">Chunk size per job</label>
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
                        Lower values create more jobs with fewer files each.
                    </p>
                </div>
                <div className="flex justify-end gap-2">
                    <button
                        type="button"
                        onClick={() => setMapLibraryConfirmOpen(false)}
                        disabled={mapLibraryLoading}
                        className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent disabled:opacity-50"
                    >
                        Cancel
                    </button>
                    <button
                        type="button"
                        onClick={confirmMapLibraryComics}
                        disabled={mapLibraryLoading}
                        className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                    >
                        {mapLibraryLoading && <Loader2 className="animate-spin" size={14} />}
                        Confirm
                    </button>
                </div>
            </Modal>
        </div>
    );
}
