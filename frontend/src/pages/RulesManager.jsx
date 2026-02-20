import { useEffect, useMemo, useState, useCallback } from 'react';
import { PlayCircle, Trash2, Plus, Eye, Loader2 } from 'lucide-react';
import { metadataService } from '../services/metadata';
import { accountsService } from '../services/accounts';
import { jobsService } from '../services/jobs';
import { useToast } from '../contexts/ToastContext';
import { getSelectOptions, parseTagsInput, tagsToInputValue } from '../utils/metadata';

const DEFAULT_FORM = {
    name: '',
    description: '',
    account_id: '',
    path_prefix: '',
    path_contains: '',
    include_folders: false,
    target_category_id: '',
    apply_metadata: true,
    apply_rename: false,
    rename_template: '',
    apply_move: false,
    destination_account_id: '',
    destination_folder_id: 'root',
    destination_path_template: '',
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

    const loadData = useCallback(async () => {
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
    }, [showToast]);

    useEffect(() => {
        loadData();
    }, [loadData]);

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
                apply_metadata: form.apply_metadata,
                apply_rename: form.apply_rename,
                rename_template: form.rename_template || null,
                apply_move: form.apply_move,
                destination_account_id: form.destination_account_id || null,
                destination_folder_id: form.destination_folder_id || 'root',
                destination_path_template: form.destination_path_template || null,
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
                apply_metadata: form.apply_metadata,
                apply_rename: form.apply_rename,
                rename_template: form.rename_template || null,
                apply_move: form.apply_move,
                destination_account_id: form.destination_account_id || null,
                destination_folder_id: form.destination_folder_id || 'root',
                destination_path_template: form.destination_path_template || null,
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
                    {getSelectOptions(attribute.options).map((option) => (
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

        if (attribute.data_type === 'tags') {
            return (
                <input
                    type="text"
                    className="w-full border rounded-md p-2 text-sm bg-background"
                    value={tagsToInputValue(value)}
                    onChange={(e) => setAttributeValue(attribute, parseTagsInput(e.target.value))}
                    placeholder={`Set ${attribute.name} tags (comma separated)`}
                />
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

                    <div className="md:col-span-2 lg:col-span-3 border rounded-md p-3 bg-background">
                        <div className="text-sm font-medium mb-3">Actions</div>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                            <label className="flex items-center gap-2 text-sm">
                                <input
                                    type="checkbox"
                                    checked={form.apply_metadata}
                                    onChange={(e) => setForm((prev) => ({ ...prev, apply_metadata: e.target.checked }))}
                                />
                                Apply Metadata Values
                            </label>
                            <label className="flex items-center gap-2 text-sm">
                                <input
                                    type="checkbox"
                                    checked={form.apply_rename}
                                    onChange={(e) => setForm((prev) => ({ ...prev, apply_rename: e.target.checked }))}
                                />
                                Rename Item
                            </label>
                            <label className="flex items-center gap-2 text-sm">
                                <input
                                    type="checkbox"
                                    checked={form.apply_move}
                                    onChange={(e) => setForm((prev) => ({ ...prev, apply_move: e.target.checked }))}
                                />
                                Move Item
                            </label>
                        </div>
                        {(form.apply_rename || form.apply_move) && (
                            <div className="mt-3 text-xs text-muted-foreground">
                                Placeholders: use attribute names like <code>[SERIES]</code>, <code>[TITLE]</code> plus <code>[EXTENSAO]</code>, <code>[NOME_ATUAL]</code>.
                            </div>
                        )}
                    </div>

                    {form.apply_rename && (
                        <input
                            className="border rounded-md p-2 bg-background text-sm md:col-span-2 lg:col-span-3"
                            placeholder="Rename template (e.g. [SERIES] - [TITLE].[EXTENSAO])"
                            value={form.rename_template}
                            onChange={(e) => setForm((prev) => ({ ...prev, rename_template: e.target.value }))}
                            required={form.apply_rename}
                        />
                    )}

                    {form.apply_move && (
                        <>
                            <select
                                className="border rounded-md p-2 bg-background text-sm"
                                value={form.destination_account_id}
                                onChange={(e) => setForm((prev) => ({ ...prev, destination_account_id: e.target.value }))}
                            >
                                <option value="">Destination account (same as source)</option>
                                {accounts.map((account) => (
                                    <option key={account.id} value={account.id}>{account.email || account.display_name}</option>
                                ))}
                            </select>
                            <input
                                className="border rounded-md p-2 bg-background text-sm"
                                placeholder="Destination folder id (default: root)"
                                value={form.destination_folder_id}
                                onChange={(e) => setForm((prev) => ({ ...prev, destination_folder_id: e.target.value }))}
                            />
                            <input
                                className="border rounded-md p-2 bg-background text-sm"
                                placeholder="Destination path template (e.g. Quadrinhos/[SERIES])"
                                value={form.destination_path_template}
                                onChange={(e) => setForm((prev) => ({ ...prev, destination_path_template: e.target.value }))}
                            />
                        </>
                    )}

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
                        <div className="grid grid-cols-[1fr_150px_240px_200px_160px] gap-3 p-3 border-b bg-muted/50 text-xs font-medium uppercase text-muted-foreground">
                            <div>Rule</div>
                            <div>Category</div>
                            <div>Actions</div>
                            <div>Scope</div>
                            <div className="text-right">Actions</div>
                        </div>
                        <div className="divide-y">
                            {rules.map((rule) => (
                                <div key={rule.id} className="grid grid-cols-[1fr_150px_240px_200px_160px] gap-3 p-3 items-center text-sm">
                                    <div>
                                        <div className="font-medium">{rule.name}</div>
                                        <div className="text-xs text-muted-foreground">{rule.description || '-'}</div>
                                    </div>
                                    <div className="text-xs text-muted-foreground truncate">
                                        {categories.find((category) => category.id === rule.target_category_id)?.name || rule.target_category_id}
                                    </div>
                                    <div className="text-xs text-muted-foreground space-y-0.5">
                                        <div>Metadata: {rule.apply_metadata ? 'on' : 'off'}</div>
                                        <div>Rename: {rule.apply_rename ? (rule.rename_template || '-') : 'off'}</div>
                                        <div>Move: {rule.apply_move ? `${rule.destination_folder_id || 'root'} / ${rule.destination_path_template || '-'}` : 'off'}</div>
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
