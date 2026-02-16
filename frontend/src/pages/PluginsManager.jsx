import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Plug, Power } from 'lucide-react';
import { metadataService } from '../services/metadata';
import { useToast } from '../contexts/ToastContext';

export default function PluginsManager() {
    const { showToast } = useToast();
    const [plugins, setPlugins] = useState([]);
    const [loading, setLoading] = useState(true);
    const [togglingKey, setTogglingKey] = useState(null);

    const loadPlugins = useCallback(async () => {
        try {
            setLoading(true);
            const data = await metadataService.listPlugins();
            setPlugins(data);
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to load plugins';
            showToast(message, 'error');
        } finally {
            setLoading(false);
        }
    }, [showToast]);

    useEffect(() => {
        loadPlugins();
    }, [loadPlugins]);

    const knownPlugins = useMemo(
        () => (plugins.length > 0
            ? plugins
            : [{ key: 'comicrack_core', name: 'ComicRack Core', description: 'Managed comic metadata schema.', is_active: false }]),
        [plugins],
    );

    const togglePlugin = async (plugin) => {
        try {
            setTogglingKey(plugin.key);
            if (plugin.is_active) {
                await metadataService.deactivatePlugin(plugin.key);
                showToast(`${plugin.name} disabled`, 'success');
            } else {
                await metadataService.activatePlugin(plugin.key);
                showToast(`${plugin.name} enabled`, 'success');
            }
            await loadPlugins();
        } catch (error) {
            const message = error?.response?.data?.detail || 'Failed to update plugin';
            showToast(message, 'error');
        } finally {
            setTogglingKey(null);
        }
    };

    return (
        <div className="flex flex-col h-screen">
            <div className="p-4 border-b flex items-center justify-between bg-background sticky top-0 z-10">
                <div className="flex items-center gap-2">
                    <h1 className="text-lg font-semibold text-foreground">Plugins</h1>
                    <span className="text-xs text-muted-foreground font-normal bg-muted px-2 py-0.5 rounded-full">
                        {knownPlugins.length} available
                    </span>
                </div>
            </div>

            <main className="flex-1 overflow-auto p-4">
                {loading ? (
                    <div className="flex justify-center p-12">
                        <Loader2 className="animate-spin text-primary" size={32} />
                    </div>
                ) : (
                    <div className="grid gap-3">
                        {knownPlugins.map((plugin) => (
                            <div key={plugin.key} className="border rounded-lg bg-card p-4 flex items-center justify-between">
                                <div className="flex items-start gap-3 min-w-0">
                                    <div className="p-2 rounded-md bg-primary/10 text-primary">
                                        <Plug size={18} />
                                    </div>
                                    <div className="min-w-0">
                                        <div className="font-semibold">{plugin.name}</div>
                                        <div className="text-xs text-muted-foreground">{plugin.key}</div>
                                        {plugin.description && (
                                            <p className="text-sm text-muted-foreground mt-1">{plugin.description}</p>
                                        )}
                                    </div>
                                </div>

                                <button
                                    onClick={() => togglePlugin(plugin)}
                                    disabled={togglingKey === plugin.key}
                                    className={`inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors disabled:opacity-60 ${
                                        plugin.is_active
                                            ? 'bg-destructive/10 text-destructive hover:bg-destructive/20'
                                            : 'bg-primary text-primary-foreground hover:bg-primary/90'
                                    }`}
                                >
                                    {togglingKey === plugin.key ? <Loader2 size={14} className="animate-spin" /> : <Power size={14} />}
                                    {plugin.is_active ? 'Disable' : 'Enable'}
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </main>
        </div>
    );
}

