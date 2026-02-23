import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GripVertical, Loader2, MoveHorizontal, Plus, RefreshCcw, Save, Trash2 } from 'lucide-react';
import Modal from './Modal';
import { metadataService } from '../services/metadata';
import { formLayoutToPayload, normalizeFormLayoutForCategory } from '../utils/metadata';
import { useToast } from '../contexts/ToastContext';

const ROW_HEIGHT_PX = 56;
const COLUMN_OPTIONS = [8, 10, 12, 16, 20, 24];

function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(value, maximum));
}

function rangesOverlap(startA, endA, startB, endB) {
    return startA < endB && startB < endA;
}

function getItemType(item) {
    if (String(item?.item_type || '').toLowerCase() === 'section') return 'section';
    return 'attribute';
}

function getItemKey(item) {
    if (getItemType(item) === 'section') {
        return `section:${String(item?.item_id || '')}`;
    }
    return `attribute:${String(item?.attribute_id || '')}`;
}

function canPlace(items, activeItemKey, x, y, w, columns) {
    if (x < 0 || y < 0 || w < 1 || x + w > columns) return false;
    return items.every((item) => {
        if (getItemKey(item) === activeItemKey) return true;
        if (item.y !== y) return true;
        return !rangesOverlap(x, x + w, item.x, item.x + item.w);
    });
}

function findFirstFreeSlot(items, activeItemKey, startY, w, columns) {
    for (let y = Math.max(0, startY); y <= 5000; y += 1) {
        for (let x = 0; x <= Math.max(0, columns - w); x += 1) {
            if (canPlace(items, activeItemKey, x, y, w, columns)) return { x, y };
        }
    }
    return null;
}

function findCollisions(items, anchorKey) {
    const anchor = items.find((item) => getItemKey(item) === anchorKey);
    if (!anchor) return [];
    return items
        .filter((item) => getItemKey(item) !== anchorKey)
        .filter((item) => item.y === anchor.y)
        .filter((item) => rangesOverlap(anchor.x, anchor.x + anchor.w, item.x, item.x + item.w))
        .sort((a, b) => a.x - b.x);
}

function applyPlacementWithDisplacement(items, targetKey, placement, columns) {
    const next = items.map((item) => ({ ...item }));
    const targetIndex = next.findIndex((item) => getItemKey(item) === targetKey);
    if (targetIndex < 0) return next;

    const target = next[targetIndex];
    const targetType = getItemType(target);
    const targetW = targetType === 'section' ? columns : clamp(placement.w, 1, columns);
    const targetX = targetType === 'section' ? 0 : clamp(placement.x, 0, columns - targetW);
    const targetY = Math.max(0, placement.y);
    target.x = targetX;
    target.y = targetY;
    target.w = targetW;

    const queue = [targetKey];
    const maxIterations = Math.max(50, next.length * 20);
    let iterations = 0;

    while (queue.length > 0 && iterations < maxIterations) {
        iterations += 1;
        const anchorKey = queue.shift();
        if (!anchorKey) continue;
        const anchor = next.find((item) => getItemKey(item) === anchorKey);
        if (!anchor) continue;

        const collisions = findCollisions(next, anchorKey);
        for (const collision of collisions) {
            const collisionKey = getItemKey(collision);
            const collisionType = getItemType(collision);
            const collisionW = collisionType === 'section' ? columns : clamp(collision.w, 1, columns);

            let slot = null;
            if (collisionType !== 'section') {
                for (let x = 0; x <= Math.max(0, columns - collisionW); x += 1) {
                    if (canPlace(next, collisionKey, x, anchor.y, collisionW, columns)) {
                        slot = { x, y: anchor.y };
                        break;
                    }
                }
            }

            if (!slot) {
                slot = findFirstFreeSlot(next, collisionKey, anchor.y + 1, collisionW, columns)
                    || findFirstFreeSlot(next, collisionKey, 0, collisionW, columns);
            }

            if (!slot) continue;
            collision.x = collisionType === 'section' ? 0 : slot.x;
            collision.y = slot.y;
            collision.w = collisionW;
            queue.push(collisionKey);
        }
    }

    return next;
}

function materializeLayout(layout) {
    const sorted = [...(layout?.items || [])].sort((a, b) => (a.y - b.y) || (a.x - b.x));
    const columns = Number(layout?.columns || 12);
    return {
        ...layout,
        items: sorted,
        ordered_attribute_ids: sorted
            .filter((item) => getItemType(item) === 'attribute')
            .map((item) => item.attribute_id),
        half_width_attribute_ids: sorted
            .filter((item) => getItemType(item) === 'attribute')
            .filter((item) => item.w <= Math.max(1, Math.floor(columns / 2)))
            .map((item) => item.attribute_id),
    };
}

export default function MetadataLayoutBuilderModal({
    isOpen,
    onClose,
    categories = [],
    onSaved,
}) {
    const { showToast } = useToast();
    const gridRef = useRef(null);

    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [layoutsByCategory, setLayoutsByCategory] = useState({});
    const [selectedCategoryId, setSelectedCategoryId] = useState('');
    const [layoutDraft, setLayoutDraft] = useState(null);
    const [interaction, setInteraction] = useState(null);

    const selectedCategory = useMemo(
        () => categories.find((category) => String(category.id) === String(selectedCategoryId)) || null,
        [categories, selectedCategoryId],
    );

    const attrById = useMemo(() => {
        const map = new Map();
        (selectedCategory?.attributes || []).forEach((attr) => {
            map.set(String(attr.id), attr);
        });
        return map;
    }, [selectedCategory]);

    const loadLayouts = useCallback(async () => {
        try {
            setLoading(true);
            const rows = await metadataService.listFormLayouts();
            const map = {};
            (rows || []).forEach((layout) => {
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
                        h: 1,
                    })),
                    ordered_attribute_ids: (layout.ordered_attribute_ids || []).map(String),
                    half_width_attribute_ids: (layout.half_width_attribute_ids || []).map(String),
                };
            });
            setLayoutsByCategory(map);

            setSelectedCategoryId((prev) => {
                if (prev && categories.some((cat) => String(cat.id) === String(prev))) return prev;
                const preferred = categories.find((cat) => cat.plugin_key === 'comics_core') || categories[0];
                return preferred ? String(preferred.id) : '';
            });
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to load metadata layouts';
            showToast(message, 'error');
        } finally {
            setLoading(false);
        }
    }, [categories, showToast]);

    useEffect(() => {
        if (!isOpen) return;
        loadLayouts();
    }, [isOpen, loadLayouts]);

    useEffect(() => {
        if (!isOpen) return;
        if (!selectedCategory) {
            setLayoutDraft(null);
            return;
        }
        const storedLayout = layoutsByCategory[String(selectedCategory.id)] || null;
        setLayoutDraft(materializeLayout(normalizeFormLayoutForCategory(selectedCategory, storedLayout)));
    }, [isOpen, selectedCategory, layoutsByCategory]);

    useEffect(() => {
        if (!interaction) return undefined;

        const onMouseMove = (event) => {
            setLayoutDraft((prev) => {
                if (!prev || !gridRef.current) return prev;
                const columns = Number(prev.columns || 12);
                const rect = gridRef.current.getBoundingClientRect();
                if (rect.width <= 0) return prev;
                const colWidth = rect.width / columns;
                const deltaCols = Math.round((event.clientX - interaction.startClientX) / colWidth);
                const deltaRows = Math.round((event.clientY - interaction.startClientY) / ROW_HEIGHT_PX);

                const sourceItems = Array.isArray(interaction.base_items)
                    ? interaction.base_items.map((item) => ({ ...item }))
                    : prev.items.map((item) => ({ ...item }));
                const index = sourceItems.findIndex((item) => getItemKey(item) === interaction.item_key);
                if (index < 0) return prev;
                const current = sourceItems[index];
                const itemType = getItemType(current);

                if (interaction.mode === 'move') {
                    const width = itemType === 'section' ? columns : current.w;
                    const nextX = itemType === 'section'
                        ? 0
                        : clamp(interaction.originX + deltaCols, 0, columns - width);
                    const nextY = Math.max(0, interaction.originY + deltaRows);

                    if (nextX === current.x && nextY === current.y && current.w === width) return prev;
                    const resolved = applyPlacementWithDisplacement(
                        sourceItems,
                        interaction.item_key,
                        { x: nextX, y: nextY, w: width },
                        columns,
                    );
                    return materializeLayout({ ...prev, items: resolved });
                } else {
                    if (itemType === 'section') return prev;
                    const maxWidth = Math.max(1, columns - current.x);
                    const requested = clamp(interaction.originW + deltaCols, 1, maxWidth);
                    if (requested === current.w) return prev;
                    const resolved = applyPlacementWithDisplacement(
                        sourceItems,
                        interaction.item_key,
                        { x: current.x, y: current.y, w: requested },
                        columns,
                    );
                    return materializeLayout({ ...prev, items: resolved });
                }
            });
        };

        const onMouseUp = () => {
            setInteraction(null);
        };

        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
        return () => {
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };
    }, [interaction]);

    const handleReset = () => {
        if (!selectedCategory) return;
        setLayoutDraft(materializeLayout(normalizeFormLayoutForCategory(selectedCategory, null)));
    };

    const handleColumnsChange = (columns) => {
        if (!selectedCategory || !layoutDraft) return;
        const nextLayout = normalizeFormLayoutForCategory(selectedCategory, {
            ...layoutDraft,
            columns,
        });
        setLayoutDraft(materializeLayout(nextLayout));
    };

    const handleAddSection = () => {
        if (!layoutDraft) return;
        setLayoutDraft((prev) => {
            if (!prev) return prev;
            const columns = Number(prev.columns || 12);
            const maxY = (prev.items || []).reduce((acc, item) => Math.max(acc, Number(item.y || 0)), 0);
            const sectionCount = (prev.items || []).filter((item) => getItemType(item) === 'section').length;
            const section = {
                item_type: 'section',
                item_id: `section_${Date.now()}_${sectionCount + 1}`,
                attribute_id: null,
                title: `Section ${sectionCount + 1}`,
                x: 0,
                y: maxY + 1,
                w: columns,
                h: 1,
            };
            return materializeLayout({
                ...prev,
                items: [...prev.items, section],
            });
        });
    };

    const handleSectionTitleChange = (itemKey, title) => {
        setLayoutDraft((prev) => {
            if (!prev) return prev;
            const nextItems = prev.items.map((item) => {
                if (getItemKey(item) !== itemKey) return item;
                return { ...item, title: title.slice(0, 80) };
            });
            return materializeLayout({ ...prev, items: nextItems });
        });
    };

    const handleRemoveSection = (itemKey) => {
        setLayoutDraft((prev) => {
            if (!prev) return prev;
            const nextItems = prev.items.filter((item) => getItemKey(item) !== itemKey);
            return materializeLayout({ ...prev, items: nextItems });
        });
    };

    const handleSave = async () => {
        if (!selectedCategory || !layoutDraft) return;
        try {
            setSaving(true);
            const payload = formLayoutToPayload(layoutDraft);
            const saved = await metadataService.saveFormLayout(selectedCategory.id, payload);
            setLayoutsByCategory((prev) => ({
                ...prev,
                [String(saved.category_id)]: {
                    columns: saved.columns,
                    row_height: saved.row_height,
                    items: (saved.items || []).map((item, index) => ({
                        item_type: String(item.item_type || (item.attribute_id ? 'attribute' : 'section')),
                        item_id: String(item.item_id || (item.attribute_id ? String(item.attribute_id) : `section_${index + 1}`)),
                        attribute_id: item.attribute_id ? String(item.attribute_id) : null,
                        title: item.title || null,
                        x: Number(item.x) || 0,
                        y: Number(item.y) || 0,
                        w: Number(item.w) || 12,
                        h: 1,
                    })),
                    ordered_attribute_ids: (saved.ordered_attribute_ids || []).map(String),
                    half_width_attribute_ids: (saved.half_width_attribute_ids || []).map(String),
                },
            }));
            showToast('Metadata layout saved', 'success');
            if (onSaved) onSaved(saved);
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to save metadata layout';
            showToast(message, 'error');
        } finally {
            setSaving(false);
        }
    };

    const columns = Number(layoutDraft?.columns || 12);
    const visibleItems = useMemo(
        () => (layoutDraft?.items || []).filter((item) => (
            getItemType(item) === 'section' || attrById.has(String(item.attribute_id))
        )),
        [layoutDraft, attrById],
    );
    const maxRow = visibleItems.reduce((acc, item) => Math.max(acc, Number(item.y || 0)), 0);
    const canvasRows = Math.max(maxRow + 3, 10);
    const canvasHeight = canvasRows * ROW_HEIGHT_PX;

    return (
        <Modal
            isOpen={isOpen}
            onClose={() => {
                if (saving) return;
                onClose();
            }}
            title="Metadata Layout Builder"
            maxWidthClass="max-w-6xl"
        >
            {loading ? (
                <div className="flex justify-center p-8">
                    <Loader2 className="animate-spin text-primary" size={32} />
                </div>
            ) : (
                <div className="space-y-4">
                    <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px_auto_auto_auto] items-end">
                        <div>
                            <label className="block text-sm font-medium mb-1">Category</label>
                            <select
                                className="w-full border rounded-md p-2 bg-background"
                                value={selectedCategoryId}
                                onChange={(event) => setSelectedCategoryId(event.target.value)}
                            >
                                {categories.map((category) => (
                                    <option key={category.id} value={category.id}>
                                        {category.name}
                                    </option>
                                ))}
                            </select>
                        </div>

                        <div>
                            <label className="block text-sm font-medium mb-1">Grid Columns</label>
                            <select
                                className="w-full border rounded-md p-2 bg-background"
                                value={columns}
                                onChange={(event) => handleColumnsChange(Number(event.target.value))}
                                disabled={!layoutDraft}
                            >
                                {COLUMN_OPTIONS.map((option) => (
                                    <option key={option} value={option}>
                                        {option} columns
                                    </option>
                                ))}
                            </select>
                        </div>

                        <button
                            type="button"
                            onClick={handleAddSection}
                            disabled={!layoutDraft || saving}
                            className="px-3 py-2 rounded-md border text-sm hover:bg-accent disabled:opacity-50 inline-flex items-center gap-2"
                        >
                            <Plus size={14} />
                            Add Section
                        </button>

                        <button
                            type="button"
                            onClick={handleReset}
                            disabled={!layoutDraft || saving}
                            className="px-3 py-2 rounded-md border text-sm hover:bg-accent disabled:opacity-50 inline-flex items-center gap-2"
                        >
                            <RefreshCcw size={14} />
                            Reset
                        </button>

                        <button
                            type="button"
                            onClick={handleSave}
                            disabled={!layoutDraft || saving}
                            className="px-3 py-2 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 disabled:opacity-50 inline-flex items-center gap-2"
                        >
                            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                            Save Layout
                        </button>
                    </div>

                    <div className="text-xs text-muted-foreground">
                        Drag blocks to reorder. Fields resize by columns; sections are full width with a compact title.
                    </div>

                    <div className="border rounded-md bg-muted/20 p-2 overflow-auto">
                        <div
                            ref={gridRef}
                            className="relative border rounded-md bg-background min-w-[760px]"
                            style={{
                                height: `${canvasHeight}px`,
                                backgroundImage: `
                                    linear-gradient(to right, rgba(148, 163, 184, 0.25) 1px, transparent 1px),
                                    linear-gradient(to bottom, rgba(148, 163, 184, 0.18) 1px, transparent 1px)
                                `,
                                backgroundSize: `${100 / columns}% 100%, 100% ${ROW_HEIGHT_PX}px`,
                            }}
                        >
                            {visibleItems.map((item) => {
                                const itemType = getItemType(item);
                                const itemKey = getItemKey(item);
                                const attr = itemType === 'attribute' ? attrById.get(String(item.attribute_id)) : null;
                                if (itemType === 'attribute' && !attr) return null;
                                const isActive = interaction?.item_key === itemKey;
                                const widthPercent = (item.w / columns) * 100;

                                return (
                                    <div
                                        key={itemKey}
                                        className={`absolute border rounded-md shadow-sm ${
                                            itemType === 'section' ? 'bg-primary/5 border-primary/25' : 'bg-card'
                                        } ${isActive ? 'ring-2 ring-primary border-primary/40' : ''}`}
                                        style={{
                                            left: `${(item.x / columns) * 100}%`,
                                            top: `${item.y * ROW_HEIGHT_PX + 4}px`,
                                            width: `calc(${widthPercent}% - 4px)`,
                                            height: `${ROW_HEIGHT_PX - 8}px`,
                                        }}
                                    >
                                        <div className="h-full flex items-center">
                                            <button
                                                type="button"
                                                onMouseDown={(event) => {
                                                    event.preventDefault();
                                                    event.stopPropagation();
                                                setInteraction({
                                                    mode: 'move',
                                                    item_key: itemKey,
                                                    startClientX: event.clientX,
                                                    startClientY: event.clientY,
                                                    originX: item.x,
                                                    originY: item.y,
                                                    originW: item.w,
                                                    base_items: (layoutDraft?.items || []).map((it) => ({ ...it })),
                                                });
                                            }}
                                            className="h-full w-7 border-r bg-muted/35 hover:bg-muted/50 cursor-grab active:cursor-grabbing flex items-center justify-center"
                                            title="Move"
                                            >
                                                <GripVertical size={12} className="text-muted-foreground" />
                                            </button>

                                            <div className="flex-1 min-w-0 px-2">
                                                {itemType === 'section' ? (
                                                    <div className="space-y-1">
                                                        <div className="flex items-center gap-2">
                                                            <input
                                                                type="text"
                                                                className="w-full text-xs font-semibold uppercase tracking-wide bg-transparent border rounded px-1.5 py-0.5"
                                                                value={item.title || ''}
                                                                placeholder="Section title"
                                                                onMouseDown={(event) => event.stopPropagation()}
                                                                onChange={(event) => handleSectionTitleChange(itemKey, event.target.value)}
                                                            />
                                                            <button
                                                                type="button"
                                                                className="p-1 rounded border text-muted-foreground hover:text-destructive hover:border-destructive/40"
                                                                onMouseDown={(event) => event.stopPropagation()}
                                                                onClick={(event) => {
                                                                    event.stopPropagation();
                                                                    handleRemoveSection(itemKey);
                                                                }}
                                                                title="Remove section"
                                                            >
                                                                <Trash2 size={12} />
                                                            </button>
                                                        </div>
                                                        <div className="h-px bg-border w-full" />
                                                    </div>
                                                ) : (
                                                    <>
                                                        <div className="text-xs font-semibold truncate">
                                                            {attr.name}
                                                        </div>
                                                        <div className="text-[11px] text-muted-foreground truncate">
                                                            {Math.round((item.w / columns) * 100)}% | X:{item.x + 1} Y:{item.y + 1}
                                                        </div>
                                                    </>
                                                )}
                                            </div>

                                            {itemType === 'attribute' && (
                                                <button
                                                    type="button"
                                                    onMouseDown={(event) => {
                                                        event.preventDefault();
                                                        event.stopPropagation();
                                                        setInteraction({
                                                            mode: 'resize',
                                                            item_key: itemKey,
                                                            startClientX: event.clientX,
                                                            startClientY: event.clientY,
                                                            originX: item.x,
                                                            originY: item.y,
                                                            originW: item.w,
                                                            base_items: (layoutDraft?.items || []).map((it) => ({ ...it })),
                                                        });
                                                    }}
                                                    className="h-full w-3 border-l bg-muted/30 hover:bg-muted/50 cursor-ew-resize flex items-center justify-center"
                                                    title="Resize width"
                                                >
                                                    <MoveHorizontal size={10} className="text-muted-foreground" />
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            )}
        </Modal>
    );
}
