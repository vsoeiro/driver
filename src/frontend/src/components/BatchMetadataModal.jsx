import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { metadataService } from '../services/metadata';
import { itemsService } from '../services/items';
import { jobsService } from '../services/jobs';
import { driveService } from '../services/drive';
import { getCategoryLibraryView } from '../metadataLibraries/categoryViews';
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
import { Loader2 } from 'lucide-react';
import Modal from './Modal';

const BatchMetadataModal = ({ isOpen, onClose, selectedItems, onSuccess, showToast }) => {
    const { t } = useTranslation();
    const [categories, setCategories] = useState([]);
    const [selectedCategory, setSelectedCategory] = useState('');
    const [attributeValues, setAttributeValues] = useState({});
    const [tagInputDrafts, setTagInputDrafts] = useState({});
    const [layoutMap, setLayoutMap] = useState({});
    const [applyRecursive, setApplyRecursive] = useState(false);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [coverUrl, setCoverUrl] = useState(null);
    const [coverLoading, setCoverLoading] = useState(false);

    const hasFolders = selectedItems.some(i => i.item_type === 'folder');

    const prefillFromSelection = useCallback(() => {
        const itemsWithMeta = selectedItems.filter(i => i.metadata);

        if (itemsWithMeta.length === 0) {
            setSelectedCategory('');
            setAttributeValues({});
            setTagInputDrafts({});
            return;
        }

        const firstCatId = itemsWithMeta[0].metadata.category_id;
        const allSameCategory = itemsWithMeta.every(
            i => i.metadata.category_id === firstCatId
        );

        if (!allSameCategory) {
            setSelectedCategory('');
            setAttributeValues({});
            setTagInputDrafts({});
            return;
        }

        setSelectedCategory(firstCatId);

        if (itemsWithMeta.length === 1) {
            setAttributeValues(itemsWithMeta[0].metadata.values || {});
            setTagInputDrafts({});
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
        setTagInputDrafts({});
    }, [selectedItems]);

    useEffect(() => {
        if (!isOpen || categories.length === 0 || selectedItems.length === 0) return;
        prefillFromSelection();
    }, [isOpen, categories, selectedItems, prefillFromSelection]);

    const loadCategories = useCallback(async () => {
        setLoading(true);
        try {
            const [data, layouts] = await Promise.all([
                metadataService.listCategories(),
                metadataService.listFormLayouts(),
            ]);
            setCategories(data);
            const map = {};
            (layouts || []).forEach((layout) => {
                if (!layout?.category_id) return;
                map[String(layout.category_id)] = {
                    columns: layout.columns,
                    row_height: layout.row_height,
                    hide_read_only_fields: !!layout.hide_read_only_fields,
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
            setTagInputDrafts({});
        }
    }, [isOpen, loadCategories]);

    const handleSave = async () => {
        if (!selectedCategory) return;
        setSaving(true);
        try {
            const promises = [];
            const groupedByAccount = {};

            for (const item of selectedItems) {
                if (!groupedByAccount[item.account_id]) {
                    groupedByAccount[item.account_id] = [];
                }
                groupedByAccount[item.account_id].push(item);
            }

            let recursiveJobs = 0;
            for (const [accountId, accountItems] of Object.entries(groupedByAccount)) {
                const folders = accountItems.filter(i => i.item_type === 'folder');
                const files = accountItems.filter(i => i.item_type !== 'folder');

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
                    recursiveJobs += folders.length;
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
            }

            await Promise.all(promises);

            if (applyRecursive && recursiveJobs > 0) {
                showToast(t('batchMetadata.recursiveJobsCreated', { count: recursiveJobs }), 'success');
            } else {
                showToast(t('batchMetadata.saved'), 'success');
            }

            onSuccess();
            onClose();
        } catch (error) {
            showToast(`${t('batchMetadata.failed')}: ${error.message}`, 'error');
        } finally {
            setSaving(false);
        }
    };

    const currentCategory = categories.find(c => String(c.id) === String(selectedCategory));
    const rawCategoryLayout = currentCategory ? layoutMap[String(currentCategory.id)] : null;
    const hasConfiguredLayout = !!(
        rawCategoryLayout
        && (
            (Array.isArray(rawCategoryLayout.items) && rawCategoryLayout.items.length > 0)
            || (Array.isArray(rawCategoryLayout.ordered_attribute_ids) && rawCategoryLayout.ordered_attribute_ids.length > 0)
        )
    );
    const categoryLayout = hasConfiguredLayout
        ? normalizeFormLayoutForCategory(currentCategory, rawCategoryLayout)
        : null;
    const orderedAttributes = sortAttributesForCategory(
        currentCategory,
        categoryLayout?.ordered_attribute_ids || null,
    );
    const hideReadOnlyFields = !!categoryLayout?.hide_read_only_fields;
    const isReadOnlyLibraryAttribute = (attr) => (
        ['comics_core', 'books_core'].includes(currentCategory?.plugin_key)
        && READ_ONLY_COMIC_FIELD_KEYS.has(attr?.plugin_field_key)
    );
    const visibleOrderedAttributes = orderedAttributes.filter(
        (attr) => !(hideReadOnlyFields && isReadOnlyLibraryAttribute(attr)),
    );
    const categoryAttributesById = new Map(
        (currentCategory?.attributes || []).map((attr) => [String(attr.id), attr]),
    );
    const layoutItemsForRender = categoryLayout
        ? resolveLayoutItemsForRender(categoryLayout.items || [], categoryLayout.columns)
        : [];
    const libraryView = getCategoryLibraryView(currentCategory);
    const coverAttr = currentCategory?.attributes?.find(
        (attr) => attr.plugin_field_key === libraryView?.gallery?.coverField
    );
    const coverAccountAttr = currentCategory?.attributes?.find(
        (attr) => attr.plugin_field_key === libraryView?.gallery?.coverAccountField
    );
    const singleItem = selectedItems.length === 1 ? selectedItems[0] : null;
    const coverItemId = coverAttr ? attributeValues?.[coverAttr.id] : null;
    const coverAccountId = coverAccountAttr
        ? attributeValues?.[coverAccountAttr.id]
        : singleItem?.account_id;
    const showCoverPanel = !!(
        singleItem &&
        singleItem.item_type !== 'folder' &&
        currentCategory &&
        coverAttr &&
        coverItemId
    );

    useEffect(() => {
        if (!isOpen || !showCoverPanel || !coverAccountId) {
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
    }, [isOpen, showCoverPanel, coverAccountId, coverItemId]);

    const renderAttributeInput = (attr, className = '', style = null) => {
        const isReadOnlyComputed = ['comics_core', 'books_core'].includes(currentCategory?.plugin_key)
            && READ_ONLY_COMIC_FIELD_KEYS.has(attr.plugin_field_key);
        const rawValue = attributeValues[attr.id];
        const value = rawValue ?? '';

        return (
            <div key={attr.id} className={className} style={style || undefined}>
                <label className="block text-xs font-medium mb-1 uppercase text-muted-foreground">
                    {attr.name} {attr.is_required && '*'}
                </label>

                {attr.data_type === 'select' && (
                    <select
                        className="w-full border rounded-md p-2 text-sm bg-background"
                        value={value}
                        disabled={isReadOnlyComputed}
                        onChange={(e) => setAttributeValues((prev) => ({ ...prev, [attr.id]: e.target.value }))}
                    >
                        <option value="">{t('batchMetadata.select')}</option>
                        {getSelectOptions(attr.options).map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                        ))}
                    </select>
                )}

                {attr.data_type === 'boolean' && (
                    <select
                        className="w-full border rounded-md p-2 text-sm bg-background"
                        value={rawValue === true ? 'true' : rawValue === false ? 'false' : ''}
                        disabled={isReadOnlyComputed}
                        onChange={(e) => {
                            const next = e.target.value === '' ? '' : e.target.value === 'true';
                            setAttributeValues((prev) => ({ ...prev, [attr.id]: next }));
                        }}
                    >
                        <option value="">{t('batchMetadata.select')}</option>
                        <option value="true">{t('common.yes')}</option>
                        <option value="false">{t('common.no')}</option>
                    </select>
                )}

                {attr.data_type === 'tags' && (
                    <input
                        type="text"
                        className="w-full border rounded-md p-2 text-sm bg-background"
                        value={tagInputDrafts[attr.id] ?? tagsToInputValue(rawValue ?? [])}
                        placeholder={t('batchMetadata.tagsPlaceholder')}
                        disabled={isReadOnlyComputed}
                        onChange={(e) => {
                            const text = e.target.value;
                            setTagInputDrafts((prev) => ({ ...prev, [attr.id]: text }));
                            setAttributeValues((prev) => ({ ...prev, [attr.id]: parseTagsInput(text) }));
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
                )}

                {!['select', 'boolean', 'tags'].includes(attr.data_type) && (
                    <input
                        type={attr.data_type === 'number' ? 'number' : attr.data_type === 'date' ? 'date' : 'text'}
                        className="w-full border rounded-md p-2 text-sm bg-background"
                        value={value}
                        disabled={isReadOnlyComputed}
                        onChange={(e) => setAttributeValues((prev) => ({ ...prev, [attr.id]: e.target.value }))}
                    />
                )}

                {isReadOnlyComputed && (
                    <div className="mt-1 text-xs text-muted-foreground">
                        {t('batchMetadata.mappedReadOnly')}
                    </div>
                )}
            </div>
        );
    };

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title={t('batchMetadata.title', { count: selectedItems.length })}
            maxWidthClass={showCoverPanel ? 'max-w-5xl' : 'max-w-2xl'}
        >
            <div className={`grid gap-4 ${showCoverPanel ? 'grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)]' : 'grid-cols-1'}`}>
                {showCoverPanel && (
                    <aside className="border rounded-md bg-muted/20 p-3 h-fit lg:sticky lg:top-0">
                        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                            {t('batchMetadata.coverPreview')}
                        </div>
                        <div className="w-full aspect-[3/4] rounded-md overflow-hidden border bg-background">
                            {coverLoading ? (
                                <div className="w-full h-full flex items-center justify-center">
                                    <Loader2 className="animate-spin text-primary" size={24} />
                                </div>
                            ) : coverUrl ? (
                                <img src={coverUrl} alt={singleItem?.name || t('batchMetadata.cover')} className="w-full h-full object-cover" />
                            ) : (
                                <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground">
                                    {t('batchMetadata.noCover')}
                                </div>
                            )}
                        </div>
                    </aside>
                )}

                <div className="space-y-4">
                {loading ? (
                    <div className="flex justify-center"><Loader2 className="animate-spin" /></div>
                ) : (
                    <>
                        <div>
                            <label className="block text-sm font-medium mb-1">{t('batchMetadata.category')}</label>
                            <select
                                className="w-full border rounded-md p-2 bg-background"
                                value={selectedCategory}
                                onChange={(e) => {
                                    setSelectedCategory(e.target.value);
                                    setAttributeValues({});
                                }}
                            >
                                <option value="">{t('batchMetadata.selectCategory')}</option>
                                {categories.map(c => (
                                    <option key={c.id} value={c.id}>{c.name}</option>
                                ))}
                            </select>
                        </div>

                        {currentCategory && (
                            <div className="space-y-3 border p-3 rounded-md bg-muted/20">
                                {categoryLayout ? (
                                    <div
                                        className="grid gap-3"
                                        style={{
                                            gridTemplateColumns: `repeat(${categoryLayout.columns}, minmax(0, 1fr))`,
                                            gridAutoRows: 'minmax(0, auto)',
                                        }}
                                    >
                                        {layoutItemsForRender.map((layoutItem, index) => {
                                            const itemType = String(layoutItem.item_type || '').toLowerCase() === 'section' ? 'section' : 'attribute';
                                            const x = Number(layoutItem.x || 0);
                                            const y = Number(layoutItem.y || index);
                                            const w = Number(layoutItem.w || categoryLayout.columns);
                                            const style = {
                                                gridColumn: `${Math.max(1, x + 1)} / span ${Math.max(1, w)}`,
                                                gridRow: `${Math.max(1, y + 1)} / span 1`,
                                            };

                                            if (itemType === 'section') {
                                                const sectionKey = String(layoutItem.item_id || `section_${index}`);
                                                const sectionTitle = String(layoutItem.title || '').trim() || t('batchMetadata.section');
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
                                            if (hideReadOnlyFields && isReadOnlyLibraryAttribute(attr)) return null;
                                            return renderAttributeInput(attr, 'min-w-0', style);
                                        })}
                                    </div>
                                ) : (
                                    <div className="space-y-3">
                                        {visibleOrderedAttributes.map((attr) => renderAttributeInput(attr))}
                                    </div>
                                )}
                            </div>
                        )}

                        {hasFolders && (
                            <label className="status-badge status-badge-warning flex items-center gap-2 p-3 text-sm">
                                <input
                                    type="checkbox"
                                    checked={applyRecursive}
                                    onChange={(e) => setApplyRecursive(e.target.checked)}
                                />
                                {t('batchMetadata.applyRecursive')}
                            </label>
                        )}
                    </>
                )}

                <div className="flex justify-end gap-2 pt-2">
                    <button onClick={onClose} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">{t('common.cancel')}</button>
                    <button
                        onClick={handleSave}
                        disabled={saving || !selectedCategory}
                        className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
                    >
                        {saving && <Loader2 className="animate-spin" size={14} />}
                        {t('batchMetadata.saveChanges')}
                    </button>
                </div>
                </div>
            </div>
        </Modal>
    );
};

export default BatchMetadataModal;
