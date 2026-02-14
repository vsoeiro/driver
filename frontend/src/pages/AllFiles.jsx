import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { itemsService } from '../services/items';
import { metadataService } from '../services/metadata';
import {
    File, Folder, Search, Filter, Database, CheckSquare, Square,
    Loader2, ChevronLeft, ChevronRight, ArrowUpDown, ArrowUp, ArrowDown
} from 'lucide-react';
import Modal from '../components/Modal';

// Filter Component
const FilterBar = ({ onFilter, filters }) => {
    const [localFilters, setLocalFilters] = useState(filters);
    const [isOpen, setIsOpen] = useState(false);

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
            item_type: ''
        };
        setLocalFilters(cleared);
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
                            value={localFilters.extensions ? localFilters.extensions.join(', ') : ''}
                            onChange={(e) => {
                                const exts = e.target.value.split(',').map(s => s.trim()).filter(Boolean);
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
const BatchMetadataModal = ({ isOpen, onClose, selectedItems, onSuccess }) => {
    const [categories, setCategories] = useState([]);
    const [selectedCategory, setSelectedCategory] = useState('');
    const [attributeValues, setAttributeValues] = useState({});
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (isOpen) {
            loadCategories();
            setAttributeValues({});
            setSelectedCategory('');
        }
    }, [isOpen]);

    const loadCategories = async () => {
        setLoading(true);
        try {
            const data = await metadataService.listCategories();
            setCategories(data);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        if (!selectedCategory) return;
        setSaving(true);
        try {
            // We assume all selected items belong to the same account for now, 
            // OR we need to group by account if the view shows mixed accounts.
            // The table view shows account_id.

            // Check if multiple accounts are selected
            const accounts = new Set(selectedItems.map(i => i.account_id));
            if (accounts.size > 1) {
                alert("Cannot batch update items from different accounts simultaneously.");
                setSaving(false);
                return;
            }

            const accountId = Array.from(accounts)[0];
            const itemIds = selectedItems.map(i => i.item_id);

            await itemsService.batchUpdateMetadata(
                accountId,
                itemIds,
                selectedCategory,
                attributeValues
            );

            onSuccess();
            onClose();
        } catch (error) {
            alert("Failed to update metadata: " + error.message);
        } finally {
            setSaving(false);
        }
    };

    const currentCategory = categories.find(c => c.id === selectedCategory);

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={`Edit Metadata for ${selectedItems.length} items`}>
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
                                onChange={(e) => setSelectedCategory(e.target.value)}
                            >
                                <option value="">Select Category...</option>
                                {categories.map(c => (
                                    <option key={c.id} value={c.id}>{c.name}</option>
                                ))}
                            </select>
                        </div>

                        {currentCategory && (
                            <div className="space-y-3 border p-3 rounded-md bg-muted/20">
                                {currentCategory.attributes.map(attr => (
                                    <div key={attr.id}>
                                        <label className="block text-xs font-medium mb-1 uppercase text-muted-foreground">{attr.name} {attr.is_required && '*'}</label>
                                        {attr.data_type === 'select' ? (
                                            <select
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={attributeValues[attr.id] || ''}
                                                onChange={e => setAttributeValues(prev => ({ ...prev, [attr.id]: e.target.value }))}
                                            >
                                                <option value="">Select...</option>
                                                {attr.options?.options?.map(opt => (
                                                    <option key={opt} value={opt}>{opt}</option>
                                                ))}
                                            </select>
                                        ) : attr.data_type === 'boolean' ? (
                                            <select
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={attributeValues[attr.id] || ''}
                                                onChange={e => setAttributeValues(prev => ({ ...prev, [attr.id]: e.target.value === 'true' }))}
                                            >
                                                <option value="">Select...</option>
                                                <option value="true">Yes</option>
                                                <option value="false">No</option>
                                            </select>
                                        ) : (
                                            <input
                                                type={attr.data_type === 'number' ? 'number' : attr.data_type === 'date' ? 'date' : 'text'}
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={attributeValues[attr.id] || ''}
                                                onChange={e => setAttributeValues(prev => ({ ...prev, [attr.id]: e.target.value }))}
                                            />
                                        )}
                                    </div>
                                ))}
                            </div>
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


export default function AllFiles() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);

    const [searchParams, setSearchParams] = useSearchParams();
    const [filters, setFilters] = useState({
        extensions: [],
        size_min: '',
        size_max: '',
        item_type: ''
    });

    const [sort, setSort] = useState({ by: 'modified_at', order: 'desc' });
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedItems, setSelectedItems] = useState(new Set());
    const [lastSelectedIndex, setLastSelectedIndex] = useState(null);

    const [batchModalOpen, setBatchModalOpen] = useState(false);

    const fetchItems = async () => {
        setLoading(true);
        try {
            const params = {
                page,
                page_size: 50,
                sort_by: sort.by,
                sort_order: sort.order,
                q: searchTerm,
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
    };

    useEffect(() => {
        fetchItems();
    }, [page, sort, filters]); // Search term is handled manually or debounce? Let's generic search on enter.

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

    return (
        <div className="flex flex-col h-screen">
            {/* Header */}
            <div className="p-4 border-b flex items-center justify-between bg-background">
                <h1 className="text-lg font-semibold flex items-center gap-2">
                    All Files <span className="text-xs text-muted-foreground font-normal bg-muted px-2 py-0.5 rounded-full">{total} items</span>
                </h1>

                <div className="flex items-center gap-2">
                    <div className="relative">
                        <Search className="absolute left-2 top-1.5 text-muted-foreground" size={16} />
                        <input
                            type="text"
                            placeholder="Search all files..."
                            className="pl-8 pr-4 py-1.5 text-sm border rounded-md w-64 focus:outline-none focus:ring-1 focus:ring-primary"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && fetchItems()}
                        />
                    </div>
                    <FilterBar onFilter={setFilters} filters={filters} />
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
                        <div className="grid grid-cols-[40px_40px_1fr_100px_100px_150px_150px] gap-4 p-3 border-b bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wider items-center sticky top-0">
                            <div className="flex justify-center">
                                <button onClick={toggleSelectAll}>
                                    {selectedItems.size === items.length && items.length > 0 ? <CheckSquare size={16} /> : <Square size={16} />}
                                </button>
                            </div>
                            <div></div>
                            <div className="cursor-pointer flex items-center gap-1 hover:text-foreground" onClick={() => handleSort('name')}>
                                Name {renderSortIcon('name')}
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
                                        className={`group grid grid-cols-[40px_40px_1fr_100px_100px_150px_150px] gap-4 p-3 items-center hover:bg-muted/30 transition-colors ${isSelected ? 'bg-muted/40' : ''}`}
                                        onClick={(e) => toggleSelection(item.id, index, !e.altKey, e.shiftKey)}
                                    >
                                        <div className="flex justify-center">
                                            <div className={`cursor-pointer ${isSelected ? 'text-primary' : 'text-muted-foreground/50'}`}>
                                                {isSelected ? <CheckSquare size={16} /> : <Square size={16} />}
                                            </div>
                                        </div>
                                        <div className="flex justify-center text-muted-foreground">
                                            {isFolder ? <Folder className="text-blue-500 fill-blue-500/20" size={20} /> : <File className="text-gray-400" size={20} />}
                                        </div>
                                        <div className="min-w-0 truncate font-medium">
                                            {item.name}
                                        </div>
                                        <div className="text-right text-sm text-muted-foreground tabular-nums">
                                            {formatSize(item.size)}
                                        </div>
                                        <div className="text-right text-sm text-muted-foreground truncate">
                                            {/* We need to fetch category name? Or just show indicator? 
                                                The item.metadata object has category_id, but not name unless joined.
                                                For now showing "Yes" if metadata exists. 
                                                Ideally Backend should return Category Name.
                                             */}
                                            {item.metadata ? <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">Yes</span> : '-'}
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
                onSuccess={() => {
                    fetchItems();
                    setSelectedItems(new Set());
                }}
            />
        </div>
    );
}
