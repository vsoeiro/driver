
import { Fragment, useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { PlayCircle, Trash2, Plus, Eye, Loader2, Folder, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import { useToast } from '../contexts/ToastContext';
import { useWorkspacePage } from '../contexts/WorkspaceContext';
import { getSelectOptions, parseTagsInput, tagsToInputValue } from '../utils/metadata';
import { useAccountsActions } from '../features/accounts/hooks/useAccountsData';
import { useDriveActions } from '../features/drive/hooks/useDriveData';
import { useJobsActions } from '../features/jobs/hooks/useJobsData';
import { useMetadataActions } from '../features/metadata/hooks/useMetadataData';

const DEFAULT_FORM = {
    name: '',
    description: '',
    account_id: '',
    path_prefix: '',
    path_contains: '',
    include_folders: false,
    target_category_id: '',
    apply_metadata: true,
    apply_remove_metadata: false,
    apply_rename: false,
    rename_template: '',
    apply_move: false,
    destination_account_id: '',
    destination_folder_id: 'root',
    destination_path_template: '',
    metadata_filters: [],
};

const TEXT_OPERATORS = [
    { value: 'contains', label: 'contains' },
    { value: 'not_contains', label: 'notContains' },
    { value: 'equals', label: 'equals' },
    { value: 'not_equals', label: 'notEquals' },
    { value: 'starts_with', label: 'startsWith' },
    { value: 'ends_with', label: 'endsWith' },
    { value: 'is_empty', label: 'isEmpty' },
    { value: 'is_not_empty', label: 'isNotEmpty' },
];

const NUMBER_OPERATORS = [
    { value: 'equals', label: 'equals' },
    { value: 'not_equals', label: 'notEquals' },
    { value: 'gt', label: 'greaterThan' },
    { value: 'gte', label: 'greaterThanOrEqual' },
    { value: 'lt', label: 'lessThan' },
    { value: 'lte', label: 'lessThanOrEqual' },
    { value: 'is_empty', label: 'isEmpty' },
    { value: 'is_not_empty', label: 'isNotEmpty' },
];

const BOOLEAN_OPERATORS = [
    { value: 'equals', label: 'equals' },
    { value: 'not_equals', label: 'notEquals' },
    { value: 'is_empty', label: 'isEmpty' },
    { value: 'is_not_empty', label: 'isNotEmpty' },
];

const normalizeToken = (value) =>
    String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^A-Za-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '')
        .toUpperCase();

const getPendingTemplateToken = (value) => {
    const text = String(value || '');
    const idx = text.lastIndexOf('{{');
    if (idx < 0) return null;
    const rest = text.slice(idx + 2);
    if (rest.includes('}}')) return null;
    const ifMatch = rest.match(/^#if\s*(.*)$/i);
    if (ifMatch) {
        return { start: idx, query: normalizeToken(ifMatch[1] || ''), mode: 'if' };
    }
    return { start: idx, query: rest.trim().toUpperCase(), mode: 'token' };
};

const createDefaultFilter = () => ({
    source: 'path',
    attribute_id: null,
    operator: 'contains',
    value: '',
});

const formatBreadcrumbLabel = (breadcrumb) => {
    const cleanPath = (breadcrumb || []).filter((part) => String(part?.name || '').toLowerCase() !== 'root');
    if (cleanPath.length === 0) return 'Root';
    return `/${cleanPath.map((part) => part.name).join('/')}`;
};

const normalizePreviewResponse = (data) => ({
    total_matches: Number(data?.total_matches || 0),
    to_change: Number(data?.to_change || 0),
    already_compliant: Number(data?.already_compliant || 0),
    sample_item_ids: Array.isArray(data?.sample_item_ids) ? data.sample_item_ids : [],
});

export default function RulesManager() {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const location = useLocation();
    const { showToast } = useToast();
    const { getAccounts } = useAccountsActions();
    const { createFolder, getFiles, getFolderFiles, getPath } = useDriveActions();
    const { createApplyRuleJob } = useJobsActions();
    const {
        listRules,
        listCategories,
        createRule,
        previewRule,
        deleteRule,
    } = useMetadataActions();
    const [rules, setRules] = useState([]);
    const [categories, setCategories] = useState([]);
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [previewing, setPreviewing] = useState(false);
    const [preview, setPreview] = useState(null);
    const [previewLabel, setPreviewLabel] = useState('');
    const previewRef = useRef(null);
    const [form, setForm] = useState(DEFAULT_FORM);
    const [targetValues, setTargetValues] = useState({});
    const [destinationPath, setDestinationPath] = useState([]);
    const [destinationFolders, setDestinationFolders] = useState([]);
    const [destinationFolderLoading, setDestinationFolderLoading] = useState(false);
    const [folderLabels, setFolderLabels] = useState({});
    const [folderPickerOpen, setFolderPickerOpen] = useState(false);
    const [newFolderName, setNewFolderName] = useState('');
    const [creatingFolder, setCreatingFolder] = useState(false);
    const [templateSuggestField, setTemplateSuggestField] = useState(null);

    const selectedCategory = useMemo(
        () => categories.find((category) => category.id === form.target_category_id),
        [categories, form.target_category_id]
    );

    const categoryAttributesById = useMemo(() => {
        const map = new Map();
        (selectedCategory?.attributes || []).forEach((attribute) => {
            map.set(attribute.id, attribute);
        });
        return map;
    }, [selectedCategory]);

    const availableFilterFields = useMemo(() => {
        const fields = [{ source: 'path', id: 'path', label: t('rules.path') }];
        (selectedCategory?.attributes || []).forEach((attribute) => {
            fields.push({ source: 'metadata', id: attribute.id, label: attribute.name });
        });
        return fields;
    }, [selectedCategory, t]);

    const placeholderTokens = useMemo(() => {
        const tokens = new Set(['EXT', 'EXTENSION', 'NOME_ATUAL', 'CURRENT_NAME', 'STEM', 'ITEM_ID']);
        (selectedCategory?.attributes || []).forEach((attribute) => {
            const nameToken = normalizeToken(attribute.name);
            if (nameToken) tokens.add(nameToken);
            if (attribute.plugin_field_key) {
                const pluginToken = normalizeToken(attribute.plugin_field_key);
                if (pluginToken) tokens.add(pluginToken);
            }
        });
        return Array.from(tokens).sort((a, b) => a.localeCompare(b));
    }, [selectedCategory]);

    const templateSuggestionState = useMemo(() => {
        if (!templateSuggestField) return null;
        return getPendingTemplateToken(form[templateSuggestField]);
    }, [templateSuggestField, form]);

    const templateSuggestions = useMemo(() => {
        if (!templateSuggestField) return [];
        if (!templateSuggestionState) return [];
        return placeholderTokens.filter((token) => token.includes(templateSuggestionState.query)).slice(0, 12);
    }, [templateSuggestField, templateSuggestionState, placeholderTokens]);

    const normalizedTargetValues = useMemo(() => {
        const values = {};
        Object.entries(targetValues).forEach(([key, value]) => {
            if (value !== '' && value !== null && value !== undefined) values[key] = value;
        });
        return values;
    }, [targetValues]);

    const normalizedFilters = useMemo(
        () =>
            (form.metadata_filters || [])
                .map((filter) => ({
                    source: filter.source || 'metadata',
                    attribute_id: filter.source === 'metadata' ? filter.attribute_id || null : null,
                    operator: filter.operator || 'equals',
                    value: filter.value,
                }))
                .filter((filter) => {
                    if (filter.source === 'metadata' && !filter.attribute_id) return false;
                    if (filter.operator === 'is_empty' || filter.operator === 'is_not_empty') return true;
                    if (Array.isArray(filter.value)) return filter.value.length > 0;
                    return filter.value !== '' && filter.value !== null && filter.value !== undefined;
                }),
        [form.metadata_filters]
    );

    const loadData = useCallback(async () => {
        setLoading(true);
        try {
            const [rulesData, categoriesData, accountsData] = await Promise.all([
                listRules(),
                listCategories(),
                getAccounts(),
            ]);
            setRules(rulesData);
            setCategories(categoriesData);
            setAccounts(accountsData);
        } catch {
            showToast(t('rules.failedLoad'), 'error');
        } finally {
            setLoading(false);
        }
    }, [getAccounts, listCategories, listRules, showToast, t]);

    const loadDestinationFolders = useCallback(async (accountId, folderId) => {
        if (!accountId) {
            setDestinationFolders([]);
            return;
        }
        setDestinationFolderLoading(true);
        try {
            const data = folderId === 'root' ? await getFiles(accountId) : await getFolderFiles(accountId, folderId);
            setDestinationFolders((data.items || []).filter((entry) => entry.item_type === 'folder'));
        } catch (error) {
            showToast(`${t('rules.failedLoadFolder')}: ${error.message}`, 'error');
            setDestinationFolders([]);
        } finally {
            setDestinationFolderLoading(false);
        }
    }, [getFiles, getFolderFiles, showToast, t]);

    useEffect(() => {
        loadData();
    }, [loadData]);

    useEffect(() => {
        setTargetValues({});
    }, [form.target_category_id]);

    useEffect(() => {
        if (!selectedCategory) {
            setForm((prev) => ({ ...prev, metadata_filters: [] }));
            return;
        }
        const attrIds = new Set(selectedCategory.attributes.map((attribute) => attribute.id));
        setForm((prev) => ({
            ...prev,
            metadata_filters: (prev.metadata_filters || []).filter(
                (filter) => filter.source === 'path' || (filter.attribute_id && attrIds.has(filter.attribute_id))
            ),
        }));
    }, [selectedCategory]);

    useEffect(() => {
        if (!form.apply_move || form.destination_account_id || accounts.length === 0) return;
        setForm((prev) => ({ ...prev, destination_account_id: prev.account_id || accounts[0].id, destination_folder_id: 'root' }));
    }, [form.apply_move, form.destination_account_id, form.account_id, accounts]);

    useEffect(() => {
        if (!form.apply_move || !form.destination_account_id) return;
        loadDestinationFolders(form.destination_account_id, form.destination_folder_id || 'root');
    }, [form.apply_move, form.destination_account_id, form.destination_folder_id, loadDestinationFolders]);

    useEffect(() => {
        if (!form.apply_move || !form.destination_account_id || !form.destination_folder_id) return;
        if (form.destination_folder_id === 'root') {
            setFolderLabels((prev) => ({ ...prev, [`${form.destination_account_id}:root`]: t('moveModal.root') }));
            return;
        }
        const cacheKey = `${form.destination_account_id}:${form.destination_folder_id}`;
        if (folderLabels[cacheKey]) return;

        let cancelled = false;
        const loadFolderLabel = async () => {
            try {
                const pathData = await getPath(form.destination_account_id, form.destination_folder_id);
                if (cancelled) return;
                setFolderLabels((prev) => ({
                    ...prev,
                    [cacheKey]: formatBreadcrumbLabel(pathData?.breadcrumb),
                }));
            } catch {
                if (cancelled) return;
                setFolderLabels((prev) => ({
                    ...prev,
                    [cacheKey]: form.destination_folder_id,
                }));
            }
        };

        loadFolderLabel();
        return () => {
            cancelled = true;
        };
    }, [form.apply_move, form.destination_account_id, form.destination_folder_id, folderLabels, getPath, t]);

    useEffect(() => {
        const moveRules = rules.filter((rule) => rule.apply_move && rule.destination_account_id && rule.destination_folder_id);
        if (moveRules.length === 0) return;

        let cancelled = false;
        const loadRuleFolderLabels = async () => {
            const pending = [];
            for (const rule of moveRules) {
                const folderId = rule.destination_folder_id || 'root';
                const accountId = rule.destination_account_id;
                const cacheKey = `${accountId}:${folderId}`;
                if (folderLabels[cacheKey]) continue;
                pending.push({ accountId, folderId, cacheKey });
            }
            if (pending.length === 0) return;

            const resolved = await Promise.all(
                pending.map(async ({ accountId, folderId, cacheKey }) => {
                    if (folderId === 'root') {
                        return { cacheKey, label: t('moveModal.root') };
                    }
                    try {
                        const pathData = await getPath(accountId, folderId);
                        return { cacheKey, label: formatBreadcrumbLabel(pathData?.breadcrumb) };
                    } catch {
                        return { cacheKey, label: folderId };
                    }
                })
            );

            if (cancelled) return;
            setFolderLabels((prev) => {
                const next = { ...prev };
                resolved.forEach(({ cacheKey, label }) => {
                    next[cacheKey] = label;
                });
                return next;
            });
        };

        loadRuleFolderLabels();
        return () => {
            cancelled = true;
        };
    }, [folderLabels, getPath, rules, t]);

    useEffect(() => {
        if (form.apply_move) return;
        setFolderPickerOpen(false);
        setNewFolderName('');
    }, [form.apply_move]);

    useEffect(() => {
        if (!preview || !previewRef.current) return;
        previewRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, [preview]);

    const handleCreateRule = async (e) => {
        e.preventDefault();
        if (!form.target_category_id) {
            showToast(t('rules.chooseCategory'), 'error');
            return;
        }

        setSaving(true);
        try {
            await createRule({
                name: form.name,
                description: form.description || null,
                account_id: form.account_id || null,
                path_prefix: null,
                path_contains: null,
                include_folders: form.include_folders,
                target_category_id: form.target_category_id,
                target_values: normalizedTargetValues,
                apply_metadata: form.apply_metadata,
                apply_remove_metadata: form.apply_remove_metadata,
                apply_rename: form.apply_rename,
                rename_template: form.rename_template || null,
                apply_move: form.apply_move,
                destination_account_id: form.destination_account_id || null,
                destination_folder_id: form.destination_folder_id || 'root',
                destination_path_template: form.destination_path_template || null,
                metadata_filters: normalizedFilters,
                is_active: true,
                priority: 100,
            });
            setForm(DEFAULT_FORM);
            setTargetValues({});
            setPreview(null);
            setDestinationPath([]);
            setDestinationFolders([]);
            setTemplateSuggestField(null);
            showToast(t('rules.created'), 'success');
            loadData();
        } catch {
            showToast(t('rules.failedCreate'), 'error');
        } finally {
            setSaving(false);
        }
    };

    const handlePreview = async () => {
        setPreviewing(true);
        setPreviewLabel(form.name || t('rules.preview'));
        try {
            const data = await previewRule({
                account_id: form.account_id || null,
                path_prefix: null,
                path_contains: null,
                include_folders: form.include_folders,
                target_category_id: form.target_category_id,
                target_values: normalizedTargetValues,
                apply_metadata: form.apply_metadata,
                apply_remove_metadata: form.apply_remove_metadata,
                apply_rename: form.apply_rename,
                rename_template: form.rename_template || null,
                apply_move: form.apply_move,
                destination_account_id: form.destination_account_id || null,
                destination_folder_id: form.destination_folder_id || 'root',
                destination_path_template: form.destination_path_template || null,
                metadata_filters: normalizedFilters,
                limit: 10,
            });
            const normalized = normalizePreviewResponse(data);
            setPreview(normalized);
            showToast(
                t('rules.previewLine', {
                    matches: normalized.total_matches,
                    change: normalized.to_change,
                    compliant: normalized.already_compliant,
                }),
                'info'
            );
        } catch {
            showToast(t('rules.failedPreview'), 'error');
        } finally {
            setPreviewing(false);
        }
    };

    const handlePreviewRule = async (rule) => {
        setPreviewing(true);
        setPreviewLabel(rule.name || t('rules.preview'));
        try {
            const data = await previewRule({
                account_id: rule.account_id || null,
                path_prefix: rule.path_prefix || null,
                path_contains: rule.path_contains || null,
                include_folders: Boolean(rule.include_folders),
                target_category_id: rule.target_category_id,
                target_values: rule.target_values || {},
                apply_metadata: Boolean(rule.apply_metadata),
                apply_remove_metadata: Boolean(rule.apply_remove_metadata),
                apply_rename: Boolean(rule.apply_rename),
                rename_template: rule.rename_template || null,
                apply_move: Boolean(rule.apply_move),
                destination_account_id: rule.destination_account_id || null,
                destination_folder_id: rule.destination_folder_id || 'root',
                destination_path_template: rule.destination_path_template || null,
                metadata_filters: rule.metadata_filters || [],
                limit: 10,
            });
            const normalized = normalizePreviewResponse(data);
            setPreview(normalized);
            showToast(
                t('rules.previewLine', {
                    matches: normalized.total_matches,
                    change: normalized.to_change,
                    compliant: normalized.already_compliant,
                }),
                'info'
            );
        } catch {
            showToast(t('rules.failedPreview'), 'error');
        } finally {
            setPreviewing(false);
        }
    };

    const handleApplyRule = async (ruleId) => {
        try {
            await createApplyRuleJob(ruleId);
            showToast(t('rules.applyJobCreated'), 'success');
        } catch {
            showToast(t('rules.failedApplyJob'), 'error');
        }
    };

    const handleDeleteRule = async (ruleId) => {
        try {
            await deleteRule(ruleId);
            showToast(t('rules.deleted'), 'success');
            loadData();
        } catch {
            showToast(t('rules.failedDelete'), 'error');
        }
    };

    const setAttributeValue = (attribute, rawValue) => {
        let value = rawValue;
        if (attribute.data_type === 'number') value = rawValue === '' ? '' : Number(rawValue);
        setTargetValues((prev) => ({ ...prev, [attribute.id]: value }));
    };

    const addFilter = () => {
        setForm((prev) => ({ ...prev, metadata_filters: [...(prev.metadata_filters || []), createDefaultFilter()] }));
    };

    const updateFilter = (index, updates) => {
        setForm((prev) => ({
            ...prev,
            metadata_filters: (prev.metadata_filters || []).map((filter, currentIndex) => {
                if (currentIndex !== index) return filter;
                return { ...filter, ...updates };
            }),
        }));
    };

    const removeFilter = (index) => {
        setForm((prev) => ({ ...prev, metadata_filters: (prev.metadata_filters || []).filter((_, currentIndex) => currentIndex !== index) }));
    };

    const resolveFilterContext = (filter) => {
        if (filter.source === 'path') return { dataType: 'text', operators: TEXT_OPERATORS, attribute: null };
        const attribute = categoryAttributesById.get(filter.attribute_id);
        if (!attribute) return { dataType: 'text', operators: TEXT_OPERATORS, attribute: null };
        if (attribute.data_type === 'number' || attribute.data_type === 'date') return { dataType: attribute.data_type, operators: NUMBER_OPERATORS, attribute };
        if (attribute.data_type === 'boolean') return { dataType: 'boolean', operators: BOOLEAN_OPERATORS, attribute };
        return { dataType: attribute.data_type, operators: TEXT_OPERATORS, attribute };
    };

    const navigateDestinationFolder = (folder) => {
        setDestinationPath((prev) => [...prev, folder]);
        setForm((prev) => ({ ...prev, destination_folder_id: folder.id }));
    };

    const navigateDestinationUp = () => {
        setDestinationPath((prev) => {
            if (prev.length === 0) return prev;
            const nextPath = prev.slice(0, -1);
            const nextFolderId = nextPath.length > 0 ? nextPath[nextPath.length - 1].id : 'root';
            setForm((current) => ({ ...current, destination_folder_id: nextFolderId }));
            return nextPath;
        });
    };

    const handleDestinationAccountChange = (value) => {
        setDestinationPath([]);
        setForm((prev) => ({ ...prev, destination_account_id: value, destination_folder_id: 'root' }));
    };

    const handleCreateDestinationFolder = async () => {
        if (!form.destination_account_id) {
            showToast(t('rules.destinationAccountRequired'), 'error');
            return;
        }
        const name = (newFolderName || '').trim();
        if (!name) {
            showToast(t('rules.folderNameRequired'), 'error');
            return;
        }
        setCreatingFolder(true);
        try {
            const created = await createFolder(
                form.destination_account_id,
                form.destination_folder_id || 'root',
                name
            );
            setNewFolderName('');
            setDestinationPath((prev) => [...prev, { id: created.id, name: created.name }]);
            setForm((prev) => ({ ...prev, destination_folder_id: created.id }));
            await loadDestinationFolders(form.destination_account_id, created.id);
            showToast(t('rules.folderCreated'), 'success');
        } catch (error) {
            showToast(`${t('rules.failedCreateFolder')}: ${error.message}`, 'error');
        } finally {
            setCreatingFolder(false);
        }
    };

    const setTemplateValue = (field, value) => {
        setForm((prev) => ({ ...prev, [field]: value }));
        const pending = getPendingTemplateToken(value);
        setTemplateSuggestField(pending ? field : null);
    };

    const insertTemplateToken = (field, token) => {
        const current = form[field] || '';
        const pending = getPendingTemplateToken(current);
        const snippet = pending?.mode === 'if' ? `{{#if ${token}}}` : `{{${token}}}`;
        if (!pending) setForm((prev) => ({ ...prev, [field]: `${current}${snippet}` }));
        else setForm((prev) => ({ ...prev, [field]: `${current.slice(0, pending.start)}${snippet}` }));
        setTemplateSuggestField(null);
    };

    const renderAttributeInput = (attribute) => {
        const value = targetValues[attribute.id] ?? '';
        if (attribute.data_type === 'select') {
            return (
                <select className="w-full border rounded-md p-2 text-sm bg-background" value={value} onChange={(e) => setAttributeValue(attribute, e.target.value)}>
                    <option value="">{t('rules.ignore')}</option>
                    {getSelectOptions(attribute.options).map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
            );
        }
        if (attribute.data_type === 'boolean') {
            return (
                <select className="w-full border rounded-md p-2 text-sm bg-background" value={value === '' ? '' : String(value)} onChange={(e) => setAttributeValue(attribute, e.target.value === '' ? '' : e.target.value === 'true')}>
                    <option value="">{t('rules.ignore')}</option>
                    <option value="true">{t('common.yes')}</option>
                    <option value="false">{t('common.no')}</option>
                </select>
            );
        }
        if (attribute.data_type === 'tags') {
            return <input type="text" className="w-full border rounded-md p-2 text-sm bg-background" value={tagsToInputValue(value)} onChange={(e) => setAttributeValue(attribute, parseTagsInput(e.target.value))} placeholder={t('rules.setTags', { name: attribute.name })} />;
        }
        return <input type={attribute.data_type === 'number' ? 'number' : attribute.data_type === 'date' ? 'date' : 'text'} className="w-full border rounded-md p-2 text-sm bg-background" value={value} onChange={(e) => setAttributeValue(attribute, e.target.value)} placeholder={t('rules.setOptional', { name: attribute.name })} />;
    };

    const getRuleActions = (rule) => {
        const actions = [];
        if (rule.apply_metadata) actions.push(t('rules.applyMetadataValues'));
        if (rule.apply_remove_metadata) actions.push(t('rules.removeMetadata'));
        if (rule.apply_rename) actions.push(`${t('rules.renameItem')}: ${rule.rename_template || '-'}`);
        if (rule.apply_move) {
            const cacheKey = `${rule.destination_account_id}:${rule.destination_folder_id || 'root'}`;
            const folderLabel = folderLabels[cacheKey] || rule.destination_folder_id || 'root';
            actions.push(`${t('rules.moveItem')}: ${folderLabel} / ${(rule.destination_path_template || '-')}`);
        }
        return actions;
    };

    const getSelectedFolderLabel = () => {
        if (!form.destination_account_id) return form.destination_folder_id || 'root';
        const cacheKey = `${form.destination_account_id}:${form.destination_folder_id || 'root'}`;
        return folderLabels[cacheKey] || form.destination_folder_id || 'root';
    };

    const getRuleScope = (rule) => {
        if (Array.isArray(rule.metadata_filters) && rule.metadata_filters.length > 0) return t('rules.filtersCount', { count: rule.metadata_filters.length });
        if (rule.path_prefix || rule.path_contains) return `${rule.path_prefix || '-'}${rule.path_contains ? ` | ${t('rules.contains')}: ${rule.path_contains}` : ''}`;
        return '-';
    };

    const builderActionCount = Number(Boolean(form.apply_metadata)) + Number(Boolean(form.apply_remove_metadata)) + Number(Boolean(form.apply_rename)) + Number(Boolean(form.apply_move));

    useWorkspacePage(useMemo(() => ({
        title: t('rules.title'),
        subtitle: t('workspace.automationSubtitle', { defaultValue: 'Regras com preview, impacto e conexoes para biblioteca, jobs e IA.' }),
        entityType: 'automation',
        entityId: 'rules',
        sourceRoute: location.pathname,
        activeFilters: [
            form.target_category_id ? t('workspace.filterCategory', { value: selectedCategory?.name || form.target_category_id, defaultValue: `Categoria: ${selectedCategory?.name || form.target_category_id}` }) : '',
            form.account_id ? t('workspace.filterAccount', { value: form.account_id, defaultValue: `Conta: ${form.account_id}` }) : '',
        ].filter(Boolean),
        metrics: [
            t('workspace.ruleCount', { count: rules.length, defaultValue: `${rules.length} regra(s)` }),
            t('rules.filtersCount', { count: normalizedFilters.length }),
            t('workspace.actionsSelected', { count: builderActionCount, defaultValue: `${builderActionCount} acao(oes)` }),
        ],
        suggestedPrompts: [
            t('workspace.aiPrompts.ruleReview', { defaultValue: 'Revise esta automacao e aponte riscos ou melhorias.' }),
            t('workspace.aiPrompts.recommend', { defaultValue: 'Sugira as proximas acoes com maior impacto.' }),
            t('workspace.aiPrompts.summarize', { defaultValue: 'Resuma o contexto atual e destaque riscos.' }),
        ],
    }), [builderActionCount, form.account_id, form.target_category_id, location.pathname, normalizedFilters.length, rules.length, selectedCategory?.name, t]));

    return (
        <div className="app-page">
            <div className="page-header">
                <h1 className="page-title">{t('rules.title')}</h1>
                <p className="page-subtitle">{t('rules.subtitle')}</p>
            </div>

            <div className="mb-4 grid gap-3 md:grid-cols-3">
                <div className="surface-card p-4">
                    <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('rules.rule')}</div>
                    <div className="mt-2 text-2xl font-semibold">{rules.length}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{t('rules.noRulesHelp')}</div>
                </div>
                <div className="surface-card p-4">
                    <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('rules.filters')}</div>
                    <div className="mt-2 text-2xl font-semibold">{normalizedFilters.length}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{t('rules.filtersCount', { count: normalizedFilters.length })}</div>
                </div>
                <div className="surface-card p-4">
                    <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t('rules.actions')}</div>
                    <div className="mt-2 text-2xl font-semibold">{builderActionCount}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{t('workspace.actionsSelected', { count: builderActionCount, defaultValue: `${builderActionCount} acao(oes)` })}</div>
                </div>
            </div>

            <div className="surface-card mb-4 p-4">
                <form onSubmit={handleCreateRule} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    <input className="border rounded-md p-2 bg-background text-sm" placeholder={t('rules.ruleName')} value={form.name} onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))} required />
                    <select className="border rounded-md p-2 bg-background text-sm" value={form.account_id} onChange={(e) => setForm((prev) => ({ ...prev, account_id: e.target.value }))}>
                        <option value="">{t('rules.allAccounts')}</option>
                        {accounts.map((account) => <option key={account.id} value={account.id}>{account.email || account.display_name}</option>)}
                    </select>
                    <select className="border rounded-md p-2 bg-background text-sm" value={form.target_category_id} onChange={(e) => setForm((prev) => ({ ...prev, target_category_id: e.target.value }))} required>
                        <option value="">{t('rules.targetCategory')}</option>
                        {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
                    </select>
                    <input className="border rounded-md p-2 bg-background text-sm md:col-span-2 lg:col-span-3" placeholder={t('rules.description')} value={form.description} onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))} />

                    <div className="md:col-span-2 lg:col-span-3 rounded-lg border border-border/70 p-3 bg-background">
                        <div className="text-sm font-medium mb-3">{t('rules.actions')}</div>
                        <div className="flex items-center gap-5 overflow-x-auto whitespace-nowrap">
                            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.apply_metadata} onChange={(e) => setForm((prev) => ({ ...prev, apply_metadata: e.target.checked, apply_remove_metadata: e.target.checked ? false : prev.apply_remove_metadata }))} />{t('rules.applyMetadataValues')}</label>
                            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.apply_remove_metadata} onChange={(e) => setForm((prev) => ({ ...prev, apply_remove_metadata: e.target.checked, apply_metadata: e.target.checked ? false : prev.apply_metadata }))} />{t('rules.removeMetadata')}</label>
                            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.apply_rename} onChange={(e) => setForm((prev) => ({ ...prev, apply_rename: e.target.checked }))} />{t('rules.renameItem')}</label>
                            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.apply_move} onChange={(e) => setForm((prev) => ({ ...prev, apply_move: e.target.checked }))} />{t('rules.moveItem')}</label>
                        </div>
                        {(form.apply_rename || form.apply_move) && (
                            <>
                                <div className="mt-3 text-xs text-muted-foreground">{t('rules.placeholdersHelp')}</div>
                                <div className="mt-1 text-xs text-muted-foreground">
                                    {t('rules.templateConditionHelp', { example: '{{#if VOLUME}}...{{else}}...{{/if}}' })}
                                </div>
                            </>
                        )}
                    </div>

                    <div className="md:col-span-2 lg:col-span-3 border rounded-md p-3 bg-background">
                        <div className="flex items-center justify-between mb-3">
                            <div className="text-sm font-medium">{t('rules.filters')}</div>
                            <button type="button" onClick={addFilter} className="inline-flex items-center gap-1 text-xs rounded-md border px-2 py-1 hover:bg-accent"><Plus className="w-3 h-3" />{t('rules.addFilter')}</button>
                        </div>
                        {(form.metadata_filters || []).length === 0 ? (
                            <p className="text-xs text-muted-foreground">{t('rules.noFilters')}</p>
                        ) : (
                            <div className="space-y-2">
                                {(form.metadata_filters || []).map((filter, index) => {
                                    const context = resolveFilterContext(filter);
                                    const hideValue = filter.operator === 'is_empty' || filter.operator === 'is_not_empty';
                                    return (
                                        <div key={`${filter.source}-${index}`} className="grid grid-cols-1 lg:grid-cols-[1fr_180px_1fr_44px] gap-2 items-center">
                                            <select className="border rounded-md p-2 bg-background text-sm" value={filter.source === 'path' ? 'path' : filter.attribute_id || ''} onChange={(e) => {
                                                const next = e.target.value;
                                                if (next === 'path') return updateFilter(index, { source: 'path', attribute_id: null, operator: 'contains', value: '' });
                                                updateFilter(index, { source: 'metadata', attribute_id: next, operator: 'equals', value: '' });
                                            }}>
                                                {availableFilterFields.map((field) => <option key={`${field.source}-${field.id}`} value={field.source === 'path' ? 'path' : field.id}>{field.source === 'path' ? field.label : `${t('rules.metadataField')}: ${field.label}`}</option>)}
                                            </select>
                                            <select className="border rounded-md p-2 bg-background text-sm" value={filter.operator || 'equals'} onChange={(e) => updateFilter(index, { operator: e.target.value })}>
                                                {context.operators.map((operator) => <option key={operator.value} value={operator.value}>{t(`rules.operator.${operator.label}`)}</option>)}
                                            </select>
                                            {hideValue ? <div className="text-xs text-muted-foreground px-2">{t('rules.noValueNeeded')}</div> : context.dataType === 'boolean' ? (
                                                <select className="border rounded-md p-2 bg-background text-sm" value={String(filter.value ?? '')} onChange={(e) => updateFilter(index, { value: e.target.value === 'true' })}>
                                                    <option value="true">{t('common.yes')}</option>
                                                    <option value="false">{t('common.no')}</option>
                                                </select>
                                            ) : context.attribute?.data_type === 'select' ? (
                                                <select className="border rounded-md p-2 bg-background text-sm" value={String(filter.value ?? '')} onChange={(e) => updateFilter(index, { value: e.target.value })}>
                                                    <option value="">{t('rules.selectValue')}</option>
                                                    {getSelectOptions(context.attribute.options).map((option) => <option key={option} value={option}>{option}</option>)}
                                                </select>
                                            ) : (
                                                <input type={context.dataType === 'number' ? 'number' : context.dataType === 'date' ? 'date' : 'text'} className="border rounded-md p-2 bg-background text-sm" value={Array.isArray(filter.value) ? tagsToInputValue(filter.value) : (filter.value ?? '')} onChange={(e) => {
                                                    if (context.dataType === 'number') return updateFilter(index, { value: e.target.value === '' ? '' : Number(e.target.value) });
                                                    if (context.dataType === 'tags') return updateFilter(index, { value: parseTagsInput(e.target.value) });
                                                    updateFilter(index, { value: e.target.value });
                                                }} placeholder={t('rules.filterValue')} />
                                            )}
                                            <button type="button" onClick={() => removeFilter(index)} className="p-2 rounded-md hover:bg-destructive/10 text-destructive" title={t('rules.removeFilter')}><Trash2 className="w-4 h-4" /></button>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    {form.apply_rename && (
                        <div className="md:col-span-2 lg:col-span-3 relative">
                            <input className="border rounded-md p-2 bg-background text-sm w-full" placeholder={t('rules.renameTemplate')} value={form.rename_template} onChange={(e) => setTemplateValue('rename_template', e.target.value)} onFocus={() => setTemplateSuggestField('rename_template')} required={form.apply_rename} />
                            {templateSuggestField === 'rename_template' && templateSuggestions.length > 0 && (
                                <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-sm max-h-48 overflow-auto">
                                    {templateSuggestions.map((token) => <button key={`rename-${token}`} type="button" className="w-full text-left px-3 py-2 text-xs hover:bg-accent" onClick={() => insertTemplateToken('rename_template', token)}>{templateSuggestionState?.mode === 'if' ? `{{#if ${token}}}` : `{{${token}}}`}</button>)}
                                </div>
                            )}
                        </div>
                    )}

                    {form.apply_move && (
                        <>
                            <select className="border rounded-md p-2 bg-background text-sm" value={form.destination_account_id} onChange={(e) => handleDestinationAccountChange(e.target.value)}>
                                <option value="">{t('rules.destinationAccount')}</option>
                                {accounts.map((account) => <option key={account.id} value={account.id}>{account.email || account.display_name}</option>)}
                            </select>
                            <button
                                type="button"
                                onClick={() => setFolderPickerOpen((prev) => !prev)}
                                className="border rounded-md p-2 bg-background text-sm flex items-center justify-between w-full hover:bg-accent"
                            >
                                <span>{t('rules.destinationFolderSelected')}: <span className="ml-1 font-medium">{getSelectedFolderLabel()}</span></span>
                                <ChevronRight className={`w-4 h-4 transition-transform ${folderPickerOpen ? 'rotate-90' : ''}`} />
                            </button>
                            <div className="relative">
                                <input className="border rounded-md p-2 bg-background text-sm w-full" placeholder={t('rules.destinationPath')} value={form.destination_path_template} onChange={(e) => setTemplateValue('destination_path_template', e.target.value)} onFocus={() => setTemplateSuggestField('destination_path_template')} />
                                {templateSuggestField === 'destination_path_template' && templateSuggestions.length > 0 && (
                                    <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-sm max-h-48 overflow-auto">
                                        {templateSuggestions.map((token) => <button key={`path-${token}`} type="button" className="w-full text-left px-3 py-2 text-xs hover:bg-accent" onClick={() => insertTemplateToken('destination_path_template', token)}>{templateSuggestionState?.mode === 'if' ? `{{#if ${token}}}` : `{{${token}}}`}</button>)}
                                    </div>
                                )}
                                <p className="mt-1 text-[11px] text-muted-foreground">{t('rules.destinationPathHelp')}</p>
                            </div>

                            {folderPickerOpen && (
                            <div className="md:col-span-2 lg:col-span-3 border rounded-md overflow-hidden">
                                <div className="flex items-center justify-between border-b px-3 py-2 bg-muted/45">
                                    <div className="text-xs font-medium uppercase text-muted-foreground">{t('rules.destinationFolder')}</div>
                                    <button type="button" onClick={navigateDestinationUp} disabled={destinationPath.length === 0} className="text-xs text-primary hover:underline disabled:opacity-50">{t('moveModal.goUp')}</button>
                                </div>
                                <div className="flex items-center gap-1 overflow-x-auto border-b px-3 py-2 text-xs text-muted-foreground">
                                    <span className="cursor-pointer hover:text-foreground" onClick={() => { setDestinationPath([]); setForm((prev) => ({ ...prev, destination_folder_id: 'root' })); }}>{t('moveModal.root')}</span>
                                    {destinationPath.map((part) => <Fragment key={part.id}><ChevronRight className="w-3 h-3" /><span className="whitespace-nowrap">{part.name}</span></Fragment>)}
                                </div>
                                <div className="flex items-center gap-2 border-b px-3 py-2 bg-background">
                                    <input
                                        type="text"
                                        className="flex-1 border rounded-md p-2 text-sm bg-background"
                                        placeholder={t('rules.newFolderPlaceholder')}
                                        value={newFolderName}
                                        onChange={(e) => setNewFolderName(e.target.value)}
                                    />
                                    <button
                                        type="button"
                                        onClick={handleCreateDestinationFolder}
                                        disabled={creatingFolder}
                                        className="inline-flex items-center gap-1 rounded-md border px-2 py-2 text-xs hover:bg-accent disabled:opacity-50"
                                    >
                                        {creatingFolder ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
                                        {t('rules.createFolder')}
                                    </button>
                                </div>
                                <div className="h-40 overflow-y-auto p-2 bg-background">
                                    {destinationFolderLoading ? <div className="flex justify-center py-4"><Loader2 className="w-4 h-4 animate-spin" /></div> : destinationFolders.length === 0 ? <div className="py-6 text-center text-xs text-muted-foreground">{t('moveModal.emptyFolder')}</div> : destinationFolders.map((folder) => (
                                        <button key={folder.id} type="button" onClick={() => navigateDestinationFolder(folder)} className="w-full flex items-center gap-2 rounded-md p-2 text-left hover:bg-accent">
                                            <Folder className="w-4 h-4 text-primary/80" />
                                            <span className="truncate text-sm">{folder.name}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                            )}
                        </>
                    )}

                    {selectedCategory && form.apply_metadata && (
                        <div className="md:col-span-2 lg:col-span-3 border rounded-md p-3 bg-background">
                            <div className="text-sm font-medium mb-3">{t('rules.metadataValues')}</div>
                            {selectedCategory.attributes.length === 0 ? <p className="text-sm text-muted-foreground">{t('rules.noAttributes')}</p> : (
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                    {selectedCategory.attributes.map((attribute) => (
                                        <div key={attribute.id}>
                                            <label className="block text-xs font-medium mb-1 uppercase text-muted-foreground">{attribute.name}</label>
                                            {renderAttributeInput(attribute)}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={form.include_folders} onChange={(e) => setForm((prev) => ({ ...prev, include_folders: e.target.checked }))} />
                        {t('rules.includeFolders')}
                    </label>
                    <div className="md:col-span-1 lg:col-span-2 flex items-center justify-end gap-2">
                        <button type="button" onClick={handlePreview} disabled={previewing || !form.target_category_id} className="btn-refresh disabled:opacity-50">{previewing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}{t('rules.preview')}</button>
                        <button type="submit" disabled={saving || !form.target_category_id} className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-lg shadow-primary/20 transition-transform hover:-translate-y-[1px] hover:bg-primary/92 disabled:opacity-50"><Plus className="w-4 h-4" />{t('rules.createRule')}</button>
                    </div>
                </form>
                {preview && (
                    <div ref={previewRef} className="mt-3 rounded-2xl border border-border/70 bg-background p-4 text-sm">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                                <div className="font-medium">{previewLabel || t('rules.preview')}</div>
                                <div className="mt-1 text-muted-foreground">{t('rules.previewLine', { matches: preview.total_matches, change: preview.to_change, compliant: preview.already_compliant })}</div>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                <span className="workspace-context-chip workspace-context-chip-accent">{t('rules.previewMatches', { count: preview.total_matches, defaultValue: `${preview.total_matches} impactos` })}</span>
                                <span className="workspace-context-chip">{t('rules.previewChanges', { count: preview.to_change, defaultValue: `${preview.to_change} alteracoes` })}</span>
                            </div>
                        </div>
                        {preview.sample_item_ids.length > 0 && (
                            <div className="mt-3 space-y-2">
                                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                                    {t('rules.sampleImpacts', { defaultValue: 'Amostra de impactos' })}
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {preview.sample_item_ids.slice(0, 6).map((itemId) => (
                                        <span key={itemId} className="workspace-context-chip">{itemId}</span>
                                    ))}
                                </div>
                            </div>
                        )}
                        <div className="mt-4 flex flex-wrap gap-2">
                            <button type="button" onClick={() => navigate('/all-files')} className="workspace-action-button">
                                {t('rules.openLibrary', { defaultValue: 'Abrir biblioteca' })}
                            </button>
                            <button type="button" onClick={() => navigate('/metadata')} className="workspace-action-button">
                                {t('rules.openMetadata', { defaultValue: 'Abrir metadata' })}
                            </button>
                            <button
                                type="button"
                                onClick={() => navigate('/ai', {
                                    state: {
                                        assistantContext: {
                                            title: previewLabel || t('rules.preview'),
                                            description: t('rules.previewLine', { matches: preview.total_matches, change: preview.to_change, compliant: preview.already_compliant }),
                                            entityType: 'automation',
                                            entityId: form.target_category_id || 'rules-preview',
                                            selectedIds: preview.sample_item_ids,
                                            activeFilters: [t('rules.filtersCount', { count: normalizedFilters.length })],
                                            suggestedPrompts: [t('workspace.aiPrompts.ruleReview', { defaultValue: 'Revise esta automacao e aponte riscos ou melhorias.' })],
                                        },
                                    },
                                })}
                                className="workspace-action-button workspace-action-button-primary"
                            >
                                {t('rules.askAiAboutPreview', { defaultValue: 'Perguntar para a IA' })}
                            </button>
                        </div>
                    </div>
                )}
            </div>

            <div className="flex-1 overflow-auto">
                {loading ? <div className="flex justify-center p-8"><Loader2 className="animate-spin" /></div> : rules.length === 0 ? (
                    <div className="empty-state">
                        <div className="empty-state-title">{t('rules.noRules')}</div>
                        <p className="empty-state-text">{t('rules.noRulesHelp')}</p>
                    </div>
                ) : (
                    <div className="surface-card overflow-hidden">
                        <div className="grid grid-cols-[1fr_150px_320px_200px_160px] gap-3 p-3 border-b border-border/70 bg-muted/45 text-xs font-medium uppercase text-muted-foreground">
                            <div>{t('rules.rule')}</div><div>{t('rules.category')}</div><div>{t('rules.actions')}</div><div>{t('rules.scope')}</div><div className="text-right">{t('rules.actions')}</div>
                        </div>
                        <div className="divide-y">
                            {rules.map((rule) => (
                                <div key={rule.id} className="grid grid-cols-[1fr_150px_320px_200px_160px] gap-3 p-3 items-center text-sm">
                                    <div><div className="font-medium">{rule.name}</div><div className="text-xs text-muted-foreground">{rule.description || '-'}</div></div>
                                    <div className="text-xs text-muted-foreground truncate">{categories.find((category) => category.id === rule.target_category_id)?.name || rule.target_category_id}</div>
                                    <div className="text-xs text-muted-foreground space-y-0.5">{getRuleActions(rule).length === 0 ? <div>-</div> : getRuleActions(rule).map((action) => <div key={`${rule.id}-${action}`} className="capitalize">{action}</div>)}</div>
                                    <div className="text-xs text-muted-foreground truncate">{getRuleScope(rule)}</div>
                                    <div className="flex justify-end gap-1">
                                        <button onClick={() => handlePreviewRule(rule)} className="p-2 rounded-md hover:bg-accent" title={t('rules.preview')}>
                                            <Eye className="w-4 h-4" />
                                        </button>
                                        <button onClick={() => handleApplyRule(rule.id)} className="p-2 rounded-md hover:bg-accent" title={t('rules.applyRule')}><PlayCircle className="w-4 h-4" /></button>
                                        <button onClick={() => handleDeleteRule(rule.id)} className="p-2 rounded-md hover:bg-destructive/10 text-destructive" title={t('rules.deleteRule')}><Trash2 className="w-4 h-4" /></button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
