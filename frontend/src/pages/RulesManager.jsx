import React, { useEffect, useMemo, useState } from 'react';
import { PlayCircle, Trash2, Plus, Eye, Loader2 } from 'lucide-react';
import { metadataService } from '../services/metadata';
import { accountsService } from '../services/accounts';
import { jobsService } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';

const DEFAULT_FORM = {
    name: '',
    description: '',
    account_id: '',
    path_prefix: '',
    path_contains: '',
    include_folders: false,
    target_category_id: '',
};

export default function RulesManager() {
    const { showToast } = useToast();
    const [rules, setRules] = useState([]);
    const [categories, setCategories] = useState([]);
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [previewing, setPreviewing] = useState(false);
    const [preview, setPreview] = useState(null);
    const [form, setForm] = useState(DEFAULT_FORM);
    const [targetValues, setTargetValues] = useState({});

    const selectedCategory = useMemo(
        () => categories.find((category) => category.id === form.target_category_id),
        [categories, form.target_category_id]
    );

    const normalizedTargetValues = useMemo(() => {
        const values = {};
        Object.entries(targetValues).forEach(([key, value]) => {
            if (value !== '' && value !== null && value !== undefined) {
                values[key] = value;
            }
        });
        return values;
    }, [targetValues]);

    const loadData = async () => {
        setLoading(true);
        try {
            const [rulesData, categoriesData, accountsData] = await Promise.all([
                metadataService.listRules(),
                metadataService.listCategories(),
                accountsService.getAccounts(),
            ]);
            setRules(rulesData);
            setCategories(categoriesData);
            setAccounts(accountsData);
        } catch (error) {
            showToast('Failed to load rules', 'error');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);

    useEffect(() => {
        setTargetValues({});
    }, [form.target_category_id]);

    const handleCreateRule = async (e) => {
        e.preventDefault();
        if (!form.target_category_id) {
            showToast('Choose a target category', 'error');
            return;
        }

        setSaving(true);
        try {
            await metadataService.createRule({
                name: form.name,
                description: form.description || null,
                account_id: form.account_id || null,
                path_prefix: form.path_prefix || null,
                path_contains: form.path_contains || null,
                include_folders: form.include_folders,
                target_category_id: form.target_category_id,
                target_values: normalizedTargetValues,
                is_active: true,
                priority: 100,
            });
            setForm(DEFAULT_FORM);
            setTargetValues({});
            setPreview(null);
            showToast('Rule created', 'success');
            loadData();
        } catch (error) {
            showToast('Failed to create rule', 'error');
        } finally {
            setSaving(false);
        }
    };

    const handlePreview = async () => {
        setPreviewing(true);
        try {
            const data = await metadataService.previewRule({
                account_id: form.account_id || null,
                path_prefix: form.path_prefix || null,
                path_contains: form.path_contains || null,
                include_folders: form.include_folders,
                target_category_id: form.target_category_id,
                target_values: normalizedTargetValues,
                limit: 10,
            });
            setPreview(data);
        } catch (error) {
            showToast('Failed to preview rule', 'error');
        } finally {
            setPreviewing(false);
        }
    };

    const handleApplyRule = async (ruleId) => {
        try {
            await jobsService.createApplyRuleJob(ruleId);
            showToast('Rule apply job created', 'success');
        } catch {
            showToast('Failed to create apply job', 'error');
        }
    };

    const handleDeleteRule = async (ruleId) => {
        try {
            await metadataService.deleteRule(ruleId);
            showToast('Rule deleted', 'success');
            loadData();
        } catch {
            showToast('Failed to delete rule', 'error');
        }
    };

    const setAttributeValue = (attribute, rawValue) => {
        let value = rawValue;
        if (attribute.data_type === 'number') {
            value = rawValue === '' ? '' : Number(rawValue);
        }
        setTargetValues((prev) => ({ ...prev, [attribute.id]: value }));
    };

    const renderAttributeInput = (attribute) => {
        const value = targetValues[attribute.id] ?? '';

        if (attribute.data_type === 'select') {
            return (
                <select
                    className="w-full border rounded-md p-2 text-sm bg-background"
                    value={value}
                    onChange={(e) => setAttributeValue(attribute, e.target.value)}
                >
                    <option value="">Ignore</option>
                    {attribute.options?.options?.map((option) => (
                        <option key={option} value={option}>{option}</option>
                    ))}
                </select>
            );
        }

        if (attribute.data_type === 'boolean') {
            return (
                <select
                    className="w-full border rounded-md p-2 text-sm bg-background"
                    value={value === '' ? '' : String(value)}
                    onChange={(e) => {
                        const next = e.target.value;
                        if (next === '') setAttributeValue(attribute, '');
                        else setAttributeValue(attribute, next === 'true');
                    }}
                >
                    <option value="">Ignore</option>
                    <option value="true">Yes</option>
                    <option value="false">No</option>
                </select>
            );
        }

        return (
            <input
                type={attribute.data_type === 'number' ? 'number' : attribute.data_type === 'date' ? 'date' : 'text'}
                className="w-full border rounded-md p-2 text-sm bg-background"
                value={value}
                onChange={(e) => setAttributeValue(attribute, e.target.value)}
                placeholder={`Set ${attribute.name} (optional)`}
            />
        );
    };

    return (
        <div className="flex flex-col h-screen">
            <div className="p-4 border-b bg-background">
                <h1 className="text-lg font-semibold text-foreground">Automatic Rules</h1>
                <p className="text-sm text-muted-foreground">Preview before apply, then run in background.</p>
            </div>

            <div className="p-4 border-b bg-muted/20">
                <form onSubmit={handleCreateRule} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    <input
                        className="border rounded-md p-2 bg-background text-sm"
                        placeholder="Rule name"
                        value={form.name}
                        onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                        required
                    />
                    <select
                        className="border rounded-md p-2 bg-background text-sm"
                        value={form.account_id}
                        onChange={(e) => setForm((prev) => ({ ...prev, account_id: e.target.value }))}
                    >
                        <option value="">All Accounts</option>
                        {accounts.map((account) => (
                            <option key={account.id} value={account.id}>{account.email || account.display_name}</option>
                        ))}
                    </select>
                    <select
                        className="border rounded-md p-2 bg-background text-sm"
                        value={form.target_category_id}
                        onChange={(e) => setForm((prev) => ({ ...prev, target_category_id: e.target.value }))}
                        required
                    >
                        <option value="">Target category</option>
                        {categories.map((category) => (
                            <option key={category.id} value={category.id}>{category.name}</option>
                        ))}
                    </select>
                    <input
                        className="border rounded-md p-2 bg-background text-sm"
                        placeholder="Path prefix (ex.: /Comics/Marvel)"
                        value={form.path_prefix}
                        onChange={(e) => setForm((prev) => ({ ...prev, path_prefix: e.target.value }))}
                    />
                    <input
                        className="border rounded-md p-2 bg-background text-sm"
                        placeholder="Path contains (ex.: Batman)"
                        value={form.path_contains}
                        onChange={(e) => setForm((prev) => ({ ...prev, path_contains: e.target.value }))}
                    />
                    <input
                        className="border rounded-md p-2 bg-background text-sm"
                        placeholder="Description"
                        value={form.description}
                        onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
                    />

                    {selectedCategory && (
                        <div className="md:col-span-2 lg:col-span-3 border rounded-md p-3 bg-background">
                            <div className="text-sm font-medium mb-3">Metadata Values</div>
                            {selectedCategory.attributes.length === 0 ? (
                                <p className="text-sm text-muted-foreground">Selected category has no attributes.</p>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                    {selectedCategory.attributes.map((attribute) => (
                                        <div key={attribute.id}>
                                            <label className="block text-xs font-medium mb-1 uppercase text-muted-foreground">
                                                {attribute.name}
                                            </label>
                                            {renderAttributeInput(attribute)}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    <label className="flex items-center gap-2 text-sm">
                        <input
                            type="checkbox"
                            checked={form.include_folders}
                            onChange={(e) => setForm((prev) => ({ ...prev, include_folders: e.target.checked }))}
                        />
                        Include folders
                    </label>
                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            onClick={handlePreview}
                            disabled={previewing || !form.target_category_id}
                            className="px-3 py-2 rounded-md border text-sm hover:bg-accent disabled:opacity-50 inline-flex items-center gap-2"
                        >
                            {previewing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}
                            Preview
                        </button>
                        <button
                            type="submit"
                            disabled={saving || !form.target_category_id}
                            className="px-3 py-2 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 disabled:opacity-50 inline-flex items-center gap-2"
                        >
                            <Plus className="w-4 h-4" />
                            Create Rule
                        </button>
                    </div>
                </form>
                {preview && (
                    <div className="mt-3 text-sm border rounded-md p-3 bg-background">
                        <div className="font-medium mb-1">Preview</div>
                        <div className="text-muted-foreground">
                            Matches: {preview.total_matches} | Change: {preview.to_change} | Already compliant: {preview.already_compliant}
                        </div>
                    </div>
                )}
            </div>

            <div className="flex-1 overflow-auto p-4">
                {loading ? (
                    <div className="flex justify-center p-8">
                        <Loader2 className="animate-spin" />
                    </div>
                ) : rules.length === 0 ? (
                    <div className="text-center text-muted-foreground p-8">No rules created yet.</div>
                ) : (
                    <div className="border rounded-lg overflow-hidden bg-card">
                        <div className="grid grid-cols-[1fr_160px_180px_160px] gap-3 p-3 border-b bg-muted/50 text-xs font-medium uppercase text-muted-foreground">
                            <div>Rule</div>
                            <div>Target</div>
                            <div>Scope</div>
                            <div className="text-right">Actions</div>
                        </div>
                        <div className="divide-y">
                            {rules.map((rule) => (
                                <div key={rule.id} className="grid grid-cols-[1fr_160px_180px_160px] gap-3 p-3 items-center text-sm">
                                    <div>
                                        <div className="font-medium">{rule.name}</div>
                                        <div className="text-xs text-muted-foreground">{rule.description || '-'}</div>
                                    </div>
                                    <div className="text-xs text-muted-foreground truncate">
                                        {categories.find((category) => category.id === rule.target_category_id)?.name || rule.target_category_id}
                                    </div>
                                    <div className="text-xs text-muted-foreground truncate">
                                        {rule.path_prefix || '-'} {rule.path_contains ? `| contains: ${rule.path_contains}` : ''}
                                    </div>
                                    <div className="flex justify-end gap-1">
                                        <button
                                            onClick={() => handleApplyRule(rule.id)}
                                            className="p-2 rounded-md hover:bg-accent"
                                            title="Apply Rule"
                                        >
                                            <PlayCircle className="w-4 h-4" />
                                        </button>
                                        <button
                                            onClick={() => handleDeleteRule(rule.id)}
                                            className="p-2 rounded-md hover:bg-destructive/10 text-destructive"
                                            title="Delete Rule"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
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
