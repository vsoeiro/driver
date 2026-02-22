import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { metadataService } from '../services/metadata';
import { itemsService } from '../services/items';
import { accountsService } from '../services/accounts';
import { driveService } from '../services/drive';
import { getCategoryLibraryView } from '../metadataLibraries/categoryViews';
import { buildCoverCacheKey, getCachedCoverUrl, setCachedCoverUrl } from '../utils/coverCache';
import {
    getSelectOptions,
    parseTagsInput,
    READ_ONLY_COMIC_FIELD_KEYS,
    sortAttributesForCategory,
    tagsToInputValue,
} from '../utils/metadata';
import {
    Plus, Trash2, ChevronRight, ChevronDown, ChevronLeft,
    Database, Loader2, Tag, Hash, ArrowLeft,
    File, Folder, ArrowUpDown, ArrowUp, ArrowDown,
    CheckSquare, Square, Eye, Search, Filter, User, Pencil, BookOpen, Power,
    Download, ArrowRightLeft, XCircle, Check, X
} from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import Modal from '../components/Modal';
import BatchMetadataModal from '../components/BatchMetadataModal';
import RemoveMetadataModal from '../components/RemoveMetadataModal';
import MetadataModal from '../components/MetadataModal';
import MoveModal from '../components/MoveModal';
import MetadataLayoutBuilderModal from '../components/MetadataLayoutBuilderModal';

const ITEMS_PER_PAGE = 50;
const BASE_SORT_OPTIONS = [
    { value: 'modified_at', label: 'Order: Modified' },
    { value: 'name', label: 'Order: Name' },
    { value: 'size', label: 'Order: Size' },
    { value: 'created_at', label: 'Order: Created' },
];


// -- Category Items Table --
const CategoryItemsTable = ({ category, onBack }) => {
    const { showToast } = useToast();
    const [items, setItems] = useState([]);
    const [seriesRows, setSeriesRows] = useState([]);
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [sort, setSort] = useState({ by: 'modified_at', order: 'desc' });
    const [selectedItems, setSelectedItems] = useState(new Set());
    const [lastSelectedIndex, setLastSelectedIndex] = useState(null);
    const [batchModalOpen, setBatchModalOpen] = useState(false);
    const [metadataModalOpen, setMetadataModalOpen] = useState(false);
    const [removeModalOpen, setRemoveModalOpen] = useState(false);
    const [deleteModalOpen, setDeleteModalOpen] = useState(false);
    const [moveModalOpen, setMoveModalOpen] = useState(false);
    const [metadataMenuOpen, setMetadataMenuOpen] = useState(false);
    const metadataMenuRef = useRef(null);
    const [renameModalOpen, setRenameModalOpen] = useState(false);
    const [renameValue, setRenameValue] = useState('');
    const [renameSaving, setRenameSaving] = useState(false);
    const [actionLoading, setActionLoading] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [appliedSearchTerm, setAppliedSearchTerm] = useState('');
    const [searchScope, setSearchScope] = useState('both');
    const [viewMode, setViewMode] = useState('table');
    const [coverUrlsByItemId, setCoverUrlsByItemId] = useState({});
    const [editingCell, setEditingCell] = useState(null);
    const [editingValue, setEditingValue] = useState('');
    const [savingCellKey, setSavingCellKey] = useState(null);
    const [filters, setFilters] = useState({
        account_id: '',
        item_type: '',
        attributes: {}
    });
    const libraryView = getCategoryLibraryView(category);
    const supportsGallery = !!libraryView?.modes?.includes('gallery');
    const supportsSeriesTracker = !!libraryView?.modes?.includes('series_tracker');
    const metadataSortOptions = useMemo(
        () =>
            (category.attributes || []).map((attr) => ({
                value: `metadata:${attr.id}`,
                label: `Order: ${attr.name}`,
                attributeId: attr.id,
                dataType: attr.data_type,
            })),
        [category.attributes]
    );
    const sortOptions = useMemo(
        () => [...BASE_SORT_OPTIONS, ...metadataSortOptions],
        [metadataSortOptions]
    );
    const selectedMetadataSort = useMemo(() => {
        if (!sort.by?.startsWith('metadata:')) return null;
        return metadataSortOptions.find((option) => option.value === sort.by) || null;
    }, [sort.by, metadataSortOptions]);

    useEffect(() => {
        accountsService.getAccounts().then(setAccounts).catch(console.error);
    }, []);

    useEffect(() => {
        function handleClickOutside(event) {
            if (metadataMenuRef.current && !metadataMenuRef.current.contains(event.target)) {
                setMetadataMenuOpen(false);
            }
        }
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    useEffect(() => {
        if (sort.by?.startsWith('metadata:') && !selectedMetadataSort) {
            setSort((prev) => ({ ...prev, by: 'modified_at' }));
        }
    }, [sort.by, selectedMetadataSort]);

    const CategoryFilterBar = ({ onFilter, currentFilters }) => {
        const [localFilters, setLocalFilters] = useState(currentFilters);
        const [isOpen, setIsOpen] = useState(false);
        const filterableAttributes = (category.attributes || []).filter(
            (attr) => !attr.is_read_only && !READ_ONLY_COMIC_FIELD_KEYS.has(attr.plugin_field_key)
        );

        useEffect(() => {
            setLocalFilters(currentFilters);
        }, [currentFilters]);

        const handleChange = (key, value) => {
            setLocalFilters(prev => ({ ...prev, [key]: value }));
        };

        const handleAttributeChange = (attrId, value) => {
            setLocalFilters(prev => ({
                ...prev,
                attributes: {
                    ...prev.attributes,
                    [attrId]: value
                }
            }));
        };

        const handleAttributeConfigChange = (attrId, key, value) => {
            const current = localFilters.attributes?.[attrId];
            const nextConfig = (current && typeof current === 'object' && !Array.isArray(current))
                ? { ...current, [key]: value }
                : { [key]: value };
            handleAttributeChange(attrId, nextConfig);
        };

        const applyFilters = () => {
            onFilter(localFilters);
            setIsOpen(false);
        };

        const clearFilters = () => {
            const cleared = {
                account_id: '',
                item_type: '',
                attributes: {}
            };
            setLocalFilters(cleared);
            onFilter(cleared);
            setIsOpen(false);
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
                    <div className="absolute right-0 top-full mt-2 w-80 bg-popover border rounded-md shadow-lg p-4 z-50 space-y-4 max-h-[70vh] overflow-y-auto">
                        <div>
                            <label className="block text-sm font-medium mb-1">Account</label>
                            <select
                                className="w-full border rounded-md p-2 text-sm bg-background"
                                value={localFilters.account_id || ''}
                                onChange={(e) => handleChange('account_id', e.target.value)}
                            >
                                <option value="">All Accounts</option>
                                {accounts.map(acc => (
                                    <option key={acc.id} value={acc.id}>{acc.email || acc.display_name}</option>
                                ))}
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

                        <div className="border-t pt-3">
                            <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                                Category Attributes
                            </h4>
                            <div className="space-y-3">
                                {filterableAttributes.map(attr => (
                                    <div key={attr.id}>
                                        <label className="block text-sm font-medium mb-1">{attr.name}</label>
                                        {attr.data_type === 'select' ? (
                                            <div className="grid grid-cols-2 gap-2">
                                                <select
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.op) || 'eq'}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'op', e.target.value)}
                                                >
                                                    <option value="eq">=</option>
                                                    <option value="ne">!=</option>
                                                </select>
                                                <select
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.value) ?? ''}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'value', e.target.value)}
                                                >
                                                    <option value="">Any</option>
                                                    {getSelectOptions(attr.options).map(opt => (
                                                        <option key={opt} value={opt}>{opt}</option>
                                                    ))}
                                                </select>
                                            </div>
                                        ) : attr.data_type === 'boolean' ? (
                                            <div className="grid grid-cols-2 gap-2">
                                                <select
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.op) || 'eq'}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'op', e.target.value)}
                                                >
                                                    <option value="eq">=</option>
                                                    <option value="ne">!=</option>
                                                </select>
                                                <select
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.value) ?? ''}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'value', e.target.value)}
                                                >
                                                    <option value="">Any</option>
                                                    <option value="true">Yes</option>
                                                    <option value="false">No</option>
                                                </select>
                                            </div>
                                        ) : attr.data_type === 'number' ? (
                                            <div className="grid grid-cols-2 gap-2">
                                                <input
                                                    type="number"
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.min) ?? ''}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'min', e.target.value)}
                                                    placeholder="Min"
                                                />
                                                <input
                                                    type="number"
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.max) ?? ''}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'max', e.target.value)}
                                                    placeholder="Max"
                                                />
                                            </div>
                                        ) : attr.data_type === 'text' || attr.data_type === 'tags' ? (
                                            <div className="grid grid-cols-2 gap-2">
                                                <select
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.op) || 'contains'}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'op', e.target.value)}
                                                >
                                                    <option value="contains">contains</option>
                                                    <option value="not_contains">not contains</option>
                                                    <option value="eq">=</option>
                                                    <option value="ne">!=</option>
                                                </select>
                                                <input
                                                    type="text"
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.value) ?? ''}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'value', e.target.value)}
                                                    placeholder={attr.data_type === 'tags' ? 'tag1, tag2' : `Filter by ${attr.name}`}
                                                />
                                            </div>
                                        ) : attr.data_type === 'date' ? (
                                            <div className="grid grid-cols-2 gap-2">
                                                <select
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.op) || 'eq'}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'op', e.target.value)}
                                                >
                                                    <option value="eq">=</option>
                                                    <option value="ne">!=</option>
                                                    <option value="gte">&gt;=</option>
                                                    <option value="lte">&lt;=</option>
                                                </select>
                                                <input
                                                    type="date"
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.value) ?? ''}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'value', e.target.value)}
                                                />
                                            </div>
                                        ) : (
                                            <select
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={localFilters.attributes[attr.id] ?? ''}
                                                onChange={(e) => handleAttributeChange(attr.id, e.target.value)}
                                            >
                                                <option value="">Any</option>
                                                <option value="true">Yes</option>
                                                <option value="false">No</option>
                                            </select>
                                        )}
                                    </div>
                                ))}
                                {filterableAttributes.length === 0 && (
                                    <p className="text-xs text-muted-foreground">
                                        No editable attributes available for filtering.
                                    </p>
                                )}
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

    const fetchItems = useCallback(async (overridePage) => {
        setLoading(true);
        try {
            const effectivePage = overridePage ?? page;
            const isSeriesTrackerMode = supportsSeriesTracker && viewMode === 'series_tracker';
            const metadataFilters = {};
            Object.entries(filters.attributes || {}).forEach(([attrId, config]) => {
                if (config === null || config === undefined) return;

                if (typeof config === 'object' && !Array.isArray(config)) {
                    const normalized = {};
                    if (config.op !== undefined && config.op !== null && config.op !== '') {
                        normalized.op = config.op;
                    }
                    if (config.value !== undefined && config.value !== null && config.value !== '') {
                        normalized.value = config.value;
                    }
                    if (config.min !== undefined && config.min !== null && config.min !== '') {
                        normalized.min = config.min;
                    }
                    if (config.max !== undefined && config.max !== null && config.max !== '') {
                        normalized.max = config.max;
                    }
                    if (Object.keys(normalized).length > 0) {
                        metadataFilters[attrId] = normalized;
                    }
                } else if (config !== '' && config !== null && config !== undefined) {
                    metadataFilters[attrId] = config;
                }
            });

            const baseParams = {
                sort_by: selectedMetadataSort ? 'modified_at' : sort.by,
                sort_order: sort.order,
                metadata_sort_attribute_id: selectedMetadataSort?.attributeId,
                metadata_sort_data_type: selectedMetadataSort?.dataType,
                category_id: category.id,
                has_metadata: true,
                q: appliedSearchTerm,
                search_fields: searchScope,
                account_id: filters.account_id || undefined,
                item_type: filters.item_type || undefined,
                metadata: metadataFilters
            };

            if (isSeriesTrackerMode) {
                const seriesSortBy = sort.by === 'size' ? 'total_items' : 'series';
                const data = await metadataService.getSeriesSummary(category.id, {
                    page: effectivePage,
                    page_size: ITEMS_PER_PAGE,
                    sort_by: seriesSortBy,
                    sort_order: sort.order,
                    q: appliedSearchTerm,
                    search_fields: searchScope,
                    account_id: filters.account_id || undefined,
                    item_type: filters.item_type || undefined,
                    metadata: metadataFilters,
                });
                setSeriesRows(data.rows || []);
                setItems([]);
                setTotal(data.total || 0);
                setTotalPages(data.total_pages || 1);
            } else {
                const data = await itemsService.listItems({
                    ...baseParams,
                    page: effectivePage,
                    page_size: ITEMS_PER_PAGE,
                });
                setSeriesRows([]);
                setItems(data.items);
                setTotal(data.total);
                setTotalPages(data.total_pages);
            }
        } catch (error) {
            console.error('Failed to fetch category items:', error);
        } finally {
            setLoading(false);
        }
    }, [page, sort.by, sort.order, selectedMetadataSort, category.id, supportsSeriesTracker, viewMode, appliedSearchTerm, searchScope, filters]);

    useEffect(() => {
        fetchItems();
    }, [fetchItems]);

    useEffect(() => {
        setSelectedItems(new Set());
    }, [items]);

    useEffect(() => {
        const allowedModes = ['table'];
        if (supportsGallery) allowedModes.push('gallery');
        if (supportsSeriesTracker) allowedModes.push('series_tracker');
        if (!allowedModes.includes(viewMode)) {
            setViewMode('table');
        }
    }, [supportsGallery, supportsSeriesTracker, viewMode, category?.id]);

    useEffect(() => {
        if (!supportsGallery || viewMode !== 'gallery') {
            setCoverUrlsByItemId({});
            return;
        }

        const coverAttr = (category.attributes || []).find(
            (attr) => attr.plugin_field_key === libraryView?.gallery?.coverField
        );
        const coverAccountAttr = (category.attributes || []).find(
            (attr) => attr.plugin_field_key === libraryView?.gallery?.coverAccountField
        );
        if (!coverAttr) {
            setCoverUrlsByItemId({});
            return;
        }

        let cancelled = false;

        const resolveCoverUrls = async () => {
            const preloaded = {};
            const misses = [];
            for (const item of items) {
                const coverItemId = item.metadata?.values?.[coverAttr.id];
                if (!coverItemId) continue;
                const coverAccountId = coverAccountAttr
                    ? item.metadata?.values?.[coverAccountAttr.id]
                    : item.account_id;
                if (!coverAccountId) continue;
                const cacheKey = buildCoverCacheKey(String(coverAccountId), String(coverItemId));
                const cached = getCachedCoverUrl(cacheKey);
                if (cached) {
                    preloaded[item.id] = cached;
                } else {
                    misses.push({
                        item,
                        coverItemId: String(coverItemId),
                        coverAccountId: String(coverAccountId),
                        cacheKey,
                    });
                }
            }

            setCoverUrlsByItemId(preloaded);
            await Promise.all(
                misses.map(async ({ item, coverItemId, coverAccountId, cacheKey }) => {
                    try {
                        const url = driveService.getDownloadContentUrl(
                            coverAccountId,
                            coverItemId,
                            { autoResolveAccount: true },
                        );
                        if (cancelled || !url) return;
                        setCachedCoverUrl(cacheKey, url);
                        setCoverUrlsByItemId((prev) => {
                            if (prev[item.id] === url) return prev;
                            return { ...prev, [item.id]: url };
                        });
                    } catch (_) {
                        // Keep placeholder when one cover fails.
                    }
                })
            );
        };

        resolveCoverUrls();

        return () => {
            cancelled = true;
        };
    }, [supportsGallery, viewMode, items, category.attributes, libraryView]);

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
        if (!bytes || bytes === 0) return '0 B';
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

    const getAttributeValue = (item, attr) => {
        if (!item.metadata?.values) return '-';
        const val = item.metadata.values[attr.id];
        if (val === undefined || val === null || val === '') return '-';

        if (attr.data_type === 'boolean') return val ? 'Yes' : 'No';
        if (attr.data_type === 'tags') {
            const tags = Array.isArray(val) ? val : parseTagsInput(String(val));
            return tags.length > 0 ? tags.join(', ') : '-';
        }
        if (attr.data_type === 'date' && val) {
            return new Date(val).toLocaleDateString('en-GB');
        }
        return String(val);
    };

    const isReadOnlyAttribute = (attr) => {
        if (!attr) return true;
        if (attr.plugin_key === 'comics_core') {
            return READ_ONLY_COMIC_FIELD_KEYS.has(attr.plugin_field_key);
        }
        return Boolean(attr.is_locked || attr.managed_by_plugin);
    };

    const getEditValue = (item, attr) => {
        const rawValue = item.metadata?.values?.[attr.id];
        if (rawValue === undefined || rawValue === null) return '';
        if (attr.data_type === 'boolean') return rawValue ? 'true' : 'false';
        if (attr.data_type === 'tags') return tagsToInputValue(rawValue);
        if (attr.data_type === 'date') {
            const text = String(rawValue);
            return text.includes('T') ? text.slice(0, 10) : text;
        }
        return String(rawValue);
    };

    const startInlineEdit = (item, attr, event) => {
        event.stopPropagation();
        if (isReadOnlyAttribute(attr)) return;
        setEditingCell({ itemId: item.id, attrId: attr.id });
        setEditingValue(getEditValue(item, attr));
    };

    const cancelInlineEdit = () => {
        setEditingCell(null);
        setEditingValue('');
    };

    const toPayloadValue = (attr, value) => {
        if (value === '' || value === null || value === undefined) return null;
        if (attr.data_type === 'boolean') {
            if (value === 'true' || value === true) return true;
            if (value === 'false' || value === false) return false;
            return null;
        }
        if (attr.data_type === 'tags') {
            const parsed = parseTagsInput(String(value || ''));
            return parsed.length > 0 ? parsed : null;
        }
        return value;
    };

    const saveInlineEdit = async (item, attr) => {
        const cellKey = `${item.id}:${attr.id}`;
        setSavingCellKey(cellKey);
        try {
            const updatedMetadata = await metadataService.updateItemMetadataField(
                item.account_id,
                item.item_id,
                attr.id,
                {
                    value: toPayloadValue(attr, editingValue),
                    category_id: category.id,
                    expected_version: item.metadata?.version ?? null,
                }
            );

            setItems((prev) =>
                prev.map((row) => {
                    if (row.id !== item.id) return row;
                    return {
                        ...row,
                        metadata: {
                            ...(row.metadata || {}),
                            ...updatedMetadata,
                            values: updatedMetadata?.values || {},
                        },
                    };
                })
            );
            setEditingCell(null);
            setEditingValue('');
            showToast(`'${attr.name}' updated.`, 'success');
        } catch (error) {
            showToast(error?.response?.data?.detail || `Failed to update '${attr.name}'`, 'error');
        } finally {
            setSavingCellKey(null);
        }
    };

    const attributes = sortAttributesForCategory(category);
    const findAttr = (pluginKey, fallbackName) => {
        if (!pluginKey && !fallbackName) return null;
        const byPluginKey = pluginKey
            ? attributes.find((attr) => attr.plugin_field_key === pluginKey)
            : null;
        if (byPluginKey) return byPluginKey;
        if (!fallbackName) return null;
        const normalizedFallback = fallbackName.trim().toLowerCase();
        return attributes.find((attr) => String(attr.name || '').trim().toLowerCase() === normalizedFallback) || null;
    };

    const titleAttr = findAttr(libraryView?.gallery?.titleField, 'Title');
    const subtitleAttr = findAttr(libraryView?.gallery?.subtitleField, 'Series');
    const pageCountAttr = findAttr(libraryView?.gallery?.pageCountField, 'Page Count');
    const volumeAttr = findAttr(libraryView?.gallery?.volumeField, 'Volume');
    const issueNumberAttr = findAttr(libraryView?.gallery?.issueNumberField, 'Issue Number');
    const statusLabel = {
        ongoing: 'Ongoing',
        completed: 'Completed',
        hiatus: 'Hiatus',
        cancelled: 'Cancelled',
        unknown: 'Unknown',
    };
    const statusClass = {
        ongoing: 'bg-blue-100 text-blue-700',
        completed: 'bg-emerald-100 text-emerald-700',
        hiatus: 'bg-amber-100 text-amber-700',
        cancelled: 'bg-rose-100 text-rose-700',
        unknown: 'bg-zinc-100 text-zinc-700',
    };

    const fixedColTemplate = '40px 40px 2fr 120px 80px';
    const attrCols = attributes.map(() => 'minmax(100px, 1fr)').join(' ');
    const gridTemplate = `${fixedColTemplate} ${attrCols} 140px minmax(180px,1fr)`;
    const tableMinWidth = Math.max(1200, 780 + attributes.length * 180);

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

    const getSelectedObjects = () => items.filter(i => selectedItems.has(i.id));
    const singleSelectedItem = selectedItems.size === 1
        ? items.find((i) => i.id === Array.from(selectedItems)[0]) || null
        : null;
    const moveTargetItem = singleSelectedItem
        ? { ...singleSelectedItem, id: singleSelectedItem.item_id }
        : null;
    const selectedItemsForBatchEdit = getSelectedObjects().map((item) => ({
        ...item,
        item_id: item.item_id || item.id,
    }));

    const handleDownload = async () => {
        const selectedFiles = getSelectedObjects().filter((item) => item.item_type === 'file');
        for (const file of selectedFiles) {
            try {
                const url = await driveService.getDownloadUrl(file.account_id, file.item_id);
                window.open(url, '_blank');
            } catch (error) {
                console.error(`Failed to download ${file.name}`, error);
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
            await fetchItems();
        } catch (error) {
            showToast(error?.response?.data?.detail || 'Failed to rename item', 'error');
        } finally {
            setRenameSaving(false);
        }
    };

    const getAccountName = (accountId) => {
        const acc = accounts.find(a => a.id === accountId);
        return acc ? (acc.email || acc.display_name) : (accountId ? String(accountId).slice(0, 8) : '-');
    };

    const applySearch = () => {
        setPage(1);
        setAppliedSearchTerm(searchTerm.trim());
    };

    const searchPlaceholders = {
        name: 'Search by title...',
        path: 'Search by path...',
        both: 'Search by title or path...'
    };

    return (
        <>
            {/* Header */}
            <div className="p-4 border-b flex items-center justify-between bg-background">
                <div className="flex items-center gap-3">
                    <button
                        onClick={onBack}
                        className="p-2 hover:bg-accent rounded-md text-muted-foreground hover:text-foreground transition-colors"
                        title="Back to categories"
                    >
                        <ArrowLeft size={18} />
                    </button>
                    <div>
                        <h1 className="text-lg font-semibold text-foreground">{category.name}</h1>
                        <p className="text-xs text-muted-foreground">{total} items</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {(supportsGallery || supportsSeriesTracker) && (
                        <div className="inline-flex items-center border rounded-md overflow-hidden">
                            <button
                                onClick={() => setViewMode('table')}
                                className={`px-3 py-1.5 text-sm ${viewMode === 'table' ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'}`}
                            >
                                Table
                            </button>
                            <button
                                onClick={() => setViewMode('gallery')}
                                className={`px-3 py-1.5 text-sm ${viewMode === 'gallery' ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'}`}
                            >
                                Gallery
                            </button>
                            {supportsSeriesTracker && (
                                <button
                                    onClick={() => setViewMode('series_tracker')}
                                    className={`px-3 py-1.5 text-sm ${viewMode === 'series_tracker' ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'}`}
                                >
                                    Series
                                </button>
                            )}
                        </div>
                    )}
                    <select
                        className="border rounded-md px-2 py-1.5 text-sm bg-background"
                        value={searchScope}
                        onChange={(e) => setSearchScope(e.target.value)}
                    >
                        <option value="both">Title + Path</option>
                        <option value="name">Title</option>
                        <option value="path">Path</option>
                    </select>
                    <select
                        className="border rounded-md px-2 py-1.5 text-sm bg-background"
                        value={sort.by}
                        onChange={(e) => {
                            setSort((prev) => ({ ...prev, by: e.target.value }));
                            setPage(1);
                        }}
                    >
                        {sortOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                    <select
                        className="border rounded-md px-2 py-1.5 text-sm bg-background"
                        value={sort.order}
                        onChange={(e) => {
                            setSort((prev) => ({ ...prev, order: e.target.value }));
                            setPage(1);
                        }}
                    >
                        <option value="desc">Desc</option>
                        <option value="asc">Asc</option>
                    </select>
                    <div className="relative">
                        <Search className="absolute left-2 top-1.5 text-muted-foreground" size={16} />
                        <input
                            type="text"
                            placeholder={searchPlaceholders[searchScope]}
                            className="pl-8 pr-4 py-1.5 text-sm border rounded-md w-72 focus:outline-none focus:ring-1 focus:ring-primary"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') applySearch(); }}
                        />
                    </div>
                    <CategoryFilterBar
                        onFilter={(newFilters) => {
                            setFilters(newFilters);
                            setPage(1);
                        }}
                        currentFilters={filters}
                    />
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
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2"
                                    >
                                        <Database size={14} /> Edit Metadata
                                    </button>
                                    <button
                                        onClick={() => {
                                            openRenameModal();
                                            setMetadataMenuOpen(false);
                                        }}
                                        disabled={selectedItems.size !== 1}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                    >
                                        <Pencil size={14} /> Rename
                                    </button>
                                    <button
                                        onClick={() => {
                                            setRemoveModalOpen(true);
                                            setMetadataMenuOpen(false);
                                        }}
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
                        onClick={() => setDeleteModalOpen(true)}
                        disabled={selectedItems.size === 0}
                        className="p-2 hover:bg-destructive/10 text-destructive rounded-md flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Delete"
                    >
                        <Trash2 size={16} /> <span className="hidden sm:inline">Delete</span>
                    </button>
                </div>

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

            {/* Content */}
            <main className="flex-1 overflow-auto p-4">
                {loading ? (
                    <div className="flex justify-center p-12">
                        <Loader2 className="animate-spin text-primary" size={32} />
                    </div>
                ) : (viewMode === 'series_tracker' && supportsSeriesTracker ? seriesRows.length === 0 : items.length === 0) ? (
                    <div className="text-center p-12 text-muted-foreground">
                        No items found in this category.
                    </div>
                ) : (
                    viewMode === 'series_tracker' && supportsSeriesTracker ? (
                        <div className="space-y-4">
                            {seriesRows.length === 0 ? (
                                <div className="border rounded-lg bg-card p-6 text-sm text-muted-foreground">
                                    Series tracker needs at least one item with the &quot;Series&quot; field filled.
                                </div>
                            ) : (
                                seriesRows.map((seriesRow) => {
                                    const statusKey = statusLabel[seriesRow.series_status] ? seriesRow.series_status : 'unknown';
                                    const maxVolumes = Math.max(0, seriesRow.max_volumes || 0);
                                    const maxIssues = Math.max(0, seriesRow.max_issues || 0);
                                    const shownVolumes = maxVolumes > 0 ? maxVolumes : 0;
                                    const shownIssues = maxIssues > 0 ? maxIssues : 0;
                                    const ownedVolumes = Array.isArray(seriesRow.owned_volumes) ? seriesRow.owned_volumes : [];
                                    const ownedVolumesSet = new Set(ownedVolumes);
                                    const issuesByVolume = seriesRow.issues_by_volume || {};

                                    return (
                                        <div key={seriesRow.series_name} className="border rounded-lg bg-card p-4">
                                            <div className="flex items-center justify-between gap-3 mb-3">
                                                <div className="min-w-0">
                                                    <h3 className="font-semibold truncate">{seriesRow.series_name}</h3>
                                                    <p className="text-xs text-muted-foreground">
                                                        {seriesRow.total_items} item(s) | owned volumes: {ownedVolumes.length}
                                                    </p>
                                                </div>
                                                <div className={`px-2 py-1 rounded text-xs font-medium ${statusClass[statusKey]}`}>
                                                    {statusLabel[statusKey]}
                                                </div>
                                            </div>

                                            <div className="space-y-3">
                                                <div>
                                                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                                                        <span>Volumes</span>
                                                        <span>
                                                            {maxVolumes > 0 ? `max ${maxVolumes}` : 'max not set'}
                                                        </span>
                                                    </div>
                                                    {shownVolumes > 0 ? (
                                                        <div className="flex flex-wrap gap-1">
                                                            {Array.from({ length: shownVolumes }, (_, idx) => {
                                                                const volumeNo = idx + 1;
                                                                const owned = ownedVolumesSet.has(volumeNo);
                                                                return (
                                                                    <div
                                                                        key={`${seriesRow.series_name}-vol-${volumeNo}`}
                                                                        title={`Volume ${volumeNo} ${owned ? '(owned)' : '(missing)'}`}
                                                                        className={`h-4 w-3 rounded-sm border ${owned ? 'bg-blue-500 border-blue-500' : 'bg-white border-zinc-300'}`}
                                                                    />
                                                                );
                                                            })}
                                                        </div>
                                                    ) : (
                                                        <div className="text-xs text-muted-foreground">Set &quot;Max Volumes&quot; to show the tracker.</div>
                                                    )}
                                                </div>

                                                {shownIssues > 0 && (
                                                    <div className="space-y-2">
                                                        <div className="text-xs text-muted-foreground">
                                                            Issues per volume (max {maxIssues})
                                                        </div>
                                                        {ownedVolumes
                                                            .sort((a, b) => a - b)
                                                            .slice(0, 10)
                                                            .map((volumeNo) => {
                                                                const issues = new Set(issuesByVolume[String(volumeNo)] || []);
                                                                return (
                                                                    <div key={`${seriesRow.series_name}-issues-${volumeNo}`} className="flex items-center gap-2">
                                                                        <div className="w-10 text-xs text-muted-foreground">V{volumeNo}</div>
                                                                        <div className="flex flex-wrap gap-1">
                                                                            {Array.from({ length: shownIssues }, (_, idx) => {
                                                                                const issueNo = idx + 1;
                                                                                const owned = issues.has(issueNo);
                                                                                return (
                                                                                    <div
                                                                                        key={`${seriesRow.series_name}-vol-${volumeNo}-issue-${issueNo}`}
                                                                                        title={`V${volumeNo} #${issueNo} ${owned ? '(owned)' : '(missing)'}`}
                                                                                        className={`h-3 w-2 rounded-sm border ${owned ? 'bg-blue-500 border-blue-500' : 'bg-white border-zinc-300'}`}
                                                                                    />
                                                                                );
                                                                            })}
                                                                        </div>
                                                                    </div>
                                                                );
                                                            })}
                                                        {ownedVolumes.length > 10 && (
                                                            <div className="text-xs text-muted-foreground">
                                                                Showing first 10 owned volumes.
                                                            </div>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })
                            )}
                        </div>
                    ) : viewMode === 'gallery' && supportsGallery ? (
                        <div className="border rounded-lg bg-card p-4">
                            <div className="grid grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-4">
                                {items.map((item, index) => {
                                    const isSelected = selectedItems.has(item.id);
                                    const titleValue = titleAttr ? item.metadata?.values?.[titleAttr.id] : null;
                                    const seriesValue = subtitleAttr ? item.metadata?.values?.[subtitleAttr.id] : null;
                                    const baseLabel = (seriesValue && String(seriesValue).trim())
                                        || (titleValue && String(titleValue).trim())
                                        || item.name;
                                    const volumeValue = volumeAttr ? item.metadata?.values?.[volumeAttr.id] : null;
                                    const issueValue = issueNumberAttr ? item.metadata?.values?.[issueNumberAttr.id] : null;
                                    const hasVolume = volumeValue !== null && volumeValue !== undefined && String(volumeValue).trim() !== '';
                                    const hasIssue = issueValue !== null && issueValue !== undefined && String(issueValue).trim() !== '';
                                    const titleSuffix = `${hasVolume ? ` - Vol. ${String(volumeValue).trim()}` : ''}${hasIssue ? ` #${String(issueValue).trim()}` : ''}`;
                                    const title = `${baseLabel}${titleSuffix}`;
                                    const subtitle = (titleValue && String(titleValue).trim()) || null;
                                    const pageCount = pageCountAttr ? item.metadata?.values?.[pageCountAttr.id] : null;
                                    return (
                                        <button
                                            key={item.id}
                                            onClick={(e) => toggleSelection(item.id, index, !e.altKey, e.shiftKey)}
                                            className={`text-left border rounded-md bg-background overflow-hidden transition-colors ${
                                                isSelected ? 'ring-2 ring-primary border-primary/40' : 'hover:border-primary/40'
                                            }`}
                                        >
                                            <div className="aspect-[3/4] bg-muted/40">
                                                {coverUrlsByItemId[item.id] ? (
                                                    <img
                                                        src={coverUrlsByItemId[item.id]}
                                                        alt={String(title)}
                                                        className="w-full h-full object-cover"
                                                        loading="lazy"
                                                    />
                                                ) : (
                                                    <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground">
                                                        No cover
                                                    </div>
                                                )}
                                            </div>
                                            <div className="p-2 space-y-0.5">
                                                <div className="text-xs font-semibold truncate" title={String(title)}>
                                                    {title}
                                                </div>
                                                {subtitle ? (
                                                    <div className="text-[11px] text-muted-foreground truncate" title={String(subtitle)}>
                                                        {subtitle}
                                                    </div>
                                                ) : (
                                                    <div className="text-[11px] text-muted-foreground truncate" title={item.name}>
                                                        {item.name}
                                                    </div>
                                                )}
                                                {pageCount !== null && pageCount !== undefined && pageCount !== '' && (
                                                    <div className="text-[11px] text-muted-foreground">
                                                        {pageCount} pages
                                                    </div>
                                                )}
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    ) : (
                        <div className="border rounded-lg bg-card select-none overflow-hidden">
                            <div className="overflow-x-auto">
                                <div style={{ minWidth: `${tableMinWidth}px` }}>
                                    {/* Table Header */}
                                    <div
                                        className="gap-4 p-3 border-b bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider items-center sticky top-0"
                                        style={{ display: 'grid', gridTemplateColumns: gridTemplate }}
                                    >
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
                                        {attributes.map(attr => (
                                            <div key={attr.id} className="flex items-center gap-1 truncate" title={attr.name}>
                                                {attr.name}
                                            </div>
                                        ))}
                                        <div className="cursor-pointer flex items-center gap-1 hover:text-foreground justify-end" onClick={() => handleSort('modified_at')}>
                                            Modified {renderSortIcon('modified_at')}
                                        </div>
                                        <div className="text-right">Path</div>
                                    </div>

                                    {/* Table Rows */}
                                    <div className="divide-y">
                                        {items.map((item, index) => {
                                            const isFolder = item.item_type === 'folder';
                                            const isSelected = selectedItems.has(item.id);
                                            return (
                                                <div
                                                    key={item.id}
                                                    className={`gap-4 p-3 items-center hover:bg-muted/30 transition-colors ${isSelected ? 'bg-muted/40' : ''}`}
                                                    style={{ display: 'grid', gridTemplateColumns: gridTemplate }}
                                                    onClick={(e) => toggleSelection(item.id, index, !e.altKey, e.shiftKey)}
                                                >
                                                    <div className="flex justify-center">
                                                        <div className={`cursor-pointer ${isSelected ? 'text-primary' : 'text-muted-foreground/50'}`}>
                                                            {isSelected ? <CheckSquare size={16} /> : <Square size={16} />}
                                                        </div>
                                                    </div>
                                                    <div className="flex justify-center text-muted-foreground">
                                                        {isFolder ? (
                                                            <Folder className="text-blue-500 fill-blue-500/20" size={20} />
                                                        ) : (
                                                            <File className="text-gray-400" size={20} />
                                                        )}
                                                    </div>
                                                    <div className="min-w-0 truncate font-medium" title={item.name}>
                                                        {item.name}
                                                    </div>
                                                    <div className="flex items-center gap-1 text-sm text-foreground">
                                                        <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                                                            <User size={12} className="text-primary" />
                                                        </div>
                                                        <span className="truncate" title={getAccountName(item.account_id)}>
                                                            {getAccountName(item.account_id)}
                                                        </span>
                                                    </div>
                                                    <div className="text-right text-sm text-muted-foreground tabular-nums">
                                                        {formatSize(item.size)}
                                                    </div>
                                                    {attributes.map((attr) => {
                                                        const isEditing = editingCell?.itemId === item.id && editingCell?.attrId === attr.id;
                                                        const cellKey = `${item.id}:${attr.id}`;
                                                        const isSaving = savingCellKey === cellKey;
                                                        const readOnly = isReadOnlyAttribute(attr);
                                                        const displayValue = getAttributeValue(item, attr);

                                                        return (
                                                            <div
                                                                key={attr.id}
                                                                className={`text-sm text-foreground min-w-0 ${readOnly ? '' : 'cursor-text'}`}
                                                                onClick={(e) => startInlineEdit(item, attr, e)}
                                                                title={readOnly ? `${displayValue} (read-only)` : String(displayValue)}
                                                            >
                                                                {isEditing ? (
                                                                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                                                                        {attr.data_type === 'select' ? (
                                                                            <select
                                                                                className="w-full border rounded px-2 py-1 text-xs bg-background"
                                                                                value={editingValue}
                                                                                onChange={(e) => setEditingValue(e.target.value)}
                                                                            >
                                                                                <option value="">-</option>
                                                                                {getSelectOptions(attr.options).map((option) => (
                                                                                    <option key={option} value={option}>
                                                                                        {option}
                                                                                    </option>
                                                                                ))}
                                                                            </select>
                                                                        ) : attr.data_type === 'boolean' ? (
                                                                            <select
                                                                                className="w-full border rounded px-2 py-1 text-xs bg-background"
                                                                                value={editingValue}
                                                                                onChange={(e) => setEditingValue(e.target.value)}
                                                                            >
                                                                                <option value="">-</option>
                                                                                <option value="true">Yes</option>
                                                                                <option value="false">No</option>
                                                                            </select>
                                                                        ) : attr.data_type === 'tags' ? (
                                                                            <input
                                                                                type="text"
                                                                                value={editingValue}
                                                                                onChange={(e) => setEditingValue(e.target.value)}
                                                                                onKeyDown={(e) => {
                                                                                    if (e.key === 'Enter') {
                                                                                        e.preventDefault();
                                                                                        saveInlineEdit(item, attr);
                                                                                    }
                                                                                    if (e.key === 'Escape') {
                                                                                        e.preventDefault();
                                                                                        cancelInlineEdit();
                                                                                    }
                                                                                }}
                                                                                placeholder="tag1, tag2, tag3"
                                                                                className="w-full border rounded px-2 py-1 text-xs bg-background"
                                                                                autoFocus
                                                                            />
                                                                        ) : (
                                                                            <input
                                                                                type={attr.data_type === 'number' ? 'number' : attr.data_type === 'date' ? 'date' : 'text'}
                                                                                value={editingValue}
                                                                                onChange={(e) => setEditingValue(e.target.value)}
                                                                                onKeyDown={(e) => {
                                                                                    if (e.key === 'Enter') {
                                                                                        e.preventDefault();
                                                                                        saveInlineEdit(item, attr);
                                                                                    }
                                                                                    if (e.key === 'Escape') {
                                                                                        e.preventDefault();
                                                                                        cancelInlineEdit();
                                                                                    }
                                                                                }}
                                                                                className="w-full border rounded px-2 py-1 text-xs bg-background"
                                                                                autoFocus
                                                                            />
                                                                        )}
                                                                        <button
                                                                            type="button"
                                                                            className="p-1 rounded hover:bg-accent disabled:opacity-50"
                                                                            onClick={(e) => {
                                                                                e.stopPropagation();
                                                                                saveInlineEdit(item, attr);
                                                                            }}
                                                                            disabled={isSaving}
                                                                            title="Confirm"
                                                                        >
                                                                            {isSaving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                                                                        </button>
                                                                        <button
                                                                            type="button"
                                                                            className="p-1 rounded hover:bg-accent disabled:opacity-50"
                                                                            onClick={(e) => {
                                                                                e.stopPropagation();
                                                                                cancelInlineEdit();
                                                                            }}
                                                                            disabled={isSaving}
                                                                            title="Cancel"
                                                                        >
                                                                            <X size={12} />
                                                                        </button>
                                                                    </div>
                                                                ) : (
                                                                    <div className={`truncate ${readOnly ? 'text-muted-foreground' : ''}`}>{displayValue}</div>
                                                                )}
                                                            </div>
                                                        );
                                                    })}
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
                            </div>
                        </div>
                    )
                )}
            </main>

            <BatchMetadataModal
                isOpen={batchModalOpen}
                onClose={() => setBatchModalOpen(false)}
                selectedItems={selectedItemsForBatchEdit}
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
                selectedItems={selectedItemsForBatchEdit}
                showToast={showToast}
                onSuccess={() => {
                    fetchItems();
                    setSelectedItems(new Set());
                }}
            />

            <MoveModal
                isOpen={moveModalOpen}
                onClose={() => setMoveModalOpen(false)}
                item={moveTargetItem}
                sourceAccountId={singleSelectedItem?.account_id}
                onSuccess={() => {
                    setMoveModalOpen(false);
                    setSelectedItems(new Set());
                    fetchItems();
                }}
            />

            <Modal
                isOpen={deleteModalOpen}
                onClose={() => !actionLoading && setDeleteModalOpen(false)}
                title={`Delete ${selectedItems.size} item(s)?`}
            >
                <div className="space-y-4">
                    <p>Are you sure you want to delete the selected items? This action cannot be undone.</p>
                    <div className="flex justify-end gap-2">
                        <button
                            onClick={() => setDeleteModalOpen(false)}
                            disabled={actionLoading}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent disabled:opacity-50"
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
                            className="w-full border rounded-md p-2 bg-background"
                            autoFocus
                        />
                    </div>
                    <div className="flex justify-end gap-2 pt-2">
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
        </>
    );
};


// -- Main Page --
export default function MetadataManager() {
    const [categories, setCategories] = useState([]);
    const [libraries, setLibraries] = useState([]);
    const [loading, setLoading] = useState(true);
    const [librariesLoading, setLibrariesLoading] = useState(true);
    const [activeView, setActiveView] = useState('metadata');
    const [expandedCategory, setExpandedCategory] = useState(null);
    const [viewingCategory, setViewingCategory] = useState(null);
    const [togglingLibraryKey, setTogglingLibraryKey] = useState(null);
    const { showToast } = useToast();

    // Create Category State
    const [createModalOpen, setCreateModalOpen] = useState(false);
    const [newCategoryName, setNewCategoryName] = useState('');
    const [newCategoryDesc, setNewCategoryDesc] = useState('');

    // Create Attribute State
    const [addAttributeCategory, setAddAttributeCategory] = useState(null);
    const [newAttrName, setNewAttrName] = useState('');
    const [newAttrType, setNewAttrType] = useState('text');
    const [newAttrRequired, setNewAttrRequired] = useState(false);
    const [newAttrOptions, setNewAttrOptions] = useState('');
    const [editAttributeTarget, setEditAttributeTarget] = useState(null);
    const [editAttrName, setEditAttrName] = useState('');
    const [editAttrType, setEditAttrType] = useState('text');
    const [editAttrRequired, setEditAttrRequired] = useState(false);
    const [editAttrOptions, setEditAttrOptions] = useState('');
    const [editingAttribute, setEditingAttribute] = useState(false);
    const [deleteCategoryTarget, setDeleteCategoryTarget] = useState(null);
    const [deletingCategory, setDeletingCategory] = useState(false);
    const [layoutBuilderOpen, setLayoutBuilderOpen] = useState(false);

    const loadLibraries = useCallback(async () => {
        try {
            setLibrariesLoading(true);
            const rows = await metadataService.listMetadataLibraries();
            setLibraries(rows || []);
        } catch (error) {
            console.error(error);
            showToast('Failed to load metadata libraries', 'error');
        } finally {
            setLibrariesLoading(false);
        }
    }, [showToast]);

    const loadCategories = useCallback(async () => {
        try {
            setLoading(true);
            const data = await metadataService.getCategoryStats();
            setCategories(data);
        } catch (error) {
            console.error(error);
            showToast('Failed to load categories', 'error');
        } finally {
            setLoading(false);
        }
    }, [showToast]);

    useEffect(() => {
        loadCategories();
    }, [loadCategories]);

    useEffect(() => {
        loadLibraries();
    }, [loadLibraries]);

    const knownLibraries = useMemo(
        () => (
            libraries.length > 0
                ? libraries
                : [{ key: 'comics_core', name: 'Comics Core', description: 'Managed comics metadata schema.', is_active: false }]
        ),
        [libraries]
    );

    const toggleLibrary = async (library) => {
        try {
            setTogglingLibraryKey(library.key);
            if (library.is_active) {
                await metadataService.deactivateMetadataLibrary(library.key);
                showToast(`${library.name} disabled`, 'success');
            } else {
                await metadataService.activateMetadataLibrary(library.key);
                showToast(`${library.name} enabled`, 'success');
            }
            await Promise.all([loadLibraries(), loadCategories()]);
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to update metadata library';
            showToast(message, 'error');
        } finally {
            setTogglingLibraryKey(null);
        }
    };

    const handleCreateCategory = async (e) => {
        e.preventDefault();
        try {
            await metadataService.createCategory(newCategoryName, newCategoryDesc);
            showToast('Category created successfully', 'success');
            setCreateModalOpen(false);
            setNewCategoryName('');
            setNewCategoryDesc('');
            loadCategories();
        } catch (error) {
            showToast(error.message || 'Failed to create category', 'error');
        }
    };

    const openDeleteCategoryModal = (category, e) => {
        e.stopPropagation();
        if (category.is_locked || category.managed_by_plugin) {
            showToast('Library-managed categories cannot be deleted. Deactivate the metadata library instead.', 'error');
            return;
        }
        setDeleteCategoryTarget(category);
    };

    const confirmDeleteCategory = async () => {
        if (!deleteCategoryTarget) return;
        setDeletingCategory(true);
        try {
            await metadataService.deleteCategory(deleteCategoryTarget.id);
            showToast('Category deleted', 'success');
            setDeleteCategoryTarget(null);
            await loadCategories();
        } catch (error) {
            showToast('Failed to delete category', 'error');
        } finally {
            setDeletingCategory(false);
        }
    };

    const handleCreateAttribute = async (e) => {
        e.preventDefault();
        try {
            let options = null;
            if (newAttrType === 'select' && newAttrOptions) {
                options = { options: newAttrOptions.split(',').map(o => o.trim()) };
            }

            await metadataService.createAttribute(addAttributeCategory.id, {
                name: newAttrName,
                data_type: newAttrType,
                is_required: newAttrRequired,
                options: options
            });

            showToast('Attribute added', 'success');
            setAddAttributeCategory(null);
            setNewAttrName('');
            setNewAttrType('text');
            setNewAttrOptions('');
            setNewAttrRequired(false);
            loadCategories();
        } catch (error) {
            showToast('Failed to add attribute', 'error');
        }
    };

    const handleDeleteAttribute = async (attr) => {
        if (attr.is_locked || attr.managed_by_plugin) {
            showToast('Library-managed attributes cannot be deleted', 'error');
            return;
        }
        if (!window.confirm('Delete this attribute?')) return;
        try {
            await metadataService.deleteAttribute(attr.id);
            showToast('Attribute deleted', 'success');
            loadCategories();
        } catch (error) {
            showToast('Failed to delete attribute', 'error');
        }
    };

    const openEditAttributeModal = (attr) => {
        if (attr.is_locked || attr.managed_by_plugin) {
            showToast('Library-managed attributes cannot be edited', 'error');
            return;
        }
        setEditAttributeTarget(attr);
        setEditAttrName(attr.name || '');
        setEditAttrType(attr.data_type || 'text');
        setEditAttrRequired(!!attr.is_required);
        setEditAttrOptions(getSelectOptions(attr.options).join(', '));
    };

    const handleUpdateAttribute = async (e) => {
        e.preventDefault();
        if (!editAttributeTarget) return;

        try {
            setEditingAttribute(true);
            let options = null;
            if (editAttrType === 'select') {
                const parsedOptions = editAttrOptions
                    .split(',')
                    .map((o) => o.trim())
                    .filter(Boolean);
                options = { options: parsedOptions };
            }

            await metadataService.updateAttribute(editAttributeTarget.id, {
                name: editAttrName,
                data_type: editAttrType,
                is_required: editAttrRequired,
                options,
            });

            showToast('Attribute updated', 'success');
            setEditAttributeTarget(null);
            await loadCategories();
        } catch (error) {
            showToast(error?.response?.data?.detail || 'Failed to update attribute', 'error');
        } finally {
            setEditingAttribute(false);
        }
    };

    const toggleExpand = (id) => {
        setExpandedCategory(expandedCategory === id ? null : id);
    };

    // If viewing a specific category's items
    if (viewingCategory) {
        return (
            <div className="flex flex-col h-screen">
                <CategoryItemsTable
                    category={viewingCategory}
                    onBack={() => { setViewingCategory(null); loadCategories(); }}
                />
            </div>
        );
    }

    return (
        <div className="flex flex-col h-screen">
            {/* Header */}
            <div className="p-4 border-b flex items-center justify-between bg-background sticky top-0 z-10">
                <div className="flex items-center gap-3">
                    <h1 className="text-lg font-semibold text-foreground">Metadata Manager</h1>
                    <span className="text-xs text-muted-foreground font-normal bg-muted px-2 py-0.5 rounded-full">
                        {activeView === 'metadata'
                            ? `${categories.length} categories`
                            : `${knownLibraries.length} libraries`}
                    </span>
                    <div className="inline-flex items-center gap-1 border rounded-md p-1 bg-muted/20">
                        <button
                            type="button"
                            onClick={() => setActiveView('metadata')}
                            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                                activeView === 'metadata'
                                    ? 'bg-primary text-primary-foreground'
                                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                            }`}
                        >
                            Metadata
                        </button>
                        <button
                            type="button"
                            onClick={() => setActiveView('libraries')}
                            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                                activeView === 'libraries'
                                    ? 'bg-primary text-primary-foreground'
                                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                            }`}
                        >
                            Libraries
                        </button>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {activeView === 'metadata' && (
                        <>
                            <button
                                onClick={() => setLayoutBuilderOpen(true)}
                                disabled={categories.length === 0}
                                className="flex items-center gap-2 px-4 py-2 border rounded-md hover:bg-accent text-sm font-medium transition-colors disabled:opacity-40"
                            >
                                Form Layout
                            </button>
                            <button
                                onClick={() => setCreateModalOpen(true)}
                                className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 text-sm font-medium transition-colors"
                            >
                                <Plus size={16} /> New Category
                            </button>
                        </>
                    )}
                </div>
            </div>

            {/* Content */}
            <main className="flex-1 overflow-auto p-4">
                {activeView === 'libraries' ? (
                    <section className="border rounded-lg bg-card p-4">
                        <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                                <h2 className="text-base font-semibold text-foreground">Metadata Libraries</h2>
                                <span className="text-xs text-muted-foreground font-normal bg-muted px-2 py-0.5 rounded-full">
                                    {knownLibraries.length} available
                                </span>
                            </div>
                        </div>

                        {librariesLoading ? (
                            <div className="flex justify-center py-6">
                                <Loader2 className="animate-spin text-primary" size={22} />
                            </div>
                        ) : (
                            <div className="grid gap-3">
                                {knownLibraries.map((library) => (
                                    <div key={library.key} className="border rounded-md bg-background p-3 flex items-center justify-between gap-3">
                                        <div className="flex items-start gap-3 min-w-0">
                                            <div className="p-2 rounded-md bg-primary/10 text-primary">
                                                <BookOpen size={16} />
                                            </div>
                                            <div className="min-w-0">
                                                <div className="font-semibold">{library.name}</div>
                                                <div className="text-xs text-muted-foreground">{library.key}</div>
                                                {library.description && (
                                                    <p className="text-sm text-muted-foreground mt-1">{library.description}</p>
                                                )}
                                            </div>
                                        </div>
                                        <button
                                            onClick={() => toggleLibrary(library)}
                                            disabled={togglingLibraryKey === library.key}
                                            className={`inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors disabled:opacity-60 ${
                                                library.is_active
                                                    ? 'bg-destructive/10 text-destructive hover:bg-destructive/20'
                                                    : 'bg-primary text-primary-foreground hover:bg-primary/90'
                                            }`}
                                        >
                                            {togglingLibraryKey === library.key
                                                ? <Loader2 size={14} className="animate-spin" />
                                                : <Power size={14} />}
                                            {library.is_active ? 'Disable' : 'Enable'}
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </section>
                ) : (
                    loading ? (
                        <div className="flex justify-center p-12">
                            <Loader2 className="animate-spin text-primary" size={32} />
                        </div>
                    ) : categories.length === 0 ? (
                        <div className="text-center p-12 text-muted-foreground border border-dashed rounded-lg bg-muted/50">
                            <Database className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                            <h3 className="text-lg font-medium mb-1">No categories defined</h3>
                            <p className="text-sm">Create a category to start organizing your file metadata.</p>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {categories.map(cat => (
                                <div key={cat.id} className="border rounded-lg bg-card overflow-hidden">
                                    {/* Category Header */}
                                    <div
                                        className="p-4 flex items-center justify-between cursor-pointer hover:bg-accent/50 transition-colors"
                                        onClick={() => toggleExpand(cat.id)}
                                    >
                                        <div className="flex items-center gap-3 min-w-0">
                                            {expandedCategory === cat.id
                                                ? <ChevronDown size={18} className="text-muted-foreground shrink-0" />
                                                : <ChevronRight size={18} className="text-muted-foreground shrink-0" />
                                            }
                                            <div className="min-w-0">
                                                <h3 className="font-semibold">{cat.name}</h3>
                                                {cat.description && <p className="text-sm text-muted-foreground truncate">{cat.description}</p>}
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-3 shrink-0">
                                            <div className="flex items-center gap-2 text-sm">
                                                <span className="bg-primary/10 text-primary px-2.5 py-1 rounded-full text-xs font-medium flex items-center gap-1.5">
                                                    <Hash size={12} />
                                                    {cat.item_count} items
                                                </span>
                                                <span className="bg-secondary text-secondary-foreground px-2.5 py-1 rounded-full text-xs font-medium flex items-center gap-1.5">
                                                    <Tag size={12} />
                                                    {cat.attributes.length} attrs
                                                </span>
                                            </div>
                                            <button
                                                onClick={(e) => { e.stopPropagation(); setViewingCategory(cat); }}
                                                className="p-2 hover:bg-primary/10 text-muted-foreground hover:text-primary rounded-md transition-colors"
                                                title="View items in this category"
                                            >
                                                <Eye size={18} />
                                            </button>
                                            <button
                                                onClick={(e) => openDeleteCategoryModal(cat, e)}
                                                disabled={cat.is_locked || cat.managed_by_plugin}
                                                className="p-2 hover:bg-destructive/10 text-muted-foreground hover:text-destructive rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                                                title="Delete category"
                                            >
                                                <Trash2 size={18} />
                                            </button>
                                        </div>
                                    </div>

                                    {/* Expanded Attributes */}
                                    {expandedCategory === cat.id && (
                                        <div className="p-4 border-t bg-muted/20">
                                            <div className="flex justify-between items-center mb-4">
                                                <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Attributes</h4>
                                                <button
                                                    onClick={() => setAddAttributeCategory(cat)}
                                                    className="text-sm text-primary hover:underline flex items-center gap-1"
                                                >
                                                    <Plus size={14} /> Add Attribute
                                                </button>
                                            </div>

                                            {cat.attributes.length === 0 ? (
                                                <p className="text-sm text-muted-foreground italic">No attributes defined yet.</p>
                                            ) : (
                                                <div className="grid gap-2">
                                                    {cat.attributes.map(attr => (
                                                        <div key={attr.id} className="flex items-center justify-between p-3 bg-background border rounded-md">
                                                            <div className="flex items-center gap-4">
                                                                <div className="font-medium">{attr.name}</div>
                                                                <div className="text-xs px-2 py-0.5 bg-secondary rounded-full text-secondary-foreground">
                                                                    {attr.data_type}
                                                                </div>
                                                                {attr.is_required && (
                                                                    <div className="text-xs text-amber-600 font-medium">Required</div>
                                                                )}
                                                                {attr.data_type === 'select' && attr.options?.options && (
                                                                    <div className="text-xs text-muted-foreground">
                                                                        Options: {getSelectOptions(attr.options).join(', ')}
                                                                    </div>
                                                                )}
                                                            </div>
                                                            <div className="flex items-center gap-1">
                                                                <button
                                                                    onClick={() => openEditAttributeModal(attr)}
                                                                    disabled={attr.is_locked || attr.managed_by_plugin}
                                                                    className="text-muted-foreground hover:text-primary p-1 rounded disabled:opacity-40 disabled:cursor-not-allowed"
                                                                    title="Edit attribute"
                                                                >
                                                                    <Pencil size={16} />
                                                                </button>
                                                                <button
                                                                    onClick={() => handleDeleteAttribute(attr)}
                                                                    disabled={attr.is_locked || attr.managed_by_plugin}
                                                                    className="text-muted-foreground hover:text-destructive p-1 rounded disabled:opacity-40 disabled:cursor-not-allowed"
                                                                    title="Delete attribute"
                                                                >
                                                                    <Trash2 size={16} />
                                                                </button>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )
                )}
            </main>

            {/* Create Category Modal */}
            <Modal
                isOpen={createModalOpen}
                onClose={() => setCreateModalOpen(false)}
                title="Create Metadata Category"
            >
                <form onSubmit={handleCreateCategory} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">Name</label>
                        <input
                            type="text"
                            required
                            className="w-full border rounded-md p-2 bg-background"
                            value={newCategoryName}
                            onChange={e => setNewCategoryName(e.target.value)}
                            placeholder="e.g. Contracts"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium mb-1">Description</label>
                        <textarea
                            className="w-full border rounded-md p-2 bg-background"
                            value={newCategoryDesc}
                            onChange={e => setNewCategoryDesc(e.target.value)}
                            placeholder="Optional description"
                            rows={3}
                        />
                    </div>
                    <div className="flex justify-end gap-2 pt-2">
                        <button
                            type="button"
                            onClick={() => setCreateModalOpen(false)}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
                        >
                            Create
                        </button>
                    </div>
                </form>
            </Modal>

            {/* Delete Category Modal */}
            <Modal
                isOpen={!!deleteCategoryTarget}
                onClose={() => !deletingCategory && setDeleteCategoryTarget(null)}
                title="Delete Category"
            >
                <div className="space-y-4">
                    <p className="text-sm text-muted-foreground">
                        Are you sure you want to delete
                        {' '}
                        <span className="font-medium text-foreground">{deleteCategoryTarget?.name}</span>
                        ? This will delete all attributes and metadata associated with this category.
                    </p>
                    <div className="flex justify-end gap-2 pt-2">
                        <button
                            type="button"
                            onClick={() => setDeleteCategoryTarget(null)}
                            disabled={deletingCategory}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent disabled:opacity-50"
                        >
                            Cancel
                        </button>
                        <button
                            type="button"
                            onClick={confirmDeleteCategory}
                            disabled={deletingCategory}
                            className="px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50"
                        >
                            {deletingCategory ? 'Deleting...' : 'Delete'}
                        </button>
                    </div>
                </div>
            </Modal>

            {/* Add Attribute Modal */}
            <Modal
                isOpen={!!addAttributeCategory}
                onClose={() => setAddAttributeCategory(null)}
                title={`Add Attribute to ${addAttributeCategory?.name}`}
            >
                <form onSubmit={handleCreateAttribute} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">Attribute Name</label>
                        <input
                            type="text"
                            required
                            className="w-full border rounded-md p-2 bg-background"
                            value={newAttrName}
                            onChange={e => setNewAttrName(e.target.value)}
                            placeholder="e.g. Contract Number"
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium mb-1">Type</label>
                            <select
                                className="w-full border rounded-md p-2 bg-background"
                                value={newAttrType}
                                onChange={e => setNewAttrType(e.target.value)}
                            >
                                <option value="text">Text</option>
                                <option value="number">Number</option>
                                <option value="date">Date</option>
                                <option value="boolean">Boolean (Checkbox)</option>
                                <option value="select">Select (Dropdown)</option>
                                <option value="tags">Tags (Array)</option>
                            </select>
                        </div>
                        <div className="flex items-center pt-6">
                            <label className="flex items-center gap-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={newAttrRequired}
                                    onChange={e => setNewAttrRequired(e.target.checked)}
                                    className="rounded border-gray-300"
                                />
                                <span className="text-sm font-medium">Required Field</span>
                            </label>
                        </div>
                    </div>

                    {newAttrType === 'select' && (
                        <div>
                            <label className="block text-sm font-medium mb-1">Options (comma separated)</label>
                            <input
                                type="text"
                                required
                                className="w-full border rounded-md p-2 bg-background"
                                value={newAttrOptions}
                                onChange={e => setNewAttrOptions(e.target.value)}
                                placeholder="Option A, Option B, Option C"
                            />
                        </div>
                    )}

                    <div className="flex justify-end gap-2 pt-2">
                        <button
                            type="button"
                            onClick={() => setAddAttributeCategory(null)}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
                        >
                            Add Attribute
                        </button>
                    </div>
                </form>
            </Modal>

            {/* Edit Attribute Modal */}
            <Modal
                isOpen={!!editAttributeTarget}
                onClose={() => !editingAttribute && setEditAttributeTarget(null)}
                title={`Edit Attribute: ${editAttributeTarget?.name || ''}`}
            >
                <form onSubmit={handleUpdateAttribute} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">Attribute Name</label>
                        <input
                            type="text"
                            required
                            className="w-full border rounded-md p-2 bg-background"
                            value={editAttrName}
                            onChange={(e) => setEditAttrName(e.target.value)}
                            placeholder="e.g. Contract Number"
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium mb-1">Type</label>
                            <select
                                className="w-full border rounded-md p-2 bg-background"
                                value={editAttrType}
                                onChange={(e) => setEditAttrType(e.target.value)}
                            >
                                <option value="text">Text</option>
                                <option value="number">Number</option>
                                <option value="date">Date</option>
                                <option value="boolean">Boolean (Checkbox)</option>
                                <option value="select">Select (Dropdown)</option>
                                <option value="tags">Tags (Array)</option>
                            </select>
                        </div>
                        <div className="flex items-center pt-6">
                            <label className="flex items-center gap-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={editAttrRequired}
                                    onChange={(e) => setEditAttrRequired(e.target.checked)}
                                    className="rounded border-gray-300"
                                />
                                <span className="text-sm font-medium">Required Field</span>
                            </label>
                        </div>
                    </div>

                    {editAttrType === 'select' && (
                        <div>
                            <label className="block text-sm font-medium mb-1">Options (comma separated)</label>
                            <input
                                type="text"
                                required
                                className="w-full border rounded-md p-2 bg-background"
                                value={editAttrOptions}
                                onChange={(e) => setEditAttrOptions(e.target.value)}
                                placeholder="Option A, Option B, Option C"
                            />
                        </div>
                    )}

                    <div className="flex justify-end gap-2 pt-2">
                        <button
                            type="button"
                            onClick={() => setEditAttributeTarget(null)}
                            disabled={editingAttribute}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent disabled:opacity-50"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={editingAttribute || !editAttrName.trim()}
                            className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                        >
                            {editingAttribute && <Loader2 className="animate-spin" size={14} />}
                            Save Changes
                        </button>
                    </div>
                </form>
            </Modal>

            <MetadataLayoutBuilderModal
                isOpen={layoutBuilderOpen}
                onClose={() => setLayoutBuilderOpen(false)}
                categories={categories}
                onSaved={async () => {
                    await loadCategories();
                }}
            />
        </div>
    );
}

