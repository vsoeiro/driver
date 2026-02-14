import React, { useState, useEffect } from 'react';
import Modal from './Modal';
import { metadataService } from '../services/metadata';
import { useToast } from '../contexts/ToastContext';
import { Loader2 } from 'lucide-react';

export default function MetadataModal({ isOpen, onClose, item, accountId, onSuccess }) {
    const { showToast } = useToast();
    const [categories, setCategories] = useState([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);

    // Form State
    const [selectedCategoryId, setSelectedCategoryId] = useState('');
    const [formValues, setFormValues] = useState({});

    useEffect(() => {
        if (isOpen && item) {
            loadData();
        } else {
            // Reset state
            setSelectedCategoryId('');
            setFormValues({});
        }
    }, [isOpen, item]);

    const loadData = async () => {
        try {
            setLoading(true);
            const [cats, meta] = await Promise.all([
                metadataService.getCategories(),
                metadataService.getItemMetadata(accountId, item.id)
            ]);
            setCategories(cats);

            if (meta) {
                setSelectedCategoryId(meta.category_id);
                setFormValues(meta.values || {});
            }
        } catch (error) {
            console.error(error);
            showToast('Failed to load metadata', 'error');
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async (e) => {
        e.preventDefault();
        try {
            setSaving(true);

            // Validate required fields
            const category = categories.find(c => c.id === selectedCategoryId);
            if (!category) return;

            const missingRequired = category.attributes
                .filter(attr => attr.is_required && !formValues[attr.id]);

            if (missingRequired.length > 0) {
                showToast(`Missing required fields: ${missingRequired.map(a => a.name).join(', ')}`, 'error');
                setSaving(false);
                return;
            }

            await metadataService.saveItemMetadata({
                account_id: accountId,
                item_id: item.id,
                category_id: selectedCategoryId,
                values: formValues
            });

            showToast('Metadata saved successfully', 'success');
            if (onSuccess) onSuccess();
            onClose();
        } catch (error) {
            console.error(error);
            showToast('Failed to save metadata', 'error');
        } finally {
            setSaving(false);
        }
    };

    const handleInputChange = (attributeId, value) => {
        setFormValues(prev => ({
            ...prev,
            [attributeId]: value
        }));
    };

    if (!isOpen) return null;

    const selectedCategory = categories.find(c => c.id === selectedCategoryId);

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={`Metadata for ${item?.name}`}>
            {loading ? (
                <div className="flex justify-center p-8">
                    <Loader2 className="animate-spin text-primary" size={32} />
                </div>
            ) : (
                <form onSubmit={handleSave} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">Category</label>
                        <select
                            className="w-full border rounded-md p-2 bg-background"
                            value={selectedCategoryId}
                            onChange={e => {
                                setSelectedCategoryId(e.target.value);
                            }}
                        >
                            <option value="">Select a category...</option>
                            {categories.map(cat => (
                                <option key={cat.id} value={cat.id}>{cat.name}</option>
                            ))}
                        </select>
                    </div>

                    {selectedCategory && (
                        <div className="space-y-3 border-t pt-4">
                            {selectedCategory.attributes.length === 0 ? (
                                <p className="text-sm text-muted-foreground italic">No attributes defined for this category.</p>
                            ) : (
                                selectedCategory.attributes.map(attr => (
                                    <div key={attr.id}>
                                        <label className="block text-sm font-medium mb-1">
                                            {attr.name}
                                            {attr.is_required && <span className="text-destructive ml-1">*</span>}
                                        </label>

                                        {attr.data_type === 'text' && (
                                            <input
                                                type="text"
                                                className="w-full border rounded-md p-2 bg-background"
                                                value={formValues[attr.id] || ''}
                                                onChange={e => handleInputChange(attr.id, e.target.value)}
                                            />
                                        )}

                                        {attr.data_type === 'number' && (
                                            <input
                                                type="number"
                                                className="w-full border rounded-md p-2 bg-background"
                                                value={formValues[attr.id] || ''}
                                                onChange={e => handleInputChange(attr.id, e.target.value)}
                                            />
                                        )}

                                        {attr.data_type === 'date' && (
                                            <input
                                                type="date"
                                                className="w-full border rounded-md p-2 bg-background"
                                                value={formValues[attr.id] || ''}
                                                onChange={e => handleInputChange(attr.id, e.target.value)}
                                            />
                                        )}

                                        {attr.data_type === 'boolean' && (
                                            <div className="flex items-center gap-2">
                                                <input
                                                    type="checkbox"
                                                    className="rounded border-gray-300"
                                                    checked={!!formValues[attr.id]}
                                                    onChange={e => handleInputChange(attr.id, e.target.checked)}
                                                />
                                                <span className="text-sm text-muted-foreground">Yes</span>
                                            </div>
                                        )}

                                        {attr.data_type === 'select' && (
                                            <select
                                                className="w-full border rounded-md p-2 bg-background"
                                                value={formValues[attr.id] || ''}
                                                onChange={e => handleInputChange(attr.id, e.target.value)}
                                            >
                                                <option value="">Select...</option>
                                                {attr.options?.options?.map(opt => (
                                                    <option key={opt} value={opt}>{opt}</option>
                                                ))}
                                            </select>
                                        )}
                                    </div>
                                ))
                            )}
                        </div>
                    )}

                    <div className="flex justify-end gap-2 pt-4 border-t mt-4">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={!selectedCategoryId || saving}
                            className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                        >
                            {saving && <Loader2 className="animate-spin" size={14} />}
                            Save
                        </button>
                    </div>
                </form>
            )}
        </Modal>
    );
}
