import { useState, useEffect, useCallback } from 'react';
import { metadataService } from '../services/metadata';
import { itemsService } from '../services/items';
import { jobsService } from '../services/jobs';
import { Loader2 } from 'lucide-react';
import Modal from './Modal';

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

    useEffect(() => {
        if (!isOpen || categories.length === 0 || selectedItems.length === 0) return;
        prefillFromSelection();
    }, [isOpen, categories, selectedItems, prefillFromSelection]);

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

    const handleSave = async () => {
        if (!selectedCategory) return;
        setSaving(true);
        try {
            const accountSet = new Set(selectedItems.map(i => i.account_id));
            if (accountSet.size > 1) {
                showToast('Cannot batch update items from different accounts simultaneously.', 'error');
                setSaving(false);
                return;
            }

            const accountId = Array.from(accountSet)[0];
            const folders = selectedItems.filter(i => i.item_type === 'folder');
            const files = selectedItems.filter(i => i.item_type !== 'folder');

            const promises = [];

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

            await Promise.all(promises);

            if (applyRecursive && folders.length > 0) {
                showToast(`${folders.length} recursive job(s) created for folder contents.`, 'success');
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
                                {currentCategory.attributes.map(attr => (
                                    <div key={attr.id}>
                                        <label className="block text-xs font-medium mb-1 uppercase text-muted-foreground">{attr.name} {attr.is_required && '*'}</label>
                                        {attr.data_type === 'select' ? (
                                            <select
                                                className="w-full border rounded-md p-2 text-sm bg-background"
                                                value={attributeValues[attr.id] ?? ''}
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
                                                value={attributeValues[attr.id] ?? ''}
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
                                                value={attributeValues[attr.id] ?? ''}
                                                onChange={e => setAttributeValues(prev => ({ ...prev, [attr.id]: e.target.value }))}
                                            />
                                        )}
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

export default BatchMetadataModal;
