import React, { useState, useEffect } from 'react';
import { metadataService } from '../services/metadata';
import { Plus, Trash2, ChevronRight, ChevronDown, Check, X } from 'lucide-react';
import { useToast } from '../contexts/ToastContext';
import Modal from '../components/Modal';

export default function MetadataManager() {
    const [categories, setCategories] = useState([]);
    const [loading, setLoading] = useState(true);
    const [expandedCategory, setExpandedCategory] = useState(null);
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
    const [newAttrOptions, setNewAttrOptions] = useState(''); // Comma separated for select

    useEffect(() => {
        loadCategories();
    }, []);

    const loadCategories = async () => {
        try {
            setLoading(true);
            const data = await metadataService.getCategories();
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

    return (
        <div className="p-6 max-w-5xl mx-auto">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold">Metadata Manager</h1>
                <button
                    onClick={() => setCreateModalOpen(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
                >
                    <Plus size={16} /> New Category
                </button>
            </div>

            {loading ? (
                <div className="text-center py-10">Loading...</div>
            ) : categories.length === 0 ? (
                <div className="text-center py-10 text-muted-foreground border rounded-lg bg-card">
                    No categories defined. Create one to get started.
                </div>
            ) : (
                <div className="space-y-4">
                    {categories.map(cat => (
                        <div key={cat.id} className="border rounded-lg bg-card overflow-hidden">
                            <div
                                className="p-4 flex items-center justify-between cursor-pointer hover:bg-accent/50 transition-colors"
                                onClick={() => toggleExpand(cat.id)}
                            >
                                <div className="flex items-center gap-3">
                                    {expandedCategory === cat.id ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
                                    <div>
                                        <h3 className="font-semibold">{cat.name}</h3>
                                        {cat.description && <p className="text-sm text-muted-foreground">{cat.description}</p>}
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="text-sm text-muted-foreground bg-secondary px-2 py-1 rounded-md">
                                        {cat.attributes.length} attributes
                                    </span>
                                    <button
                                        onClick={(e) => handleDeleteCategory(cat.id, e)}
                                        className="p-2 hover:bg-destructive/10 text-muted-foreground hover:text-destructive rounded-md"
                                    >
                                        <Trash2 size={18} />
                                    </button>
                                </div>
                            </div>

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
