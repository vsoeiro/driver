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

const READ_ONLY_COMIC_FIELDS = new Set([
    'cover_item_id',
    'cover_filename',
    'cover_account_id',
    'page_count',
    'file_format',
]);
const COMIC_AI_ALLOWED_FIELDS = new Set([
    'series',
    'volume',
    'issue_number',
    'title',
    'publisher',
    'writer',
    'penciller',
]);

export default function MetadataModal({ isOpen, onClose, item, accountId, onSuccess }) {
    const { showToast } = useToast();
    const [categories, setCategories] = useState([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [history, setHistory] = useState([]);
    const [aiFilling, setAiFilling] = useState(false);
    const [aiSuggestions, setAiSuggestions] = useState({});
    const [coverUrl, setCoverUrl] = useState(null);
    const [coverLoading, setCoverLoading] = useState(false);

    // Form State
    const [selectedCategoryId, setSelectedCategoryId] = useState('');
    const [formValues, setFormValues] = useState({});
    const providerItemId = item?.item_id || item?.id;

    const loadData = useCallback(async () => {
        try {
            setLoading(true);
            const [cats, meta] = await Promise.all([
                metadataService.getCategories(),
                metadataService.getItemMetadata(accountId, providerItemId)
            ]);
            setCategories(cats);

            if (meta) {
                setSelectedCategoryId(meta.category_id);
                setFormValues(meta.values || {});
                setAiSuggestions(meta.ai_suggestions || {});
            } else {
                setSelectedCategoryId('');
                setFormValues({});
                setAiSuggestions({});
            }
            const historyData = await metadataService.getItemMetadataHistory(accountId, providerItemId);
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
            setAiSuggestions({});
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
            const category = categories.find(c => c.id === selectedCategoryId);
            const titleAttr = (category?.attributes || []).find(
                (attr) => attr.plugin_field_key === 'title'
            );
            const coverAttr = (category?.attributes || []).find(
                (attr) => attr.plugin_field_key === 'cover_item_id'
            );
            const coverAccountAttr = (category?.attributes || []).find(
                (attr) => attr.plugin_field_key === 'cover_account_id'
            );

            const title = titleAttr ? (formValues[titleAttr.id] || item.name) : item.name;
            const coverItemId = coverAttr ? formValues[coverAttr.id] : null;
            const coverAccountId = coverAccountAttr ? formValues[coverAccountAttr.id] : accountId;
            if (!coverItemId) {
                showToast('Run Map Comics first so cover metadata is available for AI.', 'error');
                return;
            }

            const result = await aiService.suggestComicMetadata({
                category_id: selectedCategoryId,
                title,
                account_id: accountId,
                item_id: providerItemId,
                cover_account_id: coverAccountId || null,
                cover_item_id: coverItemId || null,
            });

            const attrsById = new Map((category?.attributes || []).map((a) => [a.id, a]));
            const normalizedSuggestions = {};
            Object.entries(result.suggestions || {}).forEach(([attrId, rawSuggestion]) => {
                const attr = attrsById.get(attrId);
                if (!attr || !rawSuggestion || typeof rawSuggestion !== 'object') return;
                if (isComicPluginCategory) {
                    if (!COMIC_AI_ALLOWED_FIELDS.has(attr.plugin_field_key)) return;
                    if (READ_ONLY_COMIC_FIELDS.has(attr.plugin_field_key)) return;
                }
                normalizedSuggestions[attrId] = {
                    ...rawSuggestion,
                    value: normalizeAiValue(attr, rawSuggestion.value),
                };
            });

            const filledCount = Object.keys(normalizedSuggestions).length;
            if (filledCount === 0) {
                showToast('AI did not generate useful suggestions for this item.', 'error');
                return;
            }

            setAiSuggestions((prev) => ({ ...prev, ...normalizedSuggestions }));
            await metadataService.updateItemAISuggestions(accountId, providerItemId, {
                category_id: selectedCategoryId,
                suggestions: { ...aiSuggestions, ...normalizedSuggestions },
            });

            showToast(
                `AI suggested ${filledCount} field(s)`,
                'success'
            );
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to generate AI suggestions';
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
                    providerItemId,
                    metadata,
                    category.name
                );
                showToast('Bulk metadata update job started', 'success');
            } else {
                await metadataService.saveItemMetadata({
                    account_id: accountId,
                    item_id: providerItemId,
                    category_id: selectedCategoryId,
                    values: formValues,
                    ai_suggestions: aiSuggestions,
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
        if (aiSuggestions[attributeId]) {
            setAiSuggestions((prev) => {
                const next = { ...prev };
                delete next[attributeId];
                return next;
            });
        }
    };

    const handleAcceptSuggestion = async (attributeId) => {
        if (!selectedCategoryId) return;
        try {
            const updated = await metadataService.acceptItemAISuggestion(accountId, providerItemId, {
                category_id: selectedCategoryId,
                attribute_id: attributeId,
            });
            setFormValues(updated.values || {});
            setAiSuggestions(updated.ai_suggestions || {});
            showToast('AI suggestion accepted', 'success');
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to accept AI suggestion';
            showToast(message, 'error');
        }
    };

    const handleRejectSuggestion = async (attributeId) => {
        if (!selectedCategoryId) return;
        try {
            const updated = await metadataService.rejectItemAISuggestion(accountId, providerItemId, {
                category_id: selectedCategoryId,
                attribute_id: attributeId,
            });
            setAiSuggestions(updated.ai_suggestions || {});
            showToast('AI suggestion rejected', 'success');
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to reject AI suggestion';
            showToast(message, 'error');
        }
    };

    const selectedCategory = categories.find(c => c.id === selectedCategoryId);
    const pluginView = getCategoryPluginView(selectedCategory);
    const isComicPluginCategory = selectedCategory?.plugin_key === 'comicrack_core';
    const coverAttr = selectedCategory?.attributes?.find(
        (attr) => attr.plugin_field_key === pluginView?.gallery?.coverField
    );
    const coverAccountAttr = selectedCategory?.attributes?.find(
        (attr) => attr.plugin_field_key === pluginView?.gallery?.coverAccountField
    );
    const coverItemId = coverAttr ? formValues?.[coverAttr.id] : null;
    const coverAccountId = coverAccountAttr ? formValues?.[coverAccountAttr.id] : accountId;
    const showCoverPanel = !!(selectedCategory && coverAttr && item?.item_type !== 'folder');
    const canUseComicAI = !!(
        selectedCategory &&
        isComicPluginCategory &&
        item?.item_type !== 'folder' &&
        coverItemId
    );

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
                                        setAiSuggestions({});
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
                                                AI suggestions are enabled only after comic cover is mapped.
                                            </p>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={handleFillWithAI}
                                            disabled={aiFilling || !item?.name || !canUseComicAI}
                                            className="px-3 py-2 text-sm font-medium border rounded-md hover:bg-accent disabled:opacity-50 flex items-center gap-2"
                                        >
                                            {aiFilling ? <Loader2 className="animate-spin" size={14} /> : <Sparkles size={14} />}
                                            Fill with AI
                                        </button>
                                    </div>
                                    <div className="text-xs text-muted-foreground bg-background border rounded-md p-2">
                                        {!isComicPluginCategory
                                            ? 'AI Assist is available only for Comics plugin category.'
                                            : !coverItemId
                                                ? 'Run Map Comics first to populate cover metadata, then AI assist will be enabled.'
                                                : <>Source context: <span className="font-medium">{item?.name || '-'}</span></>}
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
                                                {(() => {
                                                    const isReadOnlyComputed = selectedCategory?.plugin_key === 'comicrack_core'
                                                        && READ_ONLY_COMIC_FIELDS.has(attr.plugin_field_key);
                                                    const isAiEligibleComputed = !(
                                                        isComicPluginCategory && !COMIC_AI_ALLOWED_FIELDS.has(attr.plugin_field_key)
                                                    );
                                                    const suggestion = isAiEligibleComputed ? aiSuggestions[attr.id] : null;
                                                    const suggestionValue = suggestion?.value;
                                                    const suggestionText = suggestionValue === undefined || suggestionValue === null
                                                        ? ''
                                                        : String(suggestionValue);
                                                    const confidence = typeof suggestion?.confidence === 'number'
                                                        ? Math.round(suggestion.confidence * 100)
                                                        : null;
                                                    return (
                                                        <>

                                                            {attr.data_type === 'text' && (
                                                                <input
                                                                    type="text"
                                                                    className="w-full border rounded-md p-2 bg-background"
                                                                    value={formValues[attr.id] || ''}
                                                                    placeholder={!formValues[attr.id] ? suggestionText : ''}
                                                                    disabled={isReadOnlyComputed}
                                                                    onChange={e => handleInputChange(attr.id, e.target.value)}
                                                                />
                                                            )}

                                                            {attr.data_type === 'number' && (
                                                                <input
                                                                    type="number"
                                                                    className="w-full border rounded-md p-2 bg-background"
                                                                    value={formValues[attr.id] || ''}
                                                                    placeholder={!formValues[attr.id] ? suggestionText : ''}
                                                                    disabled={isReadOnlyComputed}
                                                                    onChange={e => handleInputChange(attr.id, e.target.value)}
                                                                />
                                                            )}

                                                            {attr.data_type === 'date' && (
                                                                <input
                                                                    type="date"
                                                                    className="w-full border rounded-md p-2 bg-background"
                                                                    value={formValues[attr.id] || ''}
                                                                    disabled={isReadOnlyComputed}
                                                                    onChange={e => handleInputChange(attr.id, e.target.value)}
                                                                />
                                                            )}

                                                            {attr.data_type === 'boolean' && (
                                                                <div className="flex items-center gap-2">
                                                                    <input
                                                                        type="checkbox"
                                                                        className="rounded border-gray-300"
                                                                        checked={!!formValues[attr.id]}
                                                                        disabled={isReadOnlyComputed}
                                                                        onChange={e => handleInputChange(attr.id, e.target.checked)}
                                                                    />
                                                                    <span className="text-sm text-muted-foreground">Yes</span>
                                                                </div>
                                                            )}

                                                            {attr.data_type === 'select' && (
                                                                <select
                                                                    className="w-full border rounded-md p-2 bg-background"
                                                                    value={formValues[attr.id] || ''}
                                                                    disabled={isReadOnlyComputed}
                                                                    onChange={e => handleInputChange(attr.id, e.target.value)}
                                                                >
                                                                    <option value="">
                                                                        {suggestionText ? `AI: ${suggestionText}` : 'Select...'}
                                                                    </option>
                                                                    {getSelectOptions(attr.options).map(opt => (
                                                                        <option key={opt} value={opt}>{opt}</option>
                                                                    ))}
                                                                </select>
                                                            )}

                                                            {isReadOnlyComputed && (
                                                                <div className="mt-1 text-xs text-muted-foreground">
                                                                    Mapped field (read-only)
                                                                </div>
                                                            )}

                                                            {suggestion && (
                                                                <div className="mt-2 flex items-center gap-2 text-xs">
                                                                    <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-700">
                                                                        AI suggestion{confidence !== null ? ` (${confidence}%)` : ''}
                                                                    </span>
                                                                    <button
                                                                        type="button"
                                                                        onClick={() => handleAcceptSuggestion(attr.id)}
                                                                        className="px-2 py-0.5 rounded border hover:bg-accent"
                                                                    >
                                                                        Accept
                                                                    </button>
                                                                    <button
                                                                        type="button"
                                                                        onClick={() => handleRejectSuggestion(attr.id)}
                                                                        className="px-2 py-0.5 rounded border hover:bg-accent"
                                                                    >
                                                                        Reject
                                                                    </button>
                                                                </div>
                                                            )}
                                                        </>
                                                    );
                                                })()}
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
