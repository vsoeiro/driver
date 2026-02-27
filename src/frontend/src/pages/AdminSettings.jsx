import { useEffect, useMemo, useState } from 'react';
import { Loader2, RefreshCw, Save, Search } from 'lucide-react';
import { settingsService } from '../services/settings';
import { useToast } from '../contexts/ToastContext';
import FolderTargetPickerModal from '../components/FolderTargetPickerModal';
import { accountsService } from '../services/accounts';
import { jobsService } from '../services/jobs';
import AdminTabs from '../components/AdminTabs';

function PluginField({ field, onChange, onOpenFolderPicker, accountLabelById }) {
    const inputClass = 'input-shell w-full p-2 text-sm';
    const renderers = {
        number: () => (
            <input
                type="number"
                className={inputClass}
                value={field.value ?? ''}
                min={field.minimum ?? undefined}
                max={field.maximum ?? undefined}
                onChange={(e) => onChange(field.key, Number(e.target.value))}
            />
        ),
        text: () => (
            <input
                type="text"
                className={inputClass}
                value={field.value ?? ''}
                placeholder={field.placeholder || ''}
                onChange={(e) => onChange(field.key, e.target.value)}
            />
        ),
        folder_target: () => {
            const target = field.value || {};
            const accountLabel = target.account_id ? (accountLabelById[target.account_id] || target.account_id) : 'Not selected';
            const folderLabel = target.folder_path || 'Root';
            return (
                <div className="space-y-2">
                    <div className="text-xs text-muted-foreground border rounded-md p-2 bg-muted/20">
                        <div><span className="font-medium text-foreground">Account:</span> {accountLabel}</div>
                        <div><span className="font-medium text-foreground">Folder:</span> {folderLabel}</div>
                    </div>
                    <button
                        type="button"
                        onClick={() => onOpenFolderPicker(field)}
                        className="px-3 py-1.5 rounded-md border text-sm hover:bg-accent"
                    >
                        Select Account and Folder
                    </button>
                </div>
            );
        },
    };

    const renderer = renderers[field.input_type];
    if (renderer) return renderer();
    return (
        <div className="space-y-2">
            <input
                type="text"
                className={inputClass}
                value={typeof field.value === 'string' ? field.value : JSON.stringify(field.value ?? '')}
                onChange={(e) => onChange(field.key, e.target.value)}
            />
            <p className="text-xs text-amber-600">
                Unsupported input type `{field.input_type}`. Rendering as plain text fallback.
            </p>
        </div>
    );
}

export default function AdminSettings() {
    const { showToast } = useToast();
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [pluginActionLoading, setPluginActionLoading] = useState({});
    const [groupFilter, setGroupFilter] = useState('');
    const [activeGroupId, setActiveGroupId] = useState('scheduler');
    const [accounts, setAccounts] = useState([]);
    const [folderPicker, setFolderPicker] = useState({
        isOpen: false,
        pluginKey: '',
        fieldKey: '',
        value: null,
    });
    const [form, setForm] = useState({
        enable_daily_sync_scheduler: true,
        daily_sync_cron: '0 0 * * *',
        worker_job_timeout_seconds: 1800,
        ai_model_default: '',
        ai_provider_mode: 'local',
        ai_base_url_remote: '',
        ai_api_key_remote: '',
        plugin_settings: [],
    });

    useEffect(() => {
        const load = async () => {
            setLoading(true);
            try {
                const [data, accountRows] = await Promise.all([
                    settingsService.getRuntimeSettings(),
                    accountsService.getAccounts(),
                ]);
                setAccounts(accountRows);
                setForm({
                    enable_daily_sync_scheduler: data.enable_daily_sync_scheduler,
                    daily_sync_cron: data.daily_sync_cron,
                    worker_job_timeout_seconds: data.worker_job_timeout_seconds ?? 1800,
                    ai_model_default: data.ai_model_default || '',
                    ai_provider_mode: data.ai_provider_mode || 'local',
                    ai_base_url_remote: data.ai_base_url_remote || '',
                    ai_api_key_remote: data.ai_api_key_remote || '',
                    plugin_settings: data.plugin_settings || [],
                });
            } catch (error) {
                console.error(error);
                showToast('Failed to load admin settings', 'error');
            } finally {
                setLoading(false);
            }
        };
        load();
    }, [showToast]);

    const accountLabelById = useMemo(
        () => Object.fromEntries(accounts.map((acc) => [acc.id, `${acc.display_name} (${acc.email})`])),
        [accounts]
    );

    const groups = useMemo(() => {
        const baseGroups = [
            {
                id: 'scheduler',
                title: 'Daily Scheduler',
                description: 'Configure recurring synchronization jobs.',
                type: 'scheduler',
            },
            {
                id: 'workers',
                title: 'Workers',
                description: 'Background worker execution limits and timeouts.',
                type: 'workers',
            },
            {
                id: 'ai',
                title: 'AI',
                description: 'AI assistant runtime model selection.',
                type: 'ai',
            },
            ...form.plugin_settings.map((group) => ({
                id: `plugin:${group.plugin_key}`,
                title: group.plugin_name,
                description: group.plugin_description || 'Metadata library runtime settings.',
                type: 'plugin',
                pluginKey: group.plugin_key,
            })),
        ];

        const normalizedFilter = groupFilter.trim().toLowerCase();
        if (!normalizedFilter) return baseGroups;
        return baseGroups.filter((group) => {
            const description = (group.description || '').toLowerCase();
            return group.title.toLowerCase().includes(normalizedFilter) || description.includes(normalizedFilter);
        });
    }, [form.plugin_settings, groupFilter]);

    useEffect(() => {
        if (!groups.some((group) => group.id === activeGroupId)) {
            setActiveGroupId(groups[0]?.id || 'scheduler');
        }
    }, [groups, activeGroupId]);

    const selectedGroup = groups.find((group) => group.id === activeGroupId);

    const updatePluginField = (pluginKey, fieldKey, value) => {
        setForm((prev) => ({
            ...prev,
            plugin_settings: prev.plugin_settings.map((group) => {
                if (group.plugin_key !== pluginKey) return group;
                return {
                    ...group,
                    fields: group.fields.map((field) => (
                        field.key === fieldKey ? { ...field, value } : field
                    )),
                };
            }),
        }));
    };

    const openFolderPicker = (pluginKey, field) => {
        setFolderPicker({
            isOpen: true,
            pluginKey,
            fieldKey: field.key,
            value: field.value || null,
        });
    };

    const handleSave = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            const pluginPayload = {};
            for (const group of form.plugin_settings) {
                pluginPayload[group.plugin_key] = {};
                for (const field of group.fields) {
                    pluginPayload[group.plugin_key][field.key] = field.value;
                }
            }
            const data = await settingsService.updateRuntimeSettings({
                enable_daily_sync_scheduler: form.enable_daily_sync_scheduler,
                daily_sync_cron: form.daily_sync_cron,
                worker_job_timeout_seconds: form.worker_job_timeout_seconds,
                ai_model_default: form.ai_model_default,
                ai_provider_mode: form.ai_provider_mode,
                ai_base_url_remote: form.ai_base_url_remote,
                ai_api_key_remote: form.ai_api_key_remote,
                plugin_settings: pluginPayload,
            });
            setForm({
                enable_daily_sync_scheduler: data.enable_daily_sync_scheduler,
                daily_sync_cron: data.daily_sync_cron,
                worker_job_timeout_seconds: data.worker_job_timeout_seconds ?? 1800,
                ai_model_default: data.ai_model_default || '',
                ai_provider_mode: data.ai_provider_mode || 'local',
                ai_base_url_remote: data.ai_base_url_remote || '',
                ai_api_key_remote: data.ai_api_key_remote || '',
                plugin_settings: data.plugin_settings || [],
            });
            showToast('Settings saved successfully', 'success');
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to save settings';
            showToast(message, 'error');
        } finally {
            setSaving(false);
        }
    };

    const handlePluginAction = async (group, action) => {
        if (action !== 'reindex_covers') return;
        setPluginActionLoading((prev) => ({ ...prev, [`${group.plugin_key}:${action}`]: true }));
        try {
            const job = await jobsService.createReindexComicCoversJob(group.plugin_key);
            showToast(`Cover re-index job started (${job.id}).`, 'success');
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to start cover re-index job';
            showToast(message, 'error');
        } finally {
            setPluginActionLoading((prev) => ({ ...prev, [`${group.plugin_key}:${action}`]: false }));
        }
    };

    const renderGroupContent = () => {
        if (!selectedGroup) {
            return <p className="text-sm text-muted-foreground">No settings group found.</p>;
        }

        if (selectedGroup.type === 'scheduler') {
            return (
                <div className="space-y-4">
                    <div className="flex items-center justify-between gap-4">
                        <div>
                            <h2 className="font-medium">Daily Sync Scheduler</h2>
                            <p className="text-sm text-muted-foreground">Toggle automatic sync jobs based on cron schedule.</p>
                        </div>
                        <label className="inline-flex items-center gap-2 text-sm">
                            <input
                                type="checkbox"
                                checked={form.enable_daily_sync_scheduler}
                                onChange={(e) =>
                                    setForm((prev) => ({
                                        ...prev,
                                        enable_daily_sync_scheduler: e.target.checked,
                                    }))
                                }
                            />
                            Enabled
                        </label>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">Cron Expression</label>
                        <input
                            type="text"
                            className="w-full border rounded-md p-2 bg-background text-sm"
                            value={form.daily_sync_cron}
                            onChange={(e) =>
                                setForm((prev) => ({
                                    ...prev,
                                    daily_sync_cron: e.target.value,
                                }))
                            }
                            placeholder="0 0 * * *"
                        />
                    </div>

                </div>
            );
        }

        if (selectedGroup.type === 'workers') {
            return (
                <div className="space-y-4">
                    <div>
                        <h2 className="font-medium">Worker Runtime</h2>
                        <p className="text-sm text-muted-foreground">
                            Configure execution timeout for a single background job.
                        </p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">Worker Job Timeout (seconds)</label>
                        <input
                            type="number"
                            min="1"
                            className="w-full border rounded-md p-2 bg-background text-sm"
                            value={form.worker_job_timeout_seconds}
                            onChange={(e) =>
                                setForm((prev) => ({
                                    ...prev,
                                    worker_job_timeout_seconds: Number(e.target.value),
                                }))
                            }
                        />
                        <p className="text-xs text-muted-foreground mt-1">
                            This value is read by worker processes. Restart workers after saving.
                        </p>
                    </div>
                </div>
            );
        }

        if (selectedGroup.type === 'ai') {
            return (
                <div className="space-y-4">
                    <div>
                        <h2 className="font-medium">AI Runtime</h2>
                        <p className="text-sm text-muted-foreground">
                            Configure model, provider mode and OpenAI-compatible endpoint credentials for AI assistant.
                        </p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">AI Provider Mode</label>
                        <select
                            className="w-full border rounded-md p-2 bg-background text-sm"
                            value={form.ai_provider_mode}
                            onChange={(e) =>
                                setForm((prev) => ({
                                    ...prev,
                                    ai_provider_mode: e.target.value,
                                }))
                            }
                        >
                            <option value="local">Local only (Ollama)</option>
                            <option value="openai_compatible">OpenAI compatible</option>
                            <option value="gemini">Gemini (Google API)</option>
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">Default AI Model</label>
                        <input
                            type="text"
                            className="w-full border rounded-md p-2 bg-background text-sm"
                            value={form.ai_model_default}
                            onChange={(e) =>
                                setForm((prev) => ({
                                    ...prev,
                                    ai_model_default: e.target.value,
                                }))
                            }
                            placeholder="e.g. llama3.1:8b"
                        />
                        <p className="text-xs text-muted-foreground mt-1">
                            Examples: <code>llama3.1:8b</code> (Ollama), <code>gemini-2.0-flash</code> (Gemini, sem <code>models/</code>).
                        </p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">OpenAI-compatible Base URL</label>
                        <input
                            type="text"
                            className="w-full border rounded-md p-2 bg-background text-sm"
                            value={form.ai_base_url_remote}
                            onChange={(e) =>
                                setForm((prev) => ({
                                    ...prev,
                                    ai_base_url_remote: e.target.value,
                                }))
                            }
                            placeholder="e.g. https://api.openai.com/v1"
                        />
                        <p className="text-xs text-muted-foreground mt-1">
                            For Gemini mode, use <code>https://generativelanguage.googleapis.com/v1beta/openai</code>.
                        </p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">OpenAI-compatible API Key</label>
                        <input
                            type="password"
                            autoComplete="new-password"
                            className="w-full border rounded-md p-2 bg-background text-sm"
                            value={form.ai_api_key_remote}
                            onChange={(e) =>
                                setForm((prev) => ({
                                    ...prev,
                                    ai_api_key_remote: e.target.value,
                                }))
                            }
                            placeholder="e.g. sk-..."
                        />
                    </div>
                </div>
            );
        }

        const pluginKey = selectedGroup.pluginKey;
        const group = form.plugin_settings.find((item) => item.plugin_key === pluginKey);
        if (!group) {
            return <p className="text-sm text-muted-foreground">Metadata library group not found.</p>;
        }

        return (
            <div className="space-y-4">
                <div>
                    <h2 className="font-medium">{group.plugin_name}</h2>
                    <p className="text-sm text-muted-foreground">{group.plugin_description || 'Metadata-library-specific runtime settings.'}</p>
                    {group.capabilities?.supported_input_types?.length > 0 && (
                        <p className="text-xs text-muted-foreground mt-1">
                            Supported field types: {group.capabilities.supported_input_types.join(', ')}
                        </p>
                    )}
                </div>

                {(group.capabilities?.actions || []).length > 0 && (
                    <div className="flex items-center gap-2">
                        {(group.capabilities.actions || []).map((action) => (
                            <button
                                key={`${group.plugin_key}:${action}`}
                                type="button"
                                onClick={() => handlePluginAction(group, action)}
                                disabled={!!pluginActionLoading[`${group.plugin_key}:${action}`]}
                                className="px-3 py-1.5 rounded-md border text-sm hover:bg-accent disabled:opacity-50 inline-flex items-center gap-2"
                            >
                                {pluginActionLoading[`${group.plugin_key}:${action}`]
                                    ? <Loader2 className="w-4 h-4 animate-spin" />
                                    : <RefreshCw className="w-4 h-4" />}
                                {action === 'reindex_covers' ? 'Re-index Covers' : action}
                            </button>
                        ))}
                    </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {group.fields.map((field) => (
                        <div
                            key={`${group.plugin_key}:${field.key}`}
                            className={field.input_type === 'folder_target' ? 'md:col-span-2 space-y-1' : 'space-y-1'}
                        >
                            <label className="block text-sm font-medium">{field.label}</label>
                            <PluginField
                                field={field}
                                accountLabelById={accountLabelById}
                                onChange={(fieldKey, value) => updatePluginField(group.plugin_key, fieldKey, value)}
                                onOpenFolderPicker={(f) => openFolderPicker(group.plugin_key, f)}
                            />
                            {field.description && (
                                <p className="text-xs text-muted-foreground">{field.description}</p>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        );
    };

    return (
        <div className="app-page">
            <div className="page-header flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h1 className="page-title">Admin Settings</h1>
                    <p className="page-subtitle">Grouped runtime configuration panel.</p>
                </div>
                <AdminTabs />
            </div>

            {loading ? (
                <div className="flex justify-center p-12">
                    <Loader2 className="animate-spin text-primary" size={30} />
                </div>
            ) : (
                <form onSubmit={handleSave} className="flex-1 min-h-0 flex gap-4">
                    <aside className="surface-card w-72 p-3 space-y-3 overflow-auto">
                        <div className="relative">
                            <Search className="w-4 h-4 absolute left-2 top-2.5 text-muted-foreground" />
                            <input
                                type="text"
                                value={groupFilter}
                                onChange={(e) => setGroupFilter(e.target.value)}
                                placeholder="Search settings"
                                className="input-shell w-full pl-8 pr-2 py-2 text-sm"
                            />
                        </div>

                        <div className="space-y-1">
                            {groups.map((group) => (
                                <button
                                    key={group.id}
                                    type="button"
                                    onClick={() => setActiveGroupId(group.id)}
                                    className={`w-full text-left rounded-lg px-3 py-2 border transition-colors ${
                                        activeGroupId === group.id
                                            ? 'bg-primary text-primary-foreground border-primary shadow-sm'
                                            : 'bg-card/80 hover:bg-accent/65 text-foreground border-border/70'
                                    }`}
                                >
                                    <div className="text-sm font-medium truncate">{group.title}</div>
                                    <div className={`text-xs truncate ${activeGroupId === group.id ? 'text-primary-foreground/80' : 'text-muted-foreground'}`}>
                                        {group.description}
                                    </div>
                                </button>
                            ))}
                        </div>
                    </aside>

                    <section className="surface-card flex-1 min-h-0 overflow-auto p-5 space-y-5">
                        <div className="flex items-center justify-between gap-3 border-b border-border/70 pb-4">
                            <div>
                                <h2 className="text-base font-semibold">{selectedGroup?.title || 'Settings group'}</h2>
                                <p className="text-sm text-muted-foreground">{selectedGroup?.description || 'Select a group on the left.'}</p>
                            </div>
                            <button
                                type="submit"
                                disabled={saving}
                                className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-lg shadow-primary/20 transition-transform hover:-translate-y-[1px] hover:bg-primary/92 disabled:opacity-50"
                            >
                                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                                Save
                            </button>
                        </div>

                        {renderGroupContent()}
                    </section>
                </form>
            )}

            <FolderTargetPickerModal
                isOpen={folderPicker.isOpen}
                initialValue={folderPicker.value}
                onClose={() => setFolderPicker({ isOpen: false, pluginKey: '', fieldKey: '', value: null })}
                onConfirm={(value) => {
                    updatePluginField(folderPicker.pluginKey, folderPicker.fieldKey, value);
                    setFolderPicker({ isOpen: false, pluginKey: '', fieldKey: '', value: null });
                }}
            />
        </div>
    );
}
