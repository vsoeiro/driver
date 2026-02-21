import { useState, useEffect, useCallback } from 'react';
import Modal from './Modal';
import { metadataService } from '../services/metadata';
import { jobsService } from '../services/jobs';
import { aiService } from '../services/ai';
import { driveService } from '../services/drive';
import { useToast } from '../contexts/ToastContext';
import { Loader2, AlertTriangle, Sparkles, ZoomIn, ZoomOut, X } from 'lucide-react';
import { getCategoryPluginView } from '../plugins/metadataCategoryViews';
import { buildCoverCacheKey, getCachedCoverUrl, setCachedCoverUrl } from '../utils/coverCache';
import {
    getSelectOptions,
    normalizeFormLayoutForCategory,
    parseTagsInput,
    READ_ONLY_COMIC_FIELD_KEYS,
    resolveLayoutItemsForRender,
    sortAttributesForCategory,
    tagsToInputValue,
} from '../utils/metadata';
const COMIC_AI_ALLOWED_FIELDS = new Set([
    'series',
    'volume',
    'issue_number',
    'title',
    'publisher',
    'writer',
    'penciller',
]);
const DEFAULT_COMIC_FORM_FIELD_GROUPS = [
    ['series', 'title'],
    ['volume', 'issue_number', 'year', 'month'],
    ['max_volumes', 'max_issues', 'series_status'],
    ['publisher', 'imprint'],
    ['writer', 'penciller', 'colorist', 'letterer'],
    ['genre', 'language', 'original_language'],
    ['tags'],
    ['summary'],
];
const DEFAULT_COMIC_COMPACT_FIELD_KEYS = new Set([
    'volume',
    'issue_number',
    'year',
    'month',
    'max_volumes',
    'max_issues',
]);

function getLayoutItemType(item) {
    if (String(item?.item_type || '').toLowerCase() === 'section') return 'section';
    return 'attribute';
}

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
    const [isCoverZoomOpen, setIsCoverZoomOpen] = useState(false);
    const [coverZoomLevel, setCoverZoomLevel] = useState(1);
    const [layoutMap, setLayoutMap] = useState({});
    const [tagInputDrafts, setTagInputDrafts] = useState({});

    // Form State
    const [selectedCategoryId, setSelectedCategoryId] = useState('');
    const [formValues, setFormValues] = useState({});
    const providerItemId = item?.item_id || item?.id;

    const loadData = useCallback(async () => {
        try {
            setLoading(true);
            const [cats, meta, layouts] = await Promise.all([
                metadataService.getCategories(),
                metadataService.getItemMetadata(accountId, providerItemId),
                metadataService.listFormLayouts(),
            ]);
            setCategories(cats);
            const map = {};
            (layouts || []).forEach((layout) => {
                if (!layout?.category_id) return;
                map[String(layout.category_id)] = {
                    columns: layout.columns,
                    row_height: layout.row_height,
                    items: (layout.items || []).map((item, index) => ({
                        item_type: String(item.item_type || (item.attribute_id ? 'attribute' : 'section')),
                        item_id: String(item.item_id || (item.attribute_id ? String(item.attribute_id) : `section_${index + 1}`)),
                        attribute_id: item.attribute_id ? String(item.attribute_id) : null,
                        title: item.title || null,
                        x: Number(item.x) || 0,
                        y: Number(item.y) || 0,
                        w: Number(item.w) || 12,
                        h: Number(item.h) || 1,
                    })),
                    ordered_attribute_ids: (layout.ordered_attribute_ids || []).map(String),
                    half_width_attribute_ids: (layout.half_width_attribute_ids || []).map(String),
                };
            });
            setLayoutMap(map);

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
            setTagInputDrafts({});
        } catch (error) {
            console.error(error);
            showToast('Failed to load metadata', 'error');
        } finally {
            setLoading(false);
        }
    }, [accountId, providerItemId, showToast]);

    useEffect(() => {
        if (isOpen && item) {
            loadData();
        } else {
            // Reset state
            setSelectedCategoryId('');
            setFormValues({});
            setAiSuggestions({});
            setHistory([]);
            setLayoutMap({});
            setTagInputDrafts({});
            setIsCoverZoomOpen(false);
            setCoverZoomLevel(1);
        }
    }, [isOpen, item, loadData]);

    useEffect(() => {
        if (!isCoverZoomOpen) return;

        const onKeyDown = (event) => {
            if (event.key === 'Escape') {
                setIsCoverZoomOpen(false);
                return;
            }
            if (event.key === '+' || event.key === '=') {
                setCoverZoomLevel((prev) => Math.min(4, Number((prev + 0.25).toFixed(2))));
            }
            if (event.key === '-') {
                setCoverZoomLevel((prev) => Math.max(1, Number((prev - 0.25).toFixed(2))));
            }
        };

        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [isCoverZoomOpen]);

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

        if (attribute.data_type === 'tags') {
            return Array.isArray(value) ? value : parseTagsInput(String(value));
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
                    if (READ_ONLY_COMIC_FIELD_KEYS.has(attr.plugin_field_key)) return;
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
                .filter((attr) => {
                    if (!attr.is_required) return false;
                    const value = formValues[attr.id];
                    if (attr.data_type === 'tags') {
                        return !Array.isArray(value) || value.length === 0;
                    }
                    return value === undefined || value === null || value === '';
                });

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
            setTagInputDrafts({});
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
    const rawCategoryLayout = selectedCategory ? layoutMap[String(selectedCategory.id)] : null;
    const hasConfiguredLayout = !!(
        rawCategoryLayout
        && (
            (Array.isArray(rawCategoryLayout.items) && rawCategoryLayout.items.length > 0)
            || (Array.isArray(rawCategoryLayout.ordered_attribute_ids) && rawCategoryLayout.ordered_attribute_ids.length > 0)
        )
    );
    const categoryLayout = hasConfiguredLayout
        ? normalizeFormLayoutForCategory(selectedCategory, rawCategoryLayout)
        : null;
    const categoryAttributesById = new Map(
        (selectedCategory?.attributes || []).map((attr) => [String(attr.id), attr]),
    );
    const layoutItemsForRender = categoryLayout
        ? resolveLayoutItemsForRender(categoryLayout.items || [], categoryLayout.columns)
        : [];
    const configuredFieldGroups = pluginView?.formLayout?.groups || DEFAULT_COMIC_FORM_FIELD_GROUPS;
    const compactFieldKeys = new Set(pluginView?.formLayout?.compactFields || Array.from(DEFAULT_COMIC_COMPACT_FIELD_KEYS));
    const orderedAttributes = sortAttributesForCategory(
        selectedCategory,
        categoryLayout?.ordered_attribute_ids || null,
    );
    const orderedFieldGroups = (() => {
        if (isComicPluginCategory) {
            const configuredKeys = configuredFieldGroups.flat();
            const grouped = configuredFieldGroups
                .map((group) =>
                    group
                        .map((fieldKey) => orderedAttributes.find((attr) => attr.plugin_field_key === fieldKey))
                        .filter(Boolean)
                )
                .filter((group) => group.length > 0);
            const leftovers = orderedAttributes
                .filter((attr) => !configuredKeys.includes(attr.plugin_field_key || ''))
                .map((attr) => [attr]);
            return [...grouped, ...leftovers];
        }

        return orderedAttributes.map((attr) => [attr]);
    })();
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

    const renderAttributeField = (attr, className = '', style = null) => {
        const isReadOnlyComputed = selectedCategory?.plugin_key === 'comicrack_core'
            && READ_ONLY_COMIC_FIELD_KEYS.has(attr.plugin_field_key);
        const isAiEligibleComputed = !(
            isComicPluginCategory && !COMIC_AI_ALLOWED_FIELDS.has(attr.plugin_field_key)
        );
        const suggestion = isAiEligibleComputed ? aiSuggestions[attr.id] : null;
        const suggestionValue = suggestion?.value;
        const suggestionText = suggestionValue === undefined || suggestionValue === null
            ? ''
            : Array.isArray(suggestionValue)
                ? suggestionValue.join(', ')
                : String(suggestionValue);
        const confidence = typeof suggestion?.confidence === 'number'
            ? Math.round(suggestion.confidence * 100)
            : null;
        const tagsValue = tagInputDrafts[attr.id] ?? tagsToInputValue(formValues[attr.id] || []);

        return (
            <div key={attr.id} className={className} style={style || undefined}>
                <label className="block text-sm font-medium mb-1">
                    {attr.name}
                    {attr.is_required && <span className="text-destructive ml-1">*</span>}
                </label>

                {attr.data_type === 'text' && (
                    <input
                        type="text"
                        className="w-full border rounded-md p-2 bg-background"
                        value={formValues[attr.id] || ''}
                        placeholder={!formValues[attr.id] ? suggestionText : ''}
                        disabled={isReadOnlyComputed}
                        onChange={(e) => handleInputChange(attr.id, e.target.value)}
                    />
                )}

                {attr.data_type === 'number' && (
                    <input
                        type="number"
                        className="w-full border rounded-md p-2 bg-background"
                        value={formValues[attr.id] || ''}
                        placeholder={!formValues[attr.id] ? suggestionText : ''}
                        disabled={isReadOnlyComputed}
                        onChange={(e) => handleInputChange(attr.id, e.target.value)}
                    />
                )}

                {attr.data_type === 'date' && (
                    <input
                        type="date"
                        className="w-full border rounded-md p-2 bg-background"
                        value={formValues[attr.id] || ''}
                        disabled={isReadOnlyComputed}
                        onChange={(e) => handleInputChange(attr.id, e.target.value)}
                    />
                )}

                {attr.data_type === 'boolean' && (
                    <div className="flex items-center gap-2">
                        <input
                            type="checkbox"
                            className="rounded border-gray-300"
                            checked={!!formValues[attr.id]}
                            disabled={isReadOnlyComputed}
                            onChange={(e) => handleInputChange(attr.id, e.target.checked)}
                        />
                        <span className="text-sm text-muted-foreground">Yes</span>
                    </div>
                )}

                {attr.data_type === 'select' && (
                    <select
                        className="w-full border rounded-md p-2 bg-background"
                        value={formValues[attr.id] || ''}
                        disabled={isReadOnlyComputed}
                        onChange={(e) => handleInputChange(attr.id, e.target.value)}
                    >
                        <option value="">
                            {suggestionText ? `AI: ${suggestionText}` : 'Select...'}
                        </option>
                        {getSelectOptions(attr.options).map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                        ))}
                    </select>
                )}

                {attr.data_type === 'tags' && (
                    <div className="space-y-2">
                        <input
                            type="text"
                            className="w-full border rounded-md p-2 bg-background"
                            value={tagsValue}
                            placeholder={!tagsValue ? (suggestionText || 'tag1, tag2, tag3') : ''}
                            disabled={isReadOnlyComputed}
                            onChange={(e) => {
                                const text = e.target.value;
                                setTagInputDrafts((prev) => ({ ...prev, [attr.id]: text }));
                                handleInputChange(attr.id, parseTagsInput(text));
                            }}
                            onBlur={() => {
                                setTagInputDrafts((prev) => {
                                    const current = prev[attr.id];
                                    if (current === undefined) return prev;
                                    return {
                                        ...prev,
                                        [attr.id]: tagsToInputValue(parseTagsInput(current)),
                                    };
                                });
                            }}
                        />
                        {Array.isArray(formValues[attr.id]) && formValues[attr.id].length > 0 && (
                            <div className="flex flex-wrap gap-1">
                                {formValues[attr.id].map((tag) => (
                                    <span key={`${attr.id}-${tag}`} className="px-2 py-0.5 rounded-full text-xs bg-muted border">
                                        {tag}
                                    </span>
                                ))}
                            </div>
                        )}
                    </div>
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
            </div>
        );
    };

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
                    <div className={`grid gap-4 ${showCoverPanel ? 'grid-cols-1 lg:grid-cols-[360px_minmax(0,1fr)]' : 'grid-cols-1'}`}>
                        {showCoverPanel && (
                            <aside className="border rounded-md bg-muted/20 p-3 h-fit lg:sticky lg:top-0">
                                <div className="flex items-center justify-between gap-2 mb-2">
                                    <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                                        Cover Preview
                                    </div>
                                    {coverUrl && (
                                        <button
                                            type="button"
                                            className="text-xs px-2 py-1 border rounded hover:bg-accent flex items-center gap-1"
                                            onClick={() => {
                                                setCoverZoomLevel(1);
                                                setIsCoverZoomOpen(true);
                                            }}
                                        >
                                            <ZoomIn size={12} />
                                            Zoom
                                        </button>
                                    )}
                                </div>
                                <div className="w-full aspect-[3/4] rounded-md overflow-hidden border bg-background">
                                    {coverLoading ? (
                                        <div className="w-full h-full flex items-center justify-center">
                                            <Loader2 className="animate-spin text-primary" size={24} />
                                        </div>
                                    ) : coverUrl ? (
                                        <button
                                            type="button"
                                            className="w-full h-full cursor-zoom-in"
                                            onClick={() => {
                                                setCoverZoomLevel(1);
                                                setIsCoverZoomOpen(true);
                                            }}
                                        >
                                            <img src={coverUrl} alt={item?.name || 'Cover'} className="w-full h-full object-cover" />
                                        </button>
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
                                    {orderedAttributes.length === 0 ? (
                                        <p className="text-sm text-muted-foreground italic">No attributes defined for this category.</p>
                                    ) : (
                                        categoryLayout ? (
                                            <div
                                                className="grid gap-3"
                                                style={{
                                                    gridTemplateColumns: `repeat(${categoryLayout.columns}, minmax(0, 1fr))`,
                                                    gridAutoRows: 'minmax(0, auto)',
                                                }}
                                            >
                                                {layoutItemsForRender.map((layoutItem, index) => {
                                                    const itemType = getLayoutItemType(layoutItem);
                                                    const x = Number(layoutItem.x || 0);
                                                    const y = Number(layoutItem.y || index);
                                                    const w = Number(layoutItem.w || categoryLayout.columns);
                                                    const style = {
                                                        gridColumn: `${Math.max(1, x + 1)} / span ${Math.max(1, w)}`,
                                                        gridRow: `${Math.max(1, y + 1)} / span 1`,
                                                    };

                                                    if (itemType === 'section') {
                                                        const sectionKey = String(layoutItem.item_id || `section_${index}`);
                                                        const sectionTitle = String(layoutItem.title || '').trim() || 'Section';
                                                        return (
                                                            <div key={`section-${sectionKey}`} className="min-w-0 pt-1" style={style}>
                                                                <div className="flex items-center gap-2">
                                                                    <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                                                                        {sectionTitle}
                                                                    </span>
                                                                    <div className="h-px flex-1 bg-border" />
                                                                </div>
                                                            </div>
                                                        );
                                                    }

                                                    const attr = categoryAttributesById.get(String(layoutItem.attribute_id));
                                                    if (!attr) return null;
                                                    return renderAttributeField(attr, 'min-w-0', style);
                                                })}
                                            </div>
                                        ) : (
                                            <div className={`grid gap-3 ${isComicPluginCategory ? 'md:grid-cols-2' : 'grid-cols-1'}`}>
                                                {orderedFieldGroups.map((group, groupIndex) => (
                                                    <div
                                                        key={`group-${groupIndex}`}
                                                        className={group.length > 1 && isComicPluginCategory ? 'contents' : 'md:col-span-2'}
                                                    >
                                                        {group.map((attr) => {
                                                            const fieldContainerClass = isComicPluginCategory
                                                                ? (
                                                                    READ_ONLY_COMIC_FIELD_KEYS.has(attr.plugin_field_key)
                                                                    || attr.plugin_field_key === 'summary'
                                                                    || attr.plugin_field_key === 'tags'
                                                                    || (attr.data_type === 'text' && !compactFieldKeys.has(attr.plugin_field_key || ''))
                                                                        ? 'md:col-span-2'
                                                                        : 'md:col-span-1'
                                                                )
                                                                : 'md:col-span-2';
                                                            return renderAttributeField(attr, fieldContainerClass);
                                                        })}
                                                    </div>
                                                ))}
                                            </div>
                                        )
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
            {isCoverZoomOpen && coverUrl && (
                <div
                    className="fixed inset-0 z-[70] bg-black/85 flex flex-col"
                    onClick={() => setIsCoverZoomOpen(false)}
                >
                    <div className="flex items-center justify-between p-3 border-b border-white/10">
                        <div className="text-xs text-white/80 truncate pr-2">
                            {item?.name || 'Cover'}
                        </div>
                        <div className="flex items-center gap-2">
                            <button
                                type="button"
                                className="px-2 py-1 text-white border border-white/20 rounded hover:bg-white/10"
                                onClick={(event) => {
                                    event.stopPropagation();
                                    setCoverZoomLevel((prev) => Math.max(1, Number((prev - 0.25).toFixed(2))));
                                }}
                            >
                                <ZoomOut size={14} />
                            </button>
                            <div className="text-xs text-white min-w-12 text-center">{Math.round(coverZoomLevel * 100)}%</div>
                            <button
                                type="button"
                                className="px-2 py-1 text-white border border-white/20 rounded hover:bg-white/10"
                                onClick={(event) => {
                                    event.stopPropagation();
                                    setCoverZoomLevel((prev) => Math.min(4, Number((prev + 0.25).toFixed(2))));
                                }}
                            >
                                <ZoomIn size={14} />
                            </button>
                            <button
                                type="button"
                                className="px-2 py-1 text-white border border-white/20 rounded hover:bg-white/10"
                                onClick={(event) => {
                                    event.stopPropagation();
                                    setIsCoverZoomOpen(false);
                                }}
                            >
                                <X size={14} />
                            </button>
                        </div>
                    </div>
                    <div
                        className="flex-1 overflow-auto p-4 flex items-center justify-center"
                        onClick={(event) => event.stopPropagation()}
                        onWheel={(event) => {
                            if (!event.ctrlKey) return;
                            event.preventDefault();
                            setCoverZoomLevel((prev) => {
                                const delta = event.deltaY < 0 ? 0.1 : -0.1;
                                return Math.max(1, Math.min(4, Number((prev + delta).toFixed(2))));
                            });
                        }}
                    >
                        <img
                            src={coverUrl}
                            alt={item?.name || 'Cover zoom'}
                            className="max-w-none rounded shadow-2xl"
                            style={{ transform: `scale(${coverZoomLevel})`, transformOrigin: 'center center' }}
                        />
                    </div>
                </div>
            )}
        </Modal>
    );
}
