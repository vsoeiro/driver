import React, { useState, useEffect, useMemo } from 'react';
import { metadataService } from '../services/metadata';
import { itemsService } from '../services/items';
import {
    Plus, Trash2, ChevronRight, ChevronDown, ChevronLeft,
    Database, Loader2, Tag, Hash, Calendar, ArrowLeft,
    File, Folder, ArrowUpDown, ArrowUp, ArrowDown,
    CheckSquare, Square, Eye
} from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import Modal from '../components/Modal';


// -- Category Items Table --
const CategoryItemsTable = ({ category, onBack }) => {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [sort, setSort] = useState({ by: 'modified_at', order: 'desc' });

    const fetchItems = async (overridePage) => {
        setLoading(true);
        try {
            const effectivePage = overridePage ?? page;
            const data = await itemsService.listItems({
                page: effectivePage,
                page_size: 50,
                sort_by: sort.by,
                sort_order: sort.order,
                category_id: category.id,
                has_metadata: true,
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
    }, [page, sort, category.id]);

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

    const fixedColTemplate = '40px 2fr 80px';
    const attrCols = attributes.map(() => 'minmax(100px, 1fr)').join(' ');
    const gridTemplate = `${fixedColTemplate} ${attrCols} 140px`;

    return (
        <>
            {/* Header */}
            <div className="p-4 border-b flex items-center justify-between bg-background sticky top-0 z-10">
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
                            <div></div>
                            <div className="cursor-pointer flex items-center gap-1 hover:text-foreground" onClick={() => handleSort('name')}>
                                Name {renderSortIcon('name')}
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
                        </div>

                        {/* Table Rows */}
                        <div className="divide-y">
                            {items.map((item) => {
                                const isFolder = item.item_type === 'folder';
                                return (
                                    <div
                                        key={item.id}
                                        className="gap-4 p-3 items-center hover:bg-muted/30 transition-colors"
                                        style={{ display: 'grid', gridTemplateColumns: gridTemplate }}
                                    >
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
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
            </main>

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="bg-muted/50 border-t px-4 py-2 flex items-center justify-end gap-2 text-sm">
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
            )}
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

    const handleDeleteCategory = async (id, e) => {
        e.stopPropagation();
        if (!window.confirm('Are you sure? This will delete all attributes and metadata associated with this category.')) return;
        try {
            await metadataService.deleteCategory(id);
            showToast('Category deleted', 'success');
            loadCategories();
        } catch (error) {
            showToast('Failed to delete category', 'error');
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
                                            onClick={(e) => handleDeleteCategory(cat.id, e)}
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
