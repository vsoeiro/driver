import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
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
    CheckSquare, Square, Eye, Search, Filter, User, Pencil, BookOpen, Power, Columns3, GripVertical,
    Download, ArrowRightLeft, XCircle, Check, X
} from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import Modal from '../components/Modal';
import BatchMetadataModal from '../components/BatchMetadataModal';
import RemoveMetadataModal from '../components/RemoveMetadataModal';
import MetadataModal from '../components/MetadataModal';
import MoveModal from '../components/MoveModal';
import MetadataLayoutBuilderModal from '../components/MetadataLayoutBuilderModal';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { formatDateOnly, formatDateTime } from '../utils/dateTime';

const ITEMS_PER_PAGE = 50;
const BASE_SORT_OPTIONS = [
    { value: 'modified_at', key: 'modified' },
    { value: 'name', key: 'name' },
    { value: 'size', key: 'size' },
    { value: 'created_at', key: 'created' },
];
const METADATA_TABLE_COLUMNS_STORAGE_PREFIX = 'driver-metadata-table-columns-v1';

const getLibraryDisplayName = (library) => (library?.key === 'comics_core' ? 'Comics' : library?.name);
const getLibraryDescription = (library, t) => {
    if (!library) return '';
    if (library.key === 'comics_core') return t('metadataManager.comicsLibraryDescription');
    return library.description || '';
};


// -- Category Items Table --
const CategoryItemsTable = ({ category, onBack }) => {
    const { t, i18n } = useTranslation();
    const { showToast } = useToast();
    const [items, setItems] = useState([]);
    const [seriesRows, setSeriesRows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [sort, setSort] = useState({ by: 'modified_at', order: 'desc' });
    const [selectedItems, setSelectedItems] = useState(new Set());
    const [lastSelectedIndex, setLastSelectedIndex] = useState(null);
    const [batchModalOpen, setBatchModalOpen] = useState(false);
    const [metadataModalOpen, setMetadataModalOpen] = useState(false);
    const [metadataModalItemId, setMetadataModalItemId] = useState(null);
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
    const debouncedSearchTerm = useDebouncedValue(searchTerm.trim(), 300);
    const [searchScope, setSearchScope] = useState('both');
    const [viewMode, setViewMode] = useState('table');
    const [coverUrlsByItemId, setCoverUrlsByItemId] = useState({});
    const [editingCell, setEditingCell] = useState(null);
    const [editingValue, setEditingValue] = useState('');
    const [savingCellKey, setSavingCellKey] = useState(null);
    const [columnsMenuOpen, setColumnsMenuOpen] = useState(false);
    const columnsMenuRef = useRef(null);
    const resizeStateRef = useRef(null);
    const [draggingColumnId, setDraggingColumnId] = useState(null);
    const [tableColumnOrder, setTableColumnOrder] = useState([]);
    const [tableColumnVisibility, setTableColumnVisibility] = useState({});
    const [tableColumnWidths, setTableColumnWidths] = useState({});
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
                label: t('metadataManager.orderByAttr', { name: attr.name }),
                attributeId: attr.id,
                dataType: attr.data_type,
            })),
        [category.attributes, t]
    );
    const sortOptions = useMemo(
        () => [
            ...BASE_SORT_OPTIONS.map((option) => ({
                ...option,
                label: t(`metadataManager.order.${option.key}`),
            })),
            ...metadataSortOptions,
        ],
        [metadataSortOptions, t]
    );
    const selectedMetadataSort = useMemo(() => {
        if (!sort.by?.startsWith('metadata:')) return null;
        return metadataSortOptions.find((option) => option.value === sort.by) || null;
    }, [sort.by, metadataSortOptions]);

    const { data: accounts = [] } = useQuery({
        queryKey: ['accounts'],
        queryFn: accountsService.getAccounts,
        staleTime: 60000,
    });

    useEffect(() => {
        function handleClickOutside(event) {
            if (metadataMenuRef.current && !metadataMenuRef.current.contains(event.target)) {
                setMetadataMenuOpen(false);
            }
            if (columnsMenuRef.current && !columnsMenuRef.current.contains(event.target)) {
                setColumnsMenuOpen(false);
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
                    <Filter size={16} /> {t('allFiles.filters')}
                </button>

                {isOpen && (
                    <div className="absolute right-0 top-full mt-2 w-80 bg-popover border rounded-md shadow-lg p-4 z-50 space-y-4 max-h-[70vh] overflow-y-auto">
                        <div>
                            <label className="block text-sm font-medium mb-1">{t('allFiles.account')}</label>
                            <select
                                className="w-full border rounded-md p-2 text-sm bg-background"
                                value={localFilters.account_id || ''}
                                onChange={(e) => handleChange('account_id', e.target.value)}
                            >
                                <option value="">{t('allFiles.allAccounts')}</option>
                                {accounts.map(acc => (
                                    <option key={acc.id} value={acc.id}>{acc.email || acc.display_name}</option>
                                ))}
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

                        <div className="border-t pt-3">
                            <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                                {t('metadataManager.categoryAttributes')}
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
                                                    <option value="">{t('metadataManager.any')}</option>
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
                                                    <option value="">{t('metadataManager.any')}</option>
                                                    <option value="true">{t('common.yes')}</option>
                                                    <option value="false">{t('common.no')}</option>
                                                </select>
                                            </div>
                                        ) : attr.data_type === 'number' ? (
                                            <div className="grid grid-cols-2 gap-2">
                                                <input
                                                    type="number"
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.min) ?? ''}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'min', e.target.value)}
                                                    placeholder={t('allFiles.min')}
                                                />
                                                <input
                                                    type="number"
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.max) ?? ''}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'max', e.target.value)}
                                                    placeholder={t('allFiles.max')}
                                                />
                                            </div>
                                        ) : attr.data_type === 'text' || attr.data_type === 'tags' ? (
                                            <div className="grid grid-cols-2 gap-2">
                                                <select
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.op) || 'contains'}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'op', e.target.value)}
                                                >
                                                    <option value="contains">{t('metadataManager.contains')}</option>
                                                    <option value="not_contains">{t('metadataManager.notContains')}</option>
                                                    <option value="eq">=</option>
                                                    <option value="ne">!=</option>
                                                </select>
                                                <input
                                                    type="text"
                                                    className="w-full border rounded-md p-2 text-sm bg-background"
                                                    value={(localFilters.attributes[attr.id]?.value) ?? ''}
                                                    onChange={(e) => handleAttributeConfigChange(attr.id, 'value', e.target.value)}
                                                    placeholder={attr.data_type === 'tags' ? t('metadataManager.tagsPlaceholderShort') : t('metadataManager.filterByAttr', { name: attr.name })}
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
                                                    <option value="">{t('metadataManager.any')}</option>
                                                    <option value="true">{t('common.yes')}</option>
                                                    <option value="false">{t('common.no')}</option>
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
                            <button onClick={clearFilters} className="text-sm text-muted-foreground hover:text-foreground">{t('allFiles.clear')}</button>
                            <button onClick={applyFilters} className="bg-primary text-primary-foreground px-3 py-1.5 rounded-md text-sm font-medium">{t('allFiles.apply')}</button>
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
                q: debouncedSearchTerm,
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
                    q: debouncedSearchTerm,
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
    }, [page, sort.by, sort.order, selectedMetadataSort, category.id, supportsSeriesTracker, viewMode, debouncedSearchTerm, searchScope, filters]);

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
        if (!bytes || bytes === 0) return t('metadataManager.zeroBytes');
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const formatDate = (dateString) => {
        return formatDateTime(dateString, i18n.language);
    };

    const getAttributeValue = (item, attr) => {
        if (!item.metadata?.values) return t('metadataManager.dash');
        const val = item.metadata.values[attr.id];
        if (val === undefined || val === null || val === '') return t('metadataManager.dash');

        if (attr.data_type === 'boolean') return val ? t('common.yes') : t('common.no');
        if (attr.data_type === 'tags') {
            const tags = Array.isArray(val) ? val : parseTagsInput(String(val));
            return tags.length > 0 ? tags.join(', ') : t('metadataManager.dash');
        }
        if (attr.data_type === 'date' && val) {
            return formatDateOnly(val, i18n.language);
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
            showToast(t('metadataManager.attributeUpdatedInline', { name: attr.name }), 'success');
        } catch (error) {
            showToast(error?.response?.data?.detail || t('metadataManager.failedUpdateInline', { name: attr.name }), 'error');
        } finally {
            setSavingCellKey(null);
        }
    };

    const attributes = useMemo(
        () => sortAttributesForCategory(category),
        [category]
    );
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

    const titleAttr = findAttr(libraryView?.gallery?.titleField, t('metadataManager.fallbackTitle'));
    const subtitleAttr = findAttr(libraryView?.gallery?.subtitleField, t('metadataManager.fallbackSeries'));
    const pageCountAttr = findAttr(libraryView?.gallery?.pageCountField, t('metadataManager.fallbackPageCount'));
    const volumeAttr = findAttr(libraryView?.gallery?.volumeField, t('metadataManager.fallbackVolume'));
    const issueNumberAttr = findAttr(libraryView?.gallery?.issueNumberField, t('metadataManager.fallbackIssueNumber'));
    const statusLabel = {
        ongoing: t('metadataManager.status.ongoing'),
        completed: t('metadataManager.status.completed'),
        hiatus: t('metadataManager.status.hiatus'),
        cancelled: t('metadataManager.status.cancelled'),
        unknown: t('metadataManager.status.unknown'),
    };
    const statusClass = {
        ongoing: 'bg-blue-100 text-blue-700',
        completed: 'bg-emerald-100 text-emerald-700',
        hiatus: 'bg-amber-100 text-amber-700',
        cancelled: 'bg-rose-100 text-rose-700',
        unknown: 'bg-zinc-100 text-zinc-700',
    };

    const tableColumnsStorageKey = `${METADATA_TABLE_COLUMNS_STORAGE_PREFIX}:${category.id}`;
    const tableColumnDefs = useMemo(() => {
        const fixed = [
            { id: 'name', label: t('allFiles.columns.name'), width: 280, minWidth: 170, sortKey: 'name' },
            { id: 'account', label: t('allFiles.columns.account'), width: 160, minWidth: 130, sortKey: null },
            { id: 'size', label: t('allFiles.columns.size'), width: 110, minWidth: 90, sortKey: 'size', align: 'right' },
        ];
        const dynamicAttributes = attributes.map((attr) => ({
            id: `attr:${attr.id}`,
            label: attr.name,
            width: 180,
            minWidth: 110,
            sortKey: null,
            attrId: attr.id,
        }));
        const tail = [
            { id: 'modified', label: t('allFiles.columns.modified'), width: 150, minWidth: 130, sortKey: 'modified_at', align: 'right' },
            { id: 'path', label: t('allFiles.columns.path'), width: 260, minWidth: 150, sortKey: null, align: 'right' },
        ];
        return [...fixed, ...dynamicAttributes, ...tail];
    }, [attributes, t]);

    useEffect(() => {
        const defaults = tableColumnDefs;
        const defaultOrder = defaults.map((col) => col.id);
        const defaultVisibility = defaults.reduce((acc, col) => ({ ...acc, [col.id]: true }), {});
        const defaultWidths = defaults.reduce((acc, col) => ({ ...acc, [col.id]: col.width }), {});
        let nextOrder = defaultOrder;
        let nextVisibility = defaultVisibility;
        let nextWidths = defaultWidths;

        try {
            const raw = window.localStorage.getItem(tableColumnsStorageKey);
            if (raw) {
                const parsed = JSON.parse(raw);
                const validIds = new Set(defaultOrder);
                const loadedOrder = Array.isArray(parsed.order) ? parsed.order.filter((id) => validIds.has(id)) : [];
                nextOrder = [...loadedOrder, ...defaultOrder.filter((id) => !loadedOrder.includes(id))];
                if (parsed.visibility && typeof parsed.visibility === 'object') {
                    nextVisibility = { ...defaultVisibility };
                    defaultOrder.forEach((id) => {
                        if (Object.prototype.hasOwnProperty.call(parsed.visibility, id)) {
                            nextVisibility[id] = Boolean(parsed.visibility[id]);
                        }
                    });
                }
                if (parsed.widths && typeof parsed.widths === 'object') {
                    nextWidths = { ...defaultWidths };
                    defaults.forEach((col) => {
                        const candidate = Number(parsed.widths[col.id]);
                        if (Number.isFinite(candidate)) {
                            nextWidths[col.id] = Math.max(col.minWidth, candidate);
                        }
                    });
                }
            }
        } catch {
            // Ignore malformed table preferences
        }

        setTableColumnOrder(nextOrder);
        setTableColumnVisibility(nextVisibility);
        setTableColumnWidths(nextWidths);
    }, [tableColumnsStorageKey, tableColumnDefs]);

    useEffect(() => {
        if (tableColumnOrder.length === 0) return;
        const payload = {
            order: tableColumnOrder,
            visibility: tableColumnVisibility,
            widths: tableColumnWidths,
        };
        window.localStorage.setItem(tableColumnsStorageKey, JSON.stringify(payload));
    }, [tableColumnsStorageKey, tableColumnOrder, tableColumnVisibility, tableColumnWidths]);

    const orderedTableColumns = useMemo(() => {
        if (tableColumnOrder.length === 0) return tableColumnDefs;
        const map = new Map(tableColumnDefs.map((col) => [col.id, col]));
        return tableColumnOrder.map((id) => map.get(id)).filter(Boolean);
    }, [tableColumnDefs, tableColumnOrder]);

    const visibleTableColumns = useMemo(
        () => orderedTableColumns.filter((col) => tableColumnVisibility[col.id] !== false),
        [orderedTableColumns, tableColumnVisibility]
    );

    const gridTemplate = useMemo(() => {
        const dataCols = visibleTableColumns.map(
            (col) => `${Math.max(col.minWidth, tableColumnWidths[col.id] ?? col.width)}px`
        );
        return `40px 40px ${dataCols.join(' ')}`;
    }, [visibleTableColumns, tableColumnWidths]);

    const tableMinWidth = useMemo(() => {
        const fixed = 80;
        const totalColumns = 2 + visibleTableColumns.length;
        const gapPx = Math.max(0, totalColumns - 1) * 16; // gap-4
        const colsWidth = visibleTableColumns.reduce(
            (sum, col) => sum + Math.max(col.minWidth, tableColumnWidths[col.id] ?? col.width),
            0
        );
        return Math.max(980, fixed + colsWidth + gapPx);
    }, [visibleTableColumns, tableColumnWidths]);

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

    const beginResize = (event, column) => {
        event.preventDefault();
        event.stopPropagation();
        const startX = event.clientX;
        const initialWidth = Math.max(column.minWidth, tableColumnWidths[column.id] ?? column.width);
        resizeStateRef.current = { columnId: column.id, startX, initialWidth, minWidth: column.minWidth };

        const onMouseMove = (moveEvent) => {
            if (!resizeStateRef.current) return;
            const nextWidth = resizeStateRef.current.initialWidth + (moveEvent.clientX - resizeStateRef.current.startX);
            setTableColumnWidths((prev) => ({
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
        setTableColumnOrder((prev) => {
            const withoutDragged = prev.filter((id) => id !== draggingColumnId);
            const targetIndex = withoutDragged.indexOf(targetId);
            if (targetIndex < 0) return prev;
            const next = [...withoutDragged];
            next.splice(targetIndex, 0, draggingColumnId);
            return next;
        });
        setDraggingColumnId(null);
    };

    const getSelectedObjects = () => items.filter(i => selectedItems.has(i.id));
    const singleSelectedItem = selectedItems.size === 1
        ? items.find((i) => i.id === Array.from(selectedItems)[0]) || null
        : null;
    const metadataNavigationItems = useMemo(() => items, [items]);
    const currentMetadataItemIndex = useMemo(
        () => metadataNavigationItems.findIndex((candidate) => candidate.id === metadataModalItemId),
        [metadataNavigationItems, metadataModalItemId]
    );
    const metadataModalItem = currentMetadataItemIndex >= 0
        ? metadataNavigationItems[currentMetadataItemIndex]
        : singleSelectedItem;
    const moveTargetItem = singleSelectedItem
        ? { ...singleSelectedItem, id: singleSelectedItem.item_id }
        : null;
    const selectedItemsForBatchEdit = getSelectedObjects().map((item) => ({
        ...item,
        item_id: item.item_id || item.id,
    }));

    const openSingleMetadataModal = () => {
        if (!singleSelectedItem) return;
        setMetadataModalItemId(singleSelectedItem.id);
        setMetadataModalOpen(true);
    };

    const handleMetadataPrevious = () => {
        if (currentMetadataItemIndex <= 0) return;
        const previousItem = metadataNavigationItems[currentMetadataItemIndex - 1];
        if (!previousItem) return;
        setMetadataModalItemId(previousItem.id);
        setSelectedItems(new Set([previousItem.id]));
    };

    const handleMetadataNext = () => {
        if (currentMetadataItemIndex < 0 || currentMetadataItemIndex >= metadataNavigationItems.length - 1) return;
        const nextItem = metadataNavigationItems[currentMetadataItemIndex + 1];
        if (!nextItem) return;
        setMetadataModalItemId(nextItem.id);
        setSelectedItems(new Set([nextItem.id]));
    };

    const renderTableCell = (item, column) => {
        if (column.id === 'name') {
            return <div className="min-w-0 truncate font-medium" title={item.name}>{item.name}</div>;
        }
        if (column.id === 'account') {
            return (
                <div className="flex items-center gap-1 text-sm text-foreground min-w-0">
                    <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                        <User size={12} className="text-primary" />
                    </div>
                    <span className="truncate" title={getAccountName(item.account_id)}>
                        {getAccountName(item.account_id)}
                    </span>
                </div>
            );
        }
        if (column.id === 'size') {
            return <div className="text-right text-sm text-muted-foreground tabular-nums">{formatSize(item.size)}</div>;
        }
        if (column.id === 'modified') {
            return <div className="text-right text-sm text-muted-foreground tabular-nums">{formatDate(item.modified_at)}</div>;
        }
        if (column.id === 'path') {
            return <div className="text-right text-xs text-muted-foreground truncate" title={item.path}>{item.path}</div>;
        }
        if (column.id.startsWith('attr:')) {
            const attr = attributes.find((candidate) => `attr:${candidate.id}` === column.id);
            if (!attr) return null;
            const isEditing = editingCell?.itemId === item.id && editingCell?.attrId === attr.id;
            const cellKey = `${item.id}:${attr.id}`;
            const isSaving = savingCellKey === cellKey;
            const readOnly = isReadOnlyAttribute(attr);
            const displayValue = getAttributeValue(item, attr);

            return (
                <div
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
                                    <option value="true">{t('common.yes')}</option>
                                    <option value="false">{t('common.no')}</option>
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
                                    placeholder={t('allFiles.tagsPlaceholder')}
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
                                title={t('common.confirm')}
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
                                title={t('common.cancel')}
                            >
                                <X size={12} />
                            </button>
                        </div>
                    ) : (
                        <div className={`truncate ${readOnly ? 'text-muted-foreground' : ''}`}>{displayValue}</div>
                    )}
                </div>
            );
        }
        return null;
    };

    const handleDownload = async () => {
        const selectedFiles = getSelectedObjects().filter((item) => item.item_type === 'file');
        for (const file of selectedFiles) {
            try {
                const url = await driveService.getDownloadUrl(file.account_id, file.item_id);
                window.open(url, '_blank');
            } catch (error) {
                console.error(`Failed to download ${file.name}`, error);
                showToast(`${t('allFiles.failedDownload')} ${file.name}`, 'error');
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
            await fetchItems();
        } catch (error) {
            showToast(error?.response?.data?.detail || t('allFiles.failedRename'), 'error');
        } finally {
            setRenameSaving(false);
        }
    };

    const getAccountName = (accountId) => {
        const acc = accounts.find(a => a.id === accountId);
        return acc ? (acc.email || acc.display_name) : (accountId ? String(accountId).slice(0, 8) : '-');
    };

    const searchPlaceholders = {
        name: t('allFiles.searchByTitle'),
        path: t('allFiles.searchByPath'),
        both: t('allFiles.searchByTitlePath'),
    };

    return (
        <>
            {/* Unified command bar */}
            <div className="surface-card relative z-[80] mb-4 overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
                <div className="flex items-center gap-3">
                    <button
                        onClick={onBack}
                        className="ghost-icon-button"
                        title={t('metadataManager.backToCategories')}
                    >
                        <ArrowLeft size={18} />
                    </button>
                    <div>
                        <h1 className="text-lg font-semibold text-foreground">{category.name}</h1>
                        <p className="text-xs text-muted-foreground">{t('allFiles.itemsCount', { count: total })}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {(supportsGallery || supportsSeriesTracker) && (
                        <div className="inline-flex items-center rounded-lg border border-border/70 overflow-hidden bg-muted/35">
                            <button
                                onClick={() => setViewMode('table')}
                                className={`px-3 py-1.5 text-sm ${viewMode === 'table' ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'}`}
                            >
                                {t('metadataManager.table')}
                            </button>
                            <button
                                onClick={() => setViewMode('gallery')}
                                className={`px-3 py-1.5 text-sm ${viewMode === 'gallery' ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'}`}
                            >
                                {t('metadataManager.gallery')}
                            </button>
                            {supportsSeriesTracker && (
                                <button
                                    onClick={() => setViewMode('series_tracker')}
                                    className={`px-3 py-1.5 text-sm ${viewMode === 'series_tracker' ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'}`}
                                >
                                    {t('metadataManager.series')}
                                </button>
                            )}
                        </div>
                    )}
                    <select
                        className="input-shell px-2 py-1.5 text-sm"
                        value={searchScope}
                        onChange={(e) => setSearchScope(e.target.value)}
                    >
                        <option value="both">{t('allFiles.titlePath')}</option>
                        <option value="name">{t('allFiles.title')}</option>
                        <option value="path">{t('allFiles.path')}</option>
                    </select>
                    <select
                        className="input-shell px-2 py-1.5 text-sm"
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
                        className="input-shell px-2 py-1.5 text-sm"
                        value={sort.order}
                        onChange={(e) => {
                            setSort((prev) => ({ ...prev, order: e.target.value }));
                            setPage(1);
                        }}
                    >
                        <option value="desc">{t('similarFiles.desc')}</option>
                        <option value="asc">{t('similarFiles.asc')}</option>
                    </select>
                    <div className="relative">
                        <Search className="absolute left-2 top-1.5 text-muted-foreground" size={16} />
                        <input
                            type="text"
                            placeholder={searchPlaceholders[searchScope]}
                            className="input-shell pl-8 pr-4 py-1.5 text-sm w-72"
                            value={searchTerm}
                            onChange={(e) => {
                                setSearchTerm(e.target.value);
                                setPage(1);
                            }}
                        />
                    </div>
                    <CategoryFilterBar
                        onFilter={(newFilters) => {
                            setFilters(newFilters);
                            setPage(1);
                        }}
                        currentFilters={filters}
                    />
                    {viewMode === 'table' && (
                        <div className="relative z-[140]" ref={columnsMenuRef}>
                            <button
                                onClick={() => setColumnsMenuOpen((prev) => !prev)}
                                className="flex items-center gap-2 px-3 py-2 border rounded-md text-sm font-medium hover:bg-accent"
                            >
                                <Columns3 size={16} />
                                {t('allFiles.columnsTitle')}
                            </button>
                            {columnsMenuOpen && (
                                <div className="absolute right-0 top-full mt-2 w-60 bg-popover border rounded-md shadow-lg p-2 z-[220] space-y-1 max-h-72 overflow-auto">
                                    {orderedTableColumns.map((column) => (
                                        <label key={column.id} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-accent cursor-pointer text-sm">
                                            <input
                                                type="checkbox"
                                                checked={tableColumnVisibility[column.id] !== false}
                                                onChange={(event) => {
                                                    const checked = event.target.checked;
                                                    setTableColumnVisibility((prev) => {
                                                        const next = { ...prev, [column.id]: checked };
                                                        const visibleCount = Object.values(next).filter(Boolean).length;
                                                        if (visibleCount === 0) {
                                                            next[column.id] = true;
                                                        }
                                                        return next;
                                                    });
                                                }}
                                            />
                                            <span className="truncate">{column.label}</span>
                                        </label>
                                    ))}
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
                                                openSingleMetadataModal();
                                            } else {
                                                setBatchModalOpen(true);
                                            }
                                            setMetadataMenuOpen(false);
                                        }}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2"
                                    >
                                        <Database size={14} /> {t('allFiles.editMetadata')}
                                    </button>
                                    <button
                                        onClick={() => {
                                            openRenameModal();
                                            setMetadataMenuOpen(false);
                                        }}
                                        disabled={selectedItems.size !== 1}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 disabled:opacity-50"
                                    >
                                        <Pencil size={14} /> {t('allFiles.rename')}
                                    </button>
                                    <button
                                        onClick={() => {
                                            setRemoveModalOpen(true);
                                            setMetadataMenuOpen(false);
                                        }}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-accent flex items-center gap-2 text-destructive hover:text-destructive"
                                    >
                                        <XCircle size={14} /> {t('allFiles.removeMetadata')}
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
                        title={t('allFiles.delete')}
                    >
                        <Trash2 size={16} /> <span className="hidden sm:inline">{t('allFiles.delete')}</span>
                    </button>
                </div>

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

            {/* Content */}
            <main className="flex-1 overflow-auto">
                {loading ? (
                    <div className="flex justify-center p-12">
                        <Loader2 className="animate-spin text-primary" size={32} />
                    </div>
                ) : (viewMode === 'series_tracker' && supportsSeriesTracker ? seriesRows.length === 0 : items.length === 0) ? (
                    <div className="empty-state">
                        <div className="empty-state-title">{t('metadataManager.noItemsInCategory')}</div>
                        <p className="empty-state-text">{t('metadataManager.noItemsInCategoryHelp')}</p>
                    </div>
                ) : (
                    viewMode === 'series_tracker' && supportsSeriesTracker ? (
                        <div className="space-y-4">
                            {seriesRows.length === 0 ? (
                                <div className="surface-card p-6 text-sm text-muted-foreground">
                                    {t('metadataManager.seriesTrackerNeedsSeries')}
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
                                        <div key={seriesRow.series_name} className="surface-card p-4">
                                            <div className="flex items-center justify-between gap-3 mb-3">
                                                <div className="min-w-0">
                                                    <h3 className="font-semibold truncate">{seriesRow.series_name}</h3>
                                                    <p className="text-xs text-muted-foreground">
                                                        {t('metadataManager.seriesTrackerSummary', {
                                                            items: seriesRow.total_items,
                                                            volumes: ownedVolumes.length,
                                                        })}
                                                    </p>
                                                </div>
                                                <div className={`px-2 py-1 rounded text-xs font-medium ${statusClass[statusKey]}`}>
                                                    {statusLabel[statusKey]}
                                                </div>
                                            </div>

                                            <div className="space-y-3">
                                                <div>
                                                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                                                        <span>{t('metadataManager.volumes')}</span>
                                                        <span>
                                                            {maxVolumes > 0
                                                                ? t('metadataManager.maxWithCount', { count: maxVolumes })
                                                                : t('metadataManager.maxNotSet')}
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
                                                                        title={t('metadataManager.volumeTitle', {
                                                                            volume: volumeNo,
                                                                            status: owned ? t('metadataManager.owned') : t('metadataManager.missing'),
                                                                        })}
                                                                        className={`h-4 w-3 rounded-sm border ${owned ? 'bg-blue-500 border-blue-500' : 'bg-white border-zinc-300'}`}
                                                                    />
                                                                );
                                                            })}
                                                        </div>
                                                    ) : (
                                                        <div className="text-xs text-muted-foreground">{t('metadataManager.setMaxVolumesHint')}</div>
                                                    )}
                                                </div>

                                                {shownIssues > 0 && (
                                                    <div className="space-y-2">
                                                        <div className="text-xs text-muted-foreground">
                                                            {t('metadataManager.issuesPerVolumeMax', { max: maxIssues })}
                                                        </div>
                                                        {ownedVolumes
                                                            .sort((a, b) => a - b)
                                                            .slice(0, 10)
                                                            .map((volumeNo) => {
                                                                const issues = new Set(issuesByVolume[String(volumeNo)] || []);
                                                                return (
                                                                    <div key={`${seriesRow.series_name}-issues-${volumeNo}`} className="flex items-center gap-2">
                                                                        <div className="w-10 text-xs text-muted-foreground">
                                                                            {t('metadataManager.volumeShort', { volume: volumeNo })}
                                                                        </div>
                                                                        <div className="flex flex-wrap gap-1">
                                                                            {Array.from({ length: shownIssues }, (_, idx) => {
                                                                                const issueNo = idx + 1;
                                                                                const owned = issues.has(issueNo);
                                                                                return (
                                                                                    <div
                                                                                        key={`${seriesRow.series_name}-vol-${volumeNo}-issue-${issueNo}`}
                                                                                        title={t('metadataManager.volumeIssueTitle', {
                                                                                            volume: volumeNo,
                                                                                            issue: issueNo,
                                                                                            status: owned ? t('metadataManager.owned') : t('metadataManager.missing'),
                                                                                        })}
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
                        <div className="surface-card p-4">
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
                                                isSelected ? 'ring-2 ring-primary border-primary/40' : 'hover:border-primary/40 hover:-translate-y-[1px]'
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
                        <div className="surface-card select-none overflow-hidden">
                            <div className="overflow-x-auto">
                                <div style={{ minWidth: `${tableMinWidth}px` }}>
                                    {/* Table Header */}
                                    <div
                                        className="gap-4 p-3 border-b border-border/70 bg-muted/45 text-xs font-medium text-muted-foreground uppercase tracking-wider items-center sticky top-0 z-10"
                                        style={{ display: 'grid', gridTemplateColumns: gridTemplate, minWidth: `${tableMinWidth}px` }}
                                    >
                                        <div className="flex justify-center">
                                            <button onClick={toggleSelectAll}>
                                                {selectedItems.size === items.length && items.length > 0 ? <CheckSquare size={16} /> : <Square size={16} />}
                                            </button>
                                        </div>
                                        <div></div>
                                        {visibleTableColumns.map((column) => (
                                            <div
                                                key={column.id}
                                                draggable
                                                onDragStart={() => setDraggingColumnId(column.id)}
                                                onDragOver={(event) => event.preventDefault()}
                                                onDrop={() => handleColumnDrop(column.id)}
                                                className={`relative flex items-center gap-1 truncate ${column.align === 'right' ? 'justify-end text-right' : ''}`}
                                            >
                                                <button
                                                    type="button"
                                                    className={`inline-flex items-center gap-1 hover:text-foreground ${column.sortKey ? '' : 'cursor-default'}`}
                                                    onClick={() => column.sortKey && handleSort(column.sortKey)}
                                                >
                                                    <GripVertical size={12} className="opacity-45" />
                                                    {column.label}
                                                    {column.sortKey ? renderSortIcon(column.sortKey) : null}
                                                </button>
                                                <div
                                                    className="absolute right-[-8px] top-0 h-full w-3 cursor-col-resize"
                                                    onMouseDown={(event) => beginResize(event, column)}
                                                />
                                            </div>
                                        ))}
                                    </div>

                                    {/* Table Rows */}
                                    <div className="divide-y">
                                        {items.map((item, index) => {
                                            const isFolder = item.item_type === 'folder';
                                            const isSelected = selectedItems.has(item.id);
                                            return (
                                                <div
                                                    key={item.id}
                                                    className={`gap-4 p-3 items-center hover:bg-accent/35 transition-colors ${isSelected ? 'bg-muted/45' : ''}`}
                                                    style={{ display: 'grid', gridTemplateColumns: gridTemplate, minWidth: `${tableMinWidth}px` }}
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
                                                    {visibleTableColumns.map((column) => (
                                                        <div key={column.id}>
                                                            {renderTableCell(item, column)}
                                                        </div>
                                                    ))}
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
                onClose={() => {
                    setMetadataModalOpen(false);
                    setMetadataModalItemId(null);
                }}
                item={metadataModalItem}
                accountId={metadataModalItem?.account_id}
                hasPrevious={currentMetadataItemIndex > 0}
                hasNext={currentMetadataItemIndex >= 0 && currentMetadataItemIndex < metadataNavigationItems.length - 1}
                onPrevious={handleMetadataPrevious}
                onNext={handleMetadataNext}
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
                title={t('allFiles.deleteTitle', { count: selectedItems.size })}
            >
                <div className="space-y-4">
                    <p>{t('allFiles.deleteConfirm')}</p>
                    <div className="flex justify-end gap-2">
                        <button
                            onClick={() => setDeleteModalOpen(false)}
                            disabled={actionLoading}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent disabled:opacity-50"
                        >
                            {t('common.cancel')}
                        </button>
                        <button
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
        </>
    );
};


// -- Main Page --
export default function MetadataManager() {
    const [activeView, setActiveView] = useState('metadata');
    const [expandedCategory, setExpandedCategory] = useState(null);
    const [viewingCategory, setViewingCategory] = useState(null);
    const [togglingLibraryKey, setTogglingLibraryKey] = useState(null);
    const { t } = useTranslation();
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

    const {
        data: categories = [],
        isLoading: loading,
        error: categoriesError,
        refetch: refetchCategories,
    } = useQuery({
        queryKey: ['metadata-category-stats'],
        queryFn: metadataService.getCategoryStats,
        staleTime: 30000,
    });
    const {
        data: libraries = [],
        isLoading: librariesLoading,
        error: librariesError,
        refetch: refetchLibraries,
    } = useQuery({
        queryKey: ['metadata-libraries'],
        queryFn: metadataService.listMetadataLibraries,
        staleTime: 30000,
    });

    useEffect(() => {
        if (categoriesError) {
            showToast(t('metadataManager.failedLoadCategories'), 'error');
        }
    }, [categoriesError, showToast, t]);

    useEffect(() => {
        if (librariesError) {
            showToast(t('metadataManager.failedLoadLibraries'), 'error');
        }
    }, [librariesError, showToast, t]);

    const knownLibraries = useMemo(
        () => (
            libraries.length > 0
                ? libraries
                : [{ key: 'comics_core', name: 'Comics', description: 'Managed comics metadata schema.', is_active: false }]
        ),
        [libraries]
    );

    const toggleLibrary = async (library) => {
        try {
            setTogglingLibraryKey(library.key);
            const libraryName = getLibraryDisplayName(library);
            if (library.is_active) {
                await metadataService.deactivateMetadataLibrary(library.key);
                showToast(t('metadataManager.libraryDisabled', { name: libraryName }), 'success');
            } else {
                await metadataService.activateMetadataLibrary(library.key);
                showToast(t('metadataManager.libraryEnabled', { name: libraryName }), 'success');
            }
            await Promise.all([refetchLibraries(), refetchCategories()]);
        } catch (error) {
            const message = error?.response?.data?.detail || t('metadataManager.failedUpdateLibrary');
            showToast(message, 'error');
        } finally {
            setTogglingLibraryKey(null);
        }
    };

    const handleCreateCategory = async (e) => {
        e.preventDefault();
        try {
            await metadataService.createCategory(newCategoryName, newCategoryDesc);
            showToast(t('metadataManager.categoryCreated'), 'success');
            setCreateModalOpen(false);
            setNewCategoryName('');
            setNewCategoryDesc('');
            refetchCategories();
        } catch (error) {
            showToast(error.message || t('metadataManager.failedCreateCategory'), 'error');
        }
    };

    const openDeleteCategoryModal = (category, e) => {
        e.stopPropagation();
        if (category.is_locked || category.managed_by_plugin) {
            showToast(t('metadataManager.libraryManagedCategoryDeleteError'), 'error');
            return;
        }
        setDeleteCategoryTarget(category);
    };

    const confirmDeleteCategory = async () => {
        if (!deleteCategoryTarget) return;
        setDeletingCategory(true);
        try {
            await metadataService.deleteCategory(deleteCategoryTarget.id);
            showToast(t('metadataManager.categoryDeleted'), 'success');
            setDeleteCategoryTarget(null);
            await refetchCategories();
        } catch (error) {
            showToast(t('metadataManager.failedDeleteCategory'), 'error');
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

            showToast(t('metadataManager.attributeAdded'), 'success');
            setAddAttributeCategory(null);
            setNewAttrName('');
            setNewAttrType('text');
            setNewAttrOptions('');
            setNewAttrRequired(false);
            refetchCategories();
        } catch (error) {
            showToast(t('metadataManager.failedAddAttribute'), 'error');
        }
    };

    const handleDeleteAttribute = async (attr) => {
        if (attr.is_locked || attr.managed_by_plugin) {
            showToast(t('metadataManager.libraryManagedAttributeDeleteError'), 'error');
            return;
        }
        if (!window.confirm(t('metadataManager.deleteAttributeConfirm'))) return;
        try {
            await metadataService.deleteAttribute(attr.id);
            showToast(t('metadataManager.attributeDeleted'), 'success');
            refetchCategories();
        } catch (error) {
            showToast(t('metadataManager.failedDeleteAttribute'), 'error');
        }
    };

    const openEditAttributeModal = (attr) => {
        if (attr.is_locked || attr.managed_by_plugin) {
            showToast(t('metadataManager.libraryManagedAttributeEditError'), 'error');
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

            showToast(t('metadataManager.attributeUpdated'), 'success');
            setEditAttributeTarget(null);
            await refetchCategories();
        } catch (error) {
            showToast(error?.response?.data?.detail || t('metadataManager.failedUpdateAttribute'), 'error');
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
            <div className="app-page">
                <CategoryItemsTable
                    category={viewingCategory}
                    onBack={() => { setViewingCategory(null); refetchCategories(); }}
                />
            </div>
        );
    }

    return (
        <div className="app-page">
            {/* Header */}
            <div className="page-header flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                    <h1 className="page-title">{t('metadataManager.title')}</h1>
                    <span className="status-chip">
                        {activeView === 'metadata'
                            ? t('metadataManager.categoriesCount', { count: categories.length })
                            : t('metadataManager.librariesCount', { count: knownLibraries.length })}
                    </span>
                    <div className="inline-flex items-center gap-1 rounded-lg border border-border/70 p-1 bg-muted/35">
                        <button
                            type="button"
                            onClick={() => setActiveView('metadata')}
                            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                                activeView === 'metadata'
                                    ? 'bg-primary text-primary-foreground'
                                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                            }`}
                        >
                            {t('metadataManager.metadataTab')}
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
                            {t('metadataManager.librariesTab')}
                        </button>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {activeView === 'metadata' && (
                        <>
                            <button
                                onClick={() => setLayoutBuilderOpen(true)}
                                disabled={categories.length === 0}
                                className="btn-refresh disabled:opacity-40"
                            >
                                {t('metadataManager.formLayout')}
                            </button>
                            <button
                                onClick={() => setCreateModalOpen(true)}
                                className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-lg shadow-primary/20 transition-transform hover:-translate-y-[1px] hover:bg-primary/92"
                            >
                                <Plus size={16} /> {t('metadataManager.newCategory')}
                            </button>
                        </>
                    )}
                </div>
            </div>

            {/* Content */}
            <main className="flex-1 overflow-auto">
                {activeView === 'libraries' ? (
                    <section className="surface-card p-4">
                        <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                                <h2 className="text-base font-semibold text-foreground">{t('metadataManager.metadataLibraries')}</h2>
                                <span className="status-chip">
                                    {t('metadataManager.availableCount', { count: knownLibraries.length })}
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
                                    <div key={library.key} className="rounded-xl border border-border/70 bg-background p-3 flex items-center justify-between gap-3">
                                        <div className="flex items-start gap-3 min-w-0">
                                            <div className="p-2 rounded-md bg-primary/10 text-primary">
                                                <BookOpen size={16} />
                                            </div>
                                            <div className="min-w-0">
                                                <div className="font-semibold">{getLibraryDisplayName(library)}</div>
                                                {library.key !== 'comics_core' && (
                                                    <div className="text-xs text-muted-foreground">{library.key}</div>
                                                )}
                                                {getLibraryDescription(library, t) && (
                                                    <p className="text-sm text-muted-foreground mt-1">{getLibraryDescription(library, t)}</p>
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
                                            {library.is_active ? t('metadataManager.disable') : t('metadataManager.enable')}
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
                        <div className="empty-state">
                            <div className="empty-state-icon">
                                <Database className="h-6 w-6" />
                            </div>
                            <h3 className="empty-state-title">{t('metadataManager.noCategories')}</h3>
                            <p className="empty-state-text">{t('metadataManager.noCategoriesHelp')}</p>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {categories.map(cat => (
                                <div key={cat.id} className="surface-card overflow-hidden">
                                    {/* Category Header */}
                                    <div
                                        className="p-4 flex items-center justify-between cursor-pointer hover:bg-accent/40 transition-colors"
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
                                                    {t('metadataManager.itemsCount', { count: cat.item_count })}
                                                </span>
                                                <span className="bg-secondary text-secondary-foreground px-2.5 py-1 rounded-full text-xs font-medium flex items-center gap-1.5">
                                                    <Tag size={12} />
                                                    {t('metadataManager.attrsCount', { count: cat.attributes.length })}
                                                </span>
                                            </div>
                                            <button
                                                onClick={(e) => { e.stopPropagation(); setViewingCategory(cat); }}
                                                className="p-2 hover:bg-primary/10 text-muted-foreground hover:text-primary rounded-md transition-colors"
                                                title={t('metadataManager.viewItemsInCategory')}
                                            >
                                                <Eye size={18} />
                                            </button>
                                            <button
                                                onClick={(e) => openDeleteCategoryModal(cat, e)}
                                                disabled={cat.is_locked || cat.managed_by_plugin}
                                                className="p-2 hover:bg-destructive/10 text-muted-foreground hover:text-destructive rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                                                title={t('metadataManager.deleteCategory')}
                                            >
                                                <Trash2 size={18} />
                                            </button>
                                        </div>
                                    </div>

                                    {/* Expanded Attributes */}
                                    {expandedCategory === cat.id && (
                                        <div className="p-4 border-t bg-muted/20">
                                            <div className="flex justify-between items-center mb-4">
                                                <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">{t('metadataManager.attributes')}</h4>
                                                <button
                                                    onClick={() => setAddAttributeCategory(cat)}
                                                    className="text-sm text-primary hover:underline flex items-center gap-1"
                                                >
                                                    <Plus size={14} /> {t('metadataManager.addAttribute')}
                                                </button>
                                            </div>

                                            {cat.attributes.length === 0 ? (
                                                <p className="text-sm text-muted-foreground italic">{t('metadataManager.noAttributes')}</p>
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
                                                                    <div className="text-xs text-amber-600 font-medium">{t('metadataManager.required')}</div>
                                                                )}
                                                                {attr.data_type === 'select' && attr.options?.options && (
                                                                    <div className="text-xs text-muted-foreground">
                                                                        {t('metadataManager.optionsLabel')}: {getSelectOptions(attr.options).join(', ')}
                                                                    </div>
                                                                )}
                                                            </div>
                                                            <div className="flex items-center gap-1">
                                                                <button
                                                                    onClick={() => openEditAttributeModal(attr)}
                                                                    disabled={attr.is_locked || attr.managed_by_plugin}
                                                                    className="text-muted-foreground hover:text-primary p-1 rounded disabled:opacity-40 disabled:cursor-not-allowed"
                                                                    title={t('metadataManager.editAttribute')}
                                                                >
                                                                    <Pencil size={16} />
                                                                </button>
                                                                <button
                                                                    onClick={() => handleDeleteAttribute(attr)}
                                                                    disabled={attr.is_locked || attr.managed_by_plugin}
                                                                    className="text-muted-foreground hover:text-destructive p-1 rounded disabled:opacity-40 disabled:cursor-not-allowed"
                                                                    title={t('metadataManager.deleteAttribute')}
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
                title={t('metadataManager.createCategoryTitle')}
            >
                <form onSubmit={handleCreateCategory} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">{t('metadataManager.name')}</label>
                        <input
                            type="text"
                            required
                            className="w-full border rounded-md p-2 bg-background"
                            value={newCategoryName}
                            onChange={e => setNewCategoryName(e.target.value)}
                            placeholder={t('metadataManager.categoryExample')}
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium mb-1">{t('metadataManager.description')}</label>
                        <textarea
                            className="w-full border rounded-md p-2 bg-background"
                            value={newCategoryDesc}
                            onChange={e => setNewCategoryDesc(e.target.value)}
                            placeholder={t('metadataManager.optionalDescription')}
                            rows={3}
                        />
                    </div>
                    <div className="flex justify-end gap-2 pt-2">
                        <button
                            type="button"
                            onClick={() => setCreateModalOpen(false)}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent"
                        >
                            {t('common.cancel')}
                        </button>
                        <button
                            type="submit"
                            className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
                        >
                            {t('metadataManager.create')}
                        </button>
                    </div>
                </form>
            </Modal>

            {/* Delete Category Modal */}
            <Modal
                isOpen={!!deleteCategoryTarget}
                onClose={() => !deletingCategory && setDeleteCategoryTarget(null)}
                title={t('metadataManager.deleteCategory')}
            >
                <div className="space-y-4">
                    <p className="text-sm text-muted-foreground">
                        {t('metadataManager.deleteCategoryConfirmPrefix')}
                        {' '}
                        <span className="font-medium text-foreground">{deleteCategoryTarget?.name}</span>
                        {t('metadataManager.deleteCategoryConfirmSuffix')}
                    </p>
                    <div className="flex justify-end gap-2 pt-2">
                        <button
                            type="button"
                            onClick={() => setDeleteCategoryTarget(null)}
                            disabled={deletingCategory}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent disabled:opacity-50"
                        >
                            {t('common.cancel')}
                        </button>
                        <button
                            type="button"
                            onClick={confirmDeleteCategory}
                            disabled={deletingCategory}
                            className="px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50"
                        >
                            {deletingCategory ? t('metadataManager.deleting') : t('allFiles.delete')}
                        </button>
                    </div>
                </div>
            </Modal>

            {/* Add Attribute Modal */}
            <Modal
                isOpen={!!addAttributeCategory}
                onClose={() => setAddAttributeCategory(null)}
                title={t('metadataManager.addAttributeTo', { name: addAttributeCategory?.name || '' })}
            >
                <form onSubmit={handleCreateAttribute} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">{t('metadataManager.attributeName')}</label>
                        <input
                            type="text"
                            required
                            className="w-full border rounded-md p-2 bg-background"
                            value={newAttrName}
                            onChange={e => setNewAttrName(e.target.value)}
                            placeholder={t('metadataManager.attributeExample')}
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium mb-1">{t('metadataManager.type')}</label>
                            <select
                                className="w-full border rounded-md p-2 bg-background"
                                value={newAttrType}
                                onChange={e => setNewAttrType(e.target.value)}
                            >
                                <option value="text">{t('metadataManager.typeText')}</option>
                                <option value="number">{t('metadataManager.typeNumber')}</option>
                                <option value="date">{t('metadataManager.typeDate')}</option>
                                <option value="boolean">{t('metadataManager.typeBoolean')}</option>
                                <option value="select">{t('metadataManager.typeSelect')}</option>
                                <option value="tags">{t('metadataManager.typeTags')}</option>
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
                                <span className="text-sm font-medium">{t('metadataManager.requiredField')}</span>
                            </label>
                        </div>
                    </div>

                    {newAttrType === 'select' && (
                        <div>
                            <label className="block text-sm font-medium mb-1">{t('metadataManager.optionsCommaSeparated')}</label>
                            <input
                                type="text"
                                required
                                className="w-full border rounded-md p-2 bg-background"
                                value={newAttrOptions}
                                onChange={e => setNewAttrOptions(e.target.value)}
                                placeholder={t('metadataManager.optionsExample')}
                            />
                        </div>
                    )}

                    <div className="flex justify-end gap-2 pt-2">
                        <button
                            type="button"
                            onClick={() => setAddAttributeCategory(null)}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent"
                        >
                            {t('common.cancel')}
                        </button>
                        <button
                            type="submit"
                            className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
                        >
                            {t('metadataManager.addAttribute')}
                        </button>
                    </div>
                </form>
            </Modal>

            {/* Edit Attribute Modal */}
            <Modal
                isOpen={!!editAttributeTarget}
                onClose={() => !editingAttribute && setEditAttributeTarget(null)}
                title={t('metadataManager.editAttributeTitle', { name: editAttributeTarget?.name || '' })}
            >
                <form onSubmit={handleUpdateAttribute} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">{t('metadataManager.attributeName')}</label>
                        <input
                            type="text"
                            required
                            className="w-full border rounded-md p-2 bg-background"
                            value={editAttrName}
                            onChange={(e) => setEditAttrName(e.target.value)}
                            placeholder={t('metadataManager.attributeExample')}
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium mb-1">{t('metadataManager.type')}</label>
                            <select
                                className="w-full border rounded-md p-2 bg-background"
                                value={editAttrType}
                                onChange={(e) => setEditAttrType(e.target.value)}
                            >
                                <option value="text">{t('metadataManager.typeText')}</option>
                                <option value="number">{t('metadataManager.typeNumber')}</option>
                                <option value="date">{t('metadataManager.typeDate')}</option>
                                <option value="boolean">{t('metadataManager.typeBoolean')}</option>
                                <option value="select">{t('metadataManager.typeSelect')}</option>
                                <option value="tags">{t('metadataManager.typeTags')}</option>
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
                                <span className="text-sm font-medium">{t('metadataManager.requiredField')}</span>
                            </label>
                        </div>
                    </div>

                    {editAttrType === 'select' && (
                        <div>
                            <label className="block text-sm font-medium mb-1">{t('metadataManager.optionsCommaSeparated')}</label>
                            <input
                                type="text"
                                required
                                className="w-full border rounded-md p-2 bg-background"
                                value={editAttrOptions}
                                onChange={(e) => setEditAttrOptions(e.target.value)}
                                placeholder={t('metadataManager.optionsExample')}
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
                            {t('common.cancel')}
                        </button>
                        <button
                            type="submit"
                            disabled={editingAttribute || !editAttrName.trim()}
                            className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                        >
                            {editingAttribute && <Loader2 className="animate-spin" size={14} />}
                            {t('allFiles.saveChanges')}
                        </button>
                    </div>
                </form>
            </Modal>

            <MetadataLayoutBuilderModal
                isOpen={layoutBuilderOpen}
                onClose={() => setLayoutBuilderOpen(false)}
                categories={categories}
                onSaved={async () => {
                    await refetchCategories();
                }}
            />
        </div>
    );
}


