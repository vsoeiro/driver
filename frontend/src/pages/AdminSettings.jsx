import { useEffect, useState } from 'react';
import { Loader2, Save } from 'lucide-react';
import { settingsService } from '../services/settings';
import { useToast } from '../contexts/ToastContext';

export default function AdminSettings() {
    const { showToast } = useToast();
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState({
        enable_daily_sync_scheduler: true,
        daily_sync_cron: '0 0 * * *',
    });

    useEffect(() => {
        const load = async () => {
            setLoading(true);
            try {
                const data = await settingsService.getRuntimeSettings();
                setForm({
                    enable_daily_sync_scheduler: data.enable_daily_sync_scheduler,
                    daily_sync_cron: data.daily_sync_cron,
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

    const handleSave = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            const data = await settingsService.updateRuntimeSettings(form);
            setForm({
                enable_daily_sync_scheduler: data.enable_daily_sync_scheduler,
                daily_sync_cron: data.daily_sync_cron,
            });
            showToast('Settings saved successfully', 'success');
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to save settings';
            showToast(message, 'error');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="flex flex-col h-screen">
            <div className="p-4 border-b bg-background">
                <h1 className="text-lg font-semibold text-foreground">Admin Settings</h1>
                <p className="text-sm text-muted-foreground">Persisted runtime settings applied without restarting the API.</p>
            </div>

            <main className="flex-1 overflow-auto p-4">
                {loading ? (
                    <div className="flex justify-center p-12">
                        <Loader2 className="animate-spin text-primary" size={30} />
                    </div>
                ) : (
                    <form onSubmit={handleSave} className="max-w-2xl space-y-6">
                        <div className="border rounded-lg p-4 bg-card space-y-4">
                            <div className="flex items-center justify-between gap-4">
                                <div>
                                    <h2 className="font-medium">Daily Sync Scheduler</h2>
                                    <p className="text-sm text-muted-foreground">
                                        Toggle automatic sync jobs based on cron schedule.
                                    </p>
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
                                <p className="text-xs text-muted-foreground mt-1">
                                    Format: minute hour day month weekday (5 fields), ex.: <code>13 0 * * *</code>
                                </p>
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={saving}
                            className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 text-sm font-medium disabled:opacity-50 inline-flex items-center gap-2"
                        >
                            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                            Save Settings
                        </button>
                    </form>
                )}
            </main>
        </div>
    );
}

