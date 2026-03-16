import { useEffect, useMemo, useState } from 'react';
import { Loader2, RefreshCw, Save, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { settingsService } from '../services/settings';
import { useToast } from '../contexts/ToastContext';
import { useWorkspacePage } from '../contexts/WorkspaceContext';
import FolderTargetPickerModal from '../components/FolderTargetPickerModal';
import { accountsService } from '../services/accounts';
import { jobsService } from '../services/jobs';
import AdminTabs from '../components/AdminTabs';
import { SUPPORTED_LANGUAGES } from '../i18n';

function PluginField({ field, onChange, onOpenFolderPicker, accountLabelById, t }) {
    const inputClass = 'input-shell w-full p-2 text-sm';
    const renderers = {
        number: () => (
            <input
                type="number"
                autoComplete="off"
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
                autoComplete="off"
                className={inputClass}
                value={field.value ?? ''}
                placeholder={field.placeholder || ''}
                onChange={(e) => onChange(field.key, e.target.value)}
            />
        ),
        folder_target: () => {
            const target = field.value || {};
            const accountLabel = target.account_id ? (accountLabelById[target.account_id] || target.account_id) : t('adminSettings.pluginField.notSelected');
            const folderLabel = target.folder_path || t('adminSettings.pluginField.root');
            return (
                <div className="space-y-2">
                    <div className="text-xs text-muted-foreground border rounded-md p-2 bg-muted/20">
                        <div><span className="font-medium text-foreground">{t('adminSettings.pluginField.account')}</span> {accountLabel}</div>
                        <div><span className="font-medium text-foreground">{t('adminSettings.pluginField.folder')}</span> {folderLabel}</div>
                    </div>
                    <button
                        type="button"
                        onClick={() => onOpenFolderPicker(field)}
                        className="px-3 py-1.5 rounded-md border text-sm hover:bg-accent"
                    >
                        {t('adminSettings.pluginField.selectAccountFolder')}
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
                autoComplete="off"
                className={inputClass}
                value={typeof field.value === 'string' ? field.value : JSON.stringify(field.value ?? '')}
                onChange={(e) => onChange(field.key, e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
                {t('adminSettings.pluginField.unsupported', { inputType: field.input_type })}
            </p>
        </div>
    );
}

export default function AdminSettings() {
    const { t, i18n } = useTranslation();
    const location = useLocation();
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
                showToast(t('adminSettings.failedLoad'), 'error');
            } finally {
                setLoading(false);
            }
        };
        load();
    }, [showToast, t]);

    const accountLabelById = useMemo(
        () => Object.fromEntries(accounts.map((acc) => [acc.id, `${acc.display_name} (${acc.email})`])),
        [accounts]
    );

    const renderPluginGroup = (group) => (
        <div key={group.plugin_key} className="rounded-lg border border-border/80 bg-background/80 p-4">
            <div>
                <h3 className="font-medium">{group.plugin_name}</h3>
                <p className="text-sm text-muted-foreground">{group.plugin_description || t('adminSettings.metadataSettingsFallback')}</p>
                {group.capabilities?.supported_input_types?.length > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">
                        {t('adminSettings.supportedFieldTypes', { types: group.capabilities.supported_input_types.join(', ') })}
                    </p>
                )}
            </div>

            {(group.capabilities?.actions || []).length > 0 && (
                <div className="mt-4 flex flex-wrap items-center gap-2">
                    {(group.capabilities.actions || []).map((action) => (
                        <button
                            key={`${group.plugin_key}:${action}`}
                            type="button"
                            onClick={() => handlePluginAction(group, action)}
                            disabled={!!pluginActionLoading[`${group.plugin_key}:${action}`]}
                            className="inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50"
                        >
                            {pluginActionLoading[`${group.plugin_key}:${action}`]
                                ? <Loader2 className="h-4 w-4 animate-spin" />
                                : <RefreshCw className="h-4 w-4" />}
                            {action === 'reindex_covers' ? t('adminSettings.reindexCovers') : action}
                        </button>
                    ))}
                </div>
            )}

            <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                {group.fields.map((field) => (
                    <div
                        key={`${group.plugin_key}:${field.key}`}
                        className={field.input_type === 'folder_target' ? 'space-y-1 md:col-span-2' : 'space-y-1'}
                    >
                        <label className="block text-sm font-medium">{field.label}</label>
                        <PluginField
                            field={field}
                            accountLabelById={accountLabelById}
                            t={t}
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

    const groups = useMemo(() => {
        const baseGroups = [
            {
                id: 'scheduler',
                title: t('adminSettings.schedulerTitle'),
                description: t('adminSettings.schedulerDescription'),
                type: 'scheduler',
            },
            {
                id: 'workers',
                title: t('adminSettings.workersTitle'),
                description: t('adminSettings.workersDescription'),
                type: 'workers',
            },
            {
                id: 'ai',
                title: t('adminSettings.aiTitle'),
                description: t('adminSettings.aiDescription'),
                type: 'ai',
            },
            {
                id: 'interface',
                title: t('adminSettings.interfaceTitle'),
                description: t('adminSettings.interfaceDescription'),
                type: 'interface',
            },
        ];
        if (form.plugin_settings.length > 0) {
            baseGroups.push({
                id: 'metadata-libraries',
                title: t('adminSettings.metadataLibrariesTitle'),
                description: t('adminSettings.metadataLibrariesDescription'),
                type: 'metadata_libraries',
                searchText: form.plugin_settings
                    .flatMap((group) => [group.plugin_name, group.plugin_description])
                    .filter(Boolean)
                    .join(' '),
            });
        }

        const normalizedFilter = groupFilter.trim().toLowerCase();
        if (!normalizedFilter) return baseGroups;
        return baseGroups.filter((group) => {
            const haystack = [group.title, group.description, group.searchText]
                .filter(Boolean)
                .join(' ')
                .toLowerCase();
            return haystack.includes(normalizedFilter);
        });
    }, [form.plugin_settings, groupFilter, t]);

    useEffect(() => {
        if (!groups.some((group) => group.id === activeGroupId)) {
            setActiveGroupId(groups[0]?.id || 'scheduler');
        }
    }, [groups, activeGroupId]);

    const selectedGroup = groups.find((group) => group.id === activeGroupId);

    useWorkspacePage(useMemo(() => ({
        title: t('adminSettings.title'),
        subtitle: t('workspace.settingsSubtitle', { defaultValue: 'Configuracoes de runtime com organizacao por dominio.' }),
        entityType: 'admin',
        entityId: activeGroupId,
        sourceRoute: location.pathname,
        activeFilters: [selectedGroup?.title || ''],
        metrics: [
            t('workspace.settingsSectionsMetric', { count: groups.length, defaultValue: `${groups.length} secoes` }),
            form.plugin_settings.length > 0
                ? t('workspace.settingsLibrariesMetric', { count: form.plugin_settings.length, defaultValue: `${form.plugin_settings.length} bibliotecas` })
                : '',
        ].filter(Boolean),
        suggestedPrompts: [
            t('workspace.aiPrompts.recommend', { defaultValue: 'Sugira as proximas acoes com maior impacto.' }),
            t('workspace.aiPrompts.summarize', { defaultValue: 'Resuma o contexto atual e destaque riscos.' }),
        ],
    }), [activeGroupId, form.plugin_settings.length, groups.length, location.pathname, selectedGroup?.title, t]));

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
            showToast(t('adminSettings.saved'), 'success');
        } catch (error) {
            const message = error?.response?.data?.detail || t('adminSettings.failedSave');
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
            showToast(t('adminSettings.reindexStarted', { id: job.id }), 'success');
        } catch (error) {
            const message = error?.response?.data?.detail || t('adminSettings.failedReindex');
            showToast(message, 'error');
        } finally {
            setPluginActionLoading((prev) => ({ ...prev, [`${group.plugin_key}:${action}`]: false }));
        }
    };

    const renderGroupContent = () => {
        if (!selectedGroup) {
            return <p className="text-sm text-muted-foreground">{t('adminSettings.noGroupFound')}</p>;
        }

        if (selectedGroup.type === 'scheduler') {
            return (
                <div className="space-y-4">
                    <div className="flex items-center justify-between gap-4">
                        <div>
                            <h2 className="font-medium">{t('adminSettings.dailySyncScheduler')}</h2>
                            <p className="text-sm text-muted-foreground">{t('adminSettings.dailySyncHelp')}</p>
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
                            {t('adminSettings.enabled')}
                        </label>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">{t('adminSettings.cronExpression')}</label>
                        <input
                            type="text"
                            autoComplete="off"
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
                        <h2 className="font-medium">{t('adminSettings.workerRuntime')}</h2>
                        <p className="text-sm text-muted-foreground">
                            {t('adminSettings.workerRuntimeHelp')}
                        </p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">{t('adminSettings.workerTimeout')}</label>
                        <input
                            type="number"
                            min="1"
                            autoComplete="off"
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
                            {t('adminSettings.workerTimeoutHelp')}
                        </p>
                    </div>
                </div>
            );
        }

        if (selectedGroup.type === 'ai') {
            return (
                <div className="space-y-4">
                    <div>
                        <h2 className="font-medium">{t('adminSettings.aiRuntime')}</h2>
                        <p className="text-sm text-muted-foreground">
                            {t('adminSettings.aiRuntimeHelp')}
                        </p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">{t('adminSettings.aiProviderMode')}</label>
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
                            <option value="local">{t('adminSettings.aiProviderLocal')}</option>
                            <option value="openai_compatible">{t('adminSettings.aiProviderOpenAiCompatible')}</option>
                            <option value="gemini">{t('adminSettings.aiProviderGemini')}</option>
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">{t('adminSettings.defaultAiModel')}</label>
                        <input
                            type="text"
                            autoComplete="off"
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
                            {t('adminSettings.modelExamples', {
                                ollama: 'llama3.1:8b',
                                gemini: 'gemini-2.0-flash',
                                models: 'models/',
                            })}
                        </p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">{t('adminSettings.baseUrl')}</label>
                        <input
                            type="text"
                            autoComplete="url"
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
                            {t('adminSettings.geminiModeHelp', {
                                url: 'https://generativelanguage.googleapis.com/v1beta/openai',
                            })}
                        </p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">{t('adminSettings.apiKey')}</label>
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

        if (selectedGroup.type === 'interface') {
            return (
                <div className="space-y-4">
                    <div>
                        <h2 className="font-medium">{t('adminSettings.languageTitle')}</h2>
                        <p className="text-sm text-muted-foreground">
                            {t('adminSettings.languageDescription')}
                        </p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium mb-1">{t('language.label')}</label>
                        <select
                            className="input-shell w-full p-2 text-sm"
                            value={i18n.language}
                            onChange={(e) => i18n.changeLanguage(e.target.value)}
                        >
                            {SUPPORTED_LANGUAGES.map((language) => (
                                <option key={language} value={language}>
                                    {language === 'pt-BR' ? t('language.portuguese') : t('language.english')}
                                </option>
                            ))}
                        </select>
                    </div>
                </div>
            );
        }

        if (selectedGroup.type === 'metadata_libraries') {
            if (form.plugin_settings.length === 0) {
                return <p className="text-sm text-muted-foreground">{t('adminSettings.metadataGroupNotFound')}</p>;
            }
            return (
                <div className="space-y-4">
                    {form.plugin_settings.map((group) => renderPluginGroup(group))}
                </div>
            );
        }

        return <p className="text-sm text-muted-foreground">{t('adminSettings.noGroupFound')}</p>;
    };

    return (
        <div className="app-page">
            <div className="page-header flex flex-wrap items-start justify-between gap-2">
                <div>
                    <h1 className="page-title">{t('adminSettings.title')}</h1>
                </div>
                <AdminTabs />
            </div>

            {loading ? (
                <div className="flex justify-center p-12">
                    <Loader2 className="animate-spin text-primary" size={30} />
                </div>
            ) : (
                <form onSubmit={handleSave} className="flex flex-1 min-h-0 flex-col gap-3 xl:flex-row">
                    <aside className="surface-card w-full space-y-2 overflow-auto p-2 xl:w-64 xl:shrink-0">
                        <div className="relative">
                            <Search className="w-4 h-4 absolute left-2 top-2.5 text-muted-foreground" />
                            <input
                                type="text"
                                value={groupFilter}
                                onChange={(e) => setGroupFilter(e.target.value)}
                                placeholder={t('adminSettings.searchPlaceholder')}
                                autoComplete="off"
                                className="input-shell w-full pl-8 pr-2 py-1.5 text-sm"
                            />
                        </div>

                        <div className="space-y-1">
                            {groups.map((group) => (
                                <button
                                    key={group.id}
                                    type="button"
                                    onClick={() => setActiveGroupId(group.id)}
                                    className={`w-full text-left rounded-md px-2.5 py-1.5 border transition-colors ${
                                        activeGroupId === group.id
                                            ? 'bg-accent text-accent-foreground border-border'
                                            : 'bg-card hover:bg-accent/65 text-foreground border-transparent'
                                    }`}
                                >
                                    <div className="text-sm font-medium truncate">{group.title}</div>
                                    <div className={`text-xs truncate ${activeGroupId === group.id ? 'text-accent-foreground/80' : 'text-muted-foreground'}`}>
                                        {group.description}
                                    </div>
                                </button>
                            ))}
                        </div>
                    </aside>

                    <section className="surface-card flex-1 min-h-0 min-w-0 overflow-auto p-4 space-y-4">
                        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 pb-3">
                            <div>
                                <h2 className="text-sm font-semibold">{selectedGroup?.title || t('adminSettings.settingsGroup')}</h2>
                                <p className="text-xs text-muted-foreground">{selectedGroup?.description || t('adminSettings.selectGroup')}</p>
                            </div>
                            <button
                                type="submit"
                                disabled={saving}
                                className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                            >
                                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                                {t('adminSettings.save')}
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
