import { useState, useEffect, useCallback } from 'react';
import Modal from './Modal';
import { metadataService } from '../services/metadata';
import { jobsService } from '../services/jobs';
import { aiService } from '../services/ai';
import { driveService } from '../services/drive';
import { useToast } from '../contexts/ToastContext';
import { Loader2, AlertTriangle, Sparkles } from 'lucide-react';
import { getCategoryPluginView } from '../plugins/metadataCategoryViews';
import { buildCoverCacheKey, getCachedCoverUrl, setCachedCoverUrl } from '../utils/coverCache';
import { getSelectOptions } from '../utils/metadata';

export default function MetadataModal({ isOpen, onClose, item, accountId, onSuccess }) {
    const { showToast } = useToast();
    const [categories, setCategories] = useState([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [history, setHistory] = useState([]);
    const [aiFilling, setAiFilling] = useState(false);
    const [coverUrl, setCoverUrl] = useState(null);
    const [coverLoading, setCoverLoading] = useState(false);

    // Form State
    const [selectedCategoryId, setSelectedCategoryId] = useState('');
    const [formValues, setFormValues] = useState({});

    const loadData = useCallback(async () => {
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
            const historyData = await metadataService.getItemMetadataHistory(accountId, item.id);
            setHistory(historyData || []);
        } catch (error) {
            console.error(error);
            showToast('Failed to load metadata', 'error');
        } finally {
            setLoading(false);
        }
    }, [accountId, item, showToast]);

    useEffect(() => {
        if (isOpen && item) {
            loadData();
        } else {
            // Reset state
            setSelectedCategoryId('');
            setFormValues({});
            setHistory([]);
        }
    }, [isOpen, item, loadData]);

    const normalizeAiValue = (attribute, value) => {
        if (value === undefined || value === null || value === '') return value;

        if (attribute.data_type === 'boolean') {
            if (typeof value === 'boolean') return value;
            if (typeof value === 'number') return value !== 0;
            if (typeof value === 'string') {
                const normalized = value.trim().toLowerCase();
                if (['true', 'yes', '1', 'y'].includes(normalized)) return true;
                if (['false', 'no', '0', 'n'].includes(normalized)) return false;
            }
            return Boolean(value);
        }

        if (attribute.data_type === 'number') {
            const parsed = Number(value);
            return Number.isNaN(parsed) ? value : parsed;
        }

        if (attribute.data_type === 'date') {
            const strValue = String(value);
            return strValue.length >= 10 ? strValue.slice(0, 10) : strValue;
        }

        return value;
    };

    const handleFillWithAI = async () => {
        if (!selectedCategoryId) {
            showToast('Select a category first', 'error');
            return;
        }
        if (!item?.name) {
            showToast('File name is not available for AI extraction', 'error');
            return;
        }

        try {
            setAiFilling(true);
            const fileFormat = item.extension || item.mime_type || null;
            const fileContext = [
                `File name: ${item.name}`,
                item.path ? `Path: ${item.path}` : null,
                item.item_type ? `Type: ${item.item_type}` : null,
                fileFormat ? `Format: ${fileFormat}` : null,
                item.size !== undefined && item.size !== null ? `Size bytes: ${item.size}` : null,
                item.created_at ? `Created at: ${item.created_at}` : null,
                item.modified_at ? `Modified at: ${item.modified_at}` : null,
            ]
                .filter(Boolean)
                .join('\n');

            const result = await aiService.extractMetadata({
                category_id: selectedCategoryId,
                document_text: fileContext,
                apply_to_item: false,
            });

            const category = categories.find(c => c.id === selectedCategoryId);
            const attrsById = new Map((category?.attributes || []).map(a => [a.id, a]));
            const normalizedValues = {};

            Object.entries(result.values || {}).forEach(([attrId, rawValue]) => {
                const attr = attrsById.get(attrId);
                if (!attr) return;
                normalizedValues[attrId] = normalizeAiValue(attr, rawValue);
            });

            const filledCount = Object.keys(normalizedValues).length;
            if (filledCount === 0) {
                showToast('AI could not match values to this category attributes. Try more document text.', 'error');
                return;
            }

            setFormValues(prev => ({ ...prev, ...normalizedValues }));

            const confidenceText = typeof result.confidence === 'number'
                ? ` (${Math.round(result.confidence * 100)}% confidence)`
                : '';
            showToast(
                `AI filled ${filledCount} field(s)${confidenceText}`,
                'success'
            );
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to extract metadata with AI';
            showToast(message, 'error');
        } finally {
            setAiFilling(false);
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

            // Check if folder -> Bulk Update
            if (item.item_type === 'folder') {
                // Prepare metadata map: { "Attribute Name": "Value" }
                // The backend job expects attribute names, not IDs, because it resolves them recursively 
                // (or strictly speaking, the handler implementation maps input keys to attribute IDs).
                // Wait, my backend implementation:
                // `attr_map = {attr.name: attr.id for attr in attributes}`
                // `if key in attr_map`
                // So yes, I need to send Attribute Names as keys.

                const metadata = {};
                Object.entries(formValues).forEach(([attrId, value]) => {
                    const attr = category.attributes.find(a => a.id === attrId);
                    if (attr) {
                        metadata[attr.name] = value;
                    }
                });

                await jobsService.createMetadataUpdateJob(
                    accountId,
                    item.id,
                    metadata,
                    category.name
                );
                showToast('Bulk metadata update job started', 'success');
            } else {
                await metadataService.saveItemMetadata({
                    account_id: accountId,
                    item_id: item.id,
                    category_id: selectedCategoryId,
                    values: formValues
                });
                showToast('Metadata saved successfully', 'success');
            }

            if (onSuccess) onSuccess();
            await loadData();
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

    const selectedCategory = categories.find(c => c.id === selectedCategoryId);
    const pluginView = getCategoryPluginView(selectedCategory);
    const coverAttr = selectedCategory?.attributes?.find(
        (attr) => attr.plugin_field_key === pluginView?.gallery?.coverField
    );
    const coverAccountAttr = selectedCategory?.attributes?.find(
        (attr) => attr.plugin_field_key === pluginView?.gallery?.coverAccountField
    );
    const coverItemId = coverAttr ? formValues?.[coverAttr.id] : null;
    const coverAccountId = coverAccountAttr ? formValues?.[coverAccountAttr.id] : accountId;
    const showCoverPanel = !!(selectedCategory && coverAttr && item?.item_type !== 'folder');

    useEffect(() => {
        if (!isOpen || !showCoverPanel || !coverItemId || !coverAccountId) {
            setCoverUrl(null);
            setCoverLoading(false);
            return;
        }

        let cancelled = false;
        const cacheKey = buildCoverCacheKey(String(coverAccountId), String(coverItemId));
        const cached = getCachedCoverUrl(cacheKey);
        if (cached) {
            setCoverUrl(cached);
            return;
        }

        const loadCover = async () => {
            try {
                setCoverLoading(true);
                const url = driveService.getDownloadContentUrl(
                    String(coverAccountId),
                    String(coverItemId),
                    { autoResolveAccount: true },
                );
                if (cancelled || !url) return;
                setCachedCoverUrl(cacheKey, url);
                setCoverUrl(url);
            } catch (_) {
                if (!cancelled) setCoverUrl(null);
            } finally {
                if (!cancelled) setCoverLoading(false);
            }
        };

        loadCover();
        return () => {
            cancelled = true;
        };
    }, [isOpen, showCoverPanel, coverItemId, coverAccountId]);

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title={`Metadata for ${item?.name}`}
            maxWidthClass="max-w-5xl"
        >
            {loading ? (
                <div className="flex justify-center p-8">
                    <Loader2 className="animate-spin text-primary" size={32} />
                </div>
            ) : (
                <form onSubmit={handleSave}>
                    <div className={`grid gap-4 ${showCoverPanel ? 'grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)]' : 'grid-cols-1'}`}>
                        {showCoverPanel && (
                            <aside className="border rounded-md bg-muted/20 p-3 h-fit lg:sticky lg:top-0">
                                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                                    Cover Preview
                                </div>
                                <div className="w-full aspect-[3/4] rounded-md overflow-hidden border bg-background">
                                    {coverLoading ? (
                                        <div className="w-full h-full flex items-center justify-center">
                                            <Loader2 className="animate-spin text-primary" size={24} />
                                        </div>
                                    ) : coverUrl ? (
                                        <img src={coverUrl} alt={item?.name || 'Cover'} className="w-full h-full object-cover" />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground">
                                            No cover available
                                        </div>
                                    )}
                                </div>
                            </aside>
                        )}

                        <div className="space-y-4 min-w-0">
                            {item?.item_type === 'folder' && (
                                <div className="bg-yellow-500/10 border-l-4 border-yellow-500 p-4 mb-4">
                                    <div className="flex">
                                        <div className="flex-shrink-0">
                                            <AlertTriangle className="h-5 w-5 text-yellow-500" aria-hidden="true" />
                                        </div>
                                        <div className="ml-3">
                                            <p className="text-sm text-yellow-700 dark:text-yellow-400">
                                                You are editing a folder. Changes will be applied effectively to <strong>all files</strong> inside this folder recursively. This process runs in the background.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            )}

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
                                <div className="space-y-2 border rounded-md p-3 bg-muted/20">
                                    <div className="flex items-center justify-between gap-3">
                                        <div>
                                            <h4 className="text-sm font-medium">AI Assist</h4>
                                            <p className="text-xs text-muted-foreground">
                                                AI will infer metadata from the file name automatically.
                                            </p>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={handleFillWithAI}
                                            disabled={aiFilling || !item?.name}
                                            className="px-3 py-2 text-sm font-medium border rounded-md hover:bg-accent disabled:opacity-50 flex items-center gap-2"
                                        >
                                            {aiFilling ? <Loader2 className="animate-spin" size={14} /> : <Sparkles size={14} />}
                                            Fill with AI
                                        </button>
                                    </div>
                                    <div className="text-xs text-muted-foreground bg-background border rounded-md p-2">
                                        Source context: <span className="font-medium">{item?.name || '-'}</span>
                                    </div>
                                </div>
                            )}

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
                                                        {getSelectOptions(attr.options).map(opt => (
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
                            <div className="border-t pt-4">
                                <h4 className="text-sm font-semibold mb-2">Metadata History</h4>
                                {history.length === 0 ? (
                                    <p className="text-xs text-muted-foreground">No metadata changes for this item yet.</p>
                                ) : (
                                    <div className="max-h-48 overflow-auto border rounded-md divide-y">
                                        {history.map((entry) => (
                                            <div key={entry.id} className="px-3 py-2 text-xs">
                                                <div className="font-medium">{entry.action}</div>
                                                <div className="text-muted-foreground">
                                                    {new Date(entry.created_at).toLocaleString('en-GB')}
                                                </div>
                                                {entry.batch_id && (
                                                    <div className="text-muted-foreground">Batch: {entry.batch_id}</div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </form>
            )}
        </Modal>
    );
}
