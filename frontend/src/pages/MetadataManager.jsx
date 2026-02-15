import React, { useState, useEffect } from 'react';
import { metadataService } from '../services/metadata';
import { itemsService } from '../services/items';
import { accountsService } from '../services/accounts';
import {
    Plus, Trash2, ChevronRight, ChevronDown, ChevronLeft,
    Database, Loader2, Tag, Hash, ArrowLeft,
    File, Folder, ArrowUpDown, ArrowUp, ArrowDown,
    CheckSquare, Square, Eye, Search, Filter, User
} from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import Modal from '../components/Modal';
import BatchMetadataModal from '../components/BatchMetadataModal';
import RemoveMetadataModal from '../components/RemoveMetadataModal';


// -- Category Items Table --
const CategoryItemsTable = ({ category, onBack }) => {
    const { showToast } = useToast();
    const [items, setItems] = useState([]);
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [sort, setSort] = useState({ by: 'modified_at', order: 'desc' });
    const [selectedItems, setSelectedItems] = useState(new Set());
    const [lastSelectedIndex, setLastSelectedIndex] = useState(null);
    const [batchModalOpen, setBatchModalOpen] = useState(false);
    const [removeModalOpen, setRemoveModalOpen] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [appliedSearchTerm, setAppliedSearchTerm] = useState('');
    const [searchScope, setSearchScope] = useState('both');
    const [filters, setFilters] = useState({
        account_id: '',
        item_type: '',
        attributes: {}
    });

    useEffect(() => {
        accountsService.getAccounts().then(setAccounts).catch(console.error);
    }, []);

    const CategoryFilterBar = ({ onFilter, currentFilters }) => {
        const [localFilters, setLocalFilters] = useState(currentFilters);
        const [isOpen, setIsOpen] = useState(false);

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
                                {(category.attributes || []).map(attr => (
                                    <div key={attr.id}>
                                        <label className="block text-sm font-medium mb-1">{attr.name}</label>
                                        {attr.data_type === 'select' ? (
                                            <select
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={localFilters.attributes[attr.id] ?? ''}
                                                onChange={(e) => handleAttributeChange(attr.id, e.target.value)}
                                            >
                                                <option value="">Any</option>
                                                {attr.options?.options?.map(opt => (
                                                    <option key={opt} value={opt}>{opt}</option>
                                                ))}
                                            </select>
                                        ) : attr.data_type === 'boolean' ? (
                                            <select
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={localFilters.attributes[attr.id] ?? ''}
                                                onChange={(e) => handleAttributeChange(attr.id, e.target.value)}
                                            >
                                                <option value="">Any</option>
                                                <option value="true">Yes</option>
                                                <option value="false">No</option>
                                            </select>
                                        ) : (
                                            <input
                                                type={attr.data_type === 'number' ? 'number' : attr.data_type === 'date' ? 'date' : 'text'}
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={localFilters.attributes[attr.id] ?? ''}
                                                onChange={(e) => handleAttributeChange(attr.id, e.target.value)}
                                                placeholder={`Filter by ${attr.name}`}
                                            />
                                        )}
                                    </div>
                                ))}
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

    const fetchItems = async (overridePage) => {
        setLoading(true);
        try {
            const effectivePage = overridePage ?? page;
            const metadataFilters = {};
            Object.entries(filters.attributes || {}).forEach(([attrId, value]) => {
                if (value !== '' && value !== null && value !== undefined) {
                    metadataFilters[attrId] = value;
                }
            });

            const data = await itemsService.listItems({
                page: effectivePage,
                page_size: 50,
                sort_by: sort.by,
                sort_order: sort.order,
                category_id: category.id,
                has_metadata: true,
                q: appliedSearchTerm,
                search_fields: searchScope,
                account_id: filters.account_id || undefined,
                item_type: filters.item_type || undefined,
                metadata: metadataFilters
            });
            setItems(data.items);
            setTotal(data.total);
            setTotalPages(data.total_pages);
        } catch (error) {
            console.error('Failed to fetch category items:', error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchItems();
    }, [page, sort, category.id, appliedSearchTerm, searchScope, filters]);

    useEffect(() => {
        setSelectedItems(new Set());
    }, [items]);

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
        if (attr.data_type === 'date' && val) {
            return new Date(val).toLocaleDateString('en-GB');
        }
        return String(val);
    };

    const attributes = category.attributes || [];

    const fixedColTemplate = '40px 40px 2fr 120px 80px';
    const attrCols = attributes.map(() => 'minmax(100px, 1fr)').join(' ');
    const gridTemplate = `${fixedColTemplate} ${attrCols} 140px minmax(180px,1fr)`;

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
                        onClick={() => setBatchModalOpen(true)}
                        disabled={selectedItems.size === 0}
                        className="flex items-center gap-2 px-3 py-1.5 hover:bg-background rounded-md disabled:opacity-50"
                    >
                        <Database size={16} /> Edit Metadata
                    </button>
                    <button
                        onClick={() => setRemoveModalOpen(true)}
                        disabled={selectedItems.size === 0}
                        className="flex items-center gap-2 px-3 py-1.5 hover:bg-red-50 text-red-600 rounded-md disabled:opacity-50"
                    >
                        <Trash2 size={16} /> Remove Metadata
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
                ) : items.length === 0 ? (
                    <div className="text-center p-12 text-muted-foreground">
                        No items found in this category.
                    </div>
                ) : (
                    <div className="border rounded-lg overflow-hidden bg-card select-none">
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
                                        {attributes.map(attr => (
                                            <div key={attr.id} className="text-sm text-foreground truncate" title={getAttributeValue(item, attr)}>
                                                {getAttributeValue(item, attr)}
                                            </div>
                                        ))}
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
        </>
    );
};


// -- Main Page --
export default function MetadataManager() {
    const [categories, setCategories] = useState([]);
    const [loading, setLoading] = useState(true);
    const [expandedCategory, setExpandedCategory] = useState(null);
    const [viewingCategory, setViewingCategory] = useState(null);
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
    const [deleteCategoryTarget, setDeleteCategoryTarget] = useState(null);
    const [deletingCategory, setDeletingCategory] = useState(false);

    useEffect(() => {
        loadCategories();
    }, []);

    const loadCategories = async () => {
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

    const handleDeleteAttribute = async (id) => {
        if (!window.confirm('Delete this attribute?')) return;
        try {
            await metadataService.deleteAttribute(id);
            showToast('Attribute deleted', 'success');
            loadCategories();
        } catch (error) {
            showToast('Failed to delete attribute', 'error');
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
                <div className="flex items-center gap-2">
                    <h1 className="text-lg font-semibold text-foreground">Metadata Manager</h1>
                    <span className="text-xs text-muted-foreground font-normal bg-muted px-2 py-0.5 rounded-full">
                        {categories.length} categories
                    </span>
                </div>
                <button
                    onClick={() => setCreateModalOpen(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 text-sm font-medium transition-colors"
                >
                    <Plus size={16} /> New Category
                </button>
            </div>

            {/* Content */}
            <main className="flex-1 overflow-auto p-4">
                {loading ? (
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
                                            className="p-2 hover:bg-destructive/10 text-muted-foreground hover:text-destructive rounded-md transition-colors"
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
                                                                    Options: {attr.options.options.join(', ')}
                                                                </div>
                                                            )}
                                                        </div>
                                                        <button
                                                            onClick={() => handleDeleteAttribute(attr.id)}
                                                            className="text-muted-foreground hover:text-destructive p-1 rounded"
                                                        >
                                                            <Trash2 size={16} />
                                                        </button>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
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
        </div>
    );
}
