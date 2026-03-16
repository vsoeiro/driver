import { Bot, Database, FileText, Folder, HardDrive, Shield, Sparkles, Wand2 } from 'lucide-react';
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useWorkspaceContext } from '../contexts/WorkspaceContext';
import { WORKSPACE_ACTION_IDS, formatWorkspaceFilterLabel, getDefaultWorkspaceActions } from '../lib/workspace';

const ACTION_ICONS = {
    [WORKSPACE_ACTION_IDS.ACCOUNTS]: HardDrive,
    [WORKSPACE_ACTION_IDS.DRIVE]: Folder,
    [WORKSPACE_ACTION_IDS.LIBRARY]: FileText,
    [WORKSPACE_ACTION_IDS.METADATA]: Database,
    [WORKSPACE_ACTION_IDS.RULES]: Wand2,
    [WORKSPACE_ACTION_IDS.JOBS]: Sparkles,
    [WORKSPACE_ACTION_IDS.AI]: Bot,
    [WORKSPACE_ACTION_IDS.ADMIN]: Shield,
};

export default function WorkspaceContextBar({ onOpenAssistant = null }) {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const { workspace } = useWorkspaceContext();

    const actions = useMemo(() => {
        if (Array.isArray(workspace.availableActions) && workspace.availableActions.length > 0) {
            return workspace.availableActions;
        }
        return getDefaultWorkspaceActions(t, workspace);
    }, [t, workspace]);

    const filterLabels = useMemo(
        () => (workspace.activeFilters || []).map(formatWorkspaceFilterLabel).filter(Boolean),
        [workspace.activeFilters],
    );

    const selectedCount = Array.isArray(workspace.selectedIds) ? workspace.selectedIds.length : 0;
    const metricLabels = Array.isArray(workspace.metrics) ? workspace.metrics.filter(Boolean) : [];
    const hasContent = Boolean(
        workspace.title
        || workspace.subtitle
        || selectedCount
        || filterLabels.length
        || metricLabels.length
        || actions.length,
    );

    if (!hasContent) return null;

    return (
        <section className="workspace-context-strip border-b border-border/70 px-3 py-3 md:px-4">
            <div className="workspace-context-grid">
                <div className="min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                        <span className="workspace-context-kicker">
                            {workspace.entityType || t('workspace.current', { defaultValue: 'workspace' })}
                        </span>
                        {selectedCount > 0 && (
                            <span className="workspace-context-chip workspace-context-chip-accent">
                                {t('workspace.selection', { count: selectedCount, defaultValue: `${selectedCount} selecionado(s)` })}
                            </span>
                        )}
                        {metricLabels.map((metric) => (
                            <span key={metric} className="workspace-context-chip">
                                {metric}
                            </span>
                        ))}
                    </div>
                    {workspace.title && (
                        <div className="min-w-0">
                            <div className="workspace-context-title">{workspace.title}</div>
                            {workspace.subtitle && (
                                <p className="workspace-context-subtitle">{workspace.subtitle}</p>
                            )}
                        </div>
                    )}
                    {filterLabels.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                            {filterLabels.slice(0, 5).map((filterLabel) => (
                                <span key={filterLabel} className="workspace-context-chip">
                                    {filterLabel}
                                </span>
                            ))}
                        </div>
                    )}
                </div>

                <div className="flex flex-wrap items-center justify-start gap-2 xl:justify-end">
                    {actions.map((action) => {
                        const Icon = ACTION_ICONS[action.id] || Folder;
                        const isAssistantAction = action.id === WORKSPACE_ACTION_IDS.AI && typeof onOpenAssistant === 'function';

                        return (
                            <button
                                key={`${action.id}:${action.to}`}
                                type="button"
                                onClick={() => {
                                    if (isAssistantAction) {
                                        onOpenAssistant();
                                        return;
                                    }
                                    navigate(action.to, { state: action.state || null });
                                }}
                                className={`workspace-action-button ${
                                    action.id === WORKSPACE_ACTION_IDS.AI ? 'workspace-action-button-primary' : ''
                                }`}
                            >
                                <Icon size={14} />
                                <span>{action.label}</span>
                            </button>
                        );
                    })}
                </div>
            </div>
        </section>
    );
}
