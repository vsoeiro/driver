import { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import AIAssistantWorkspace from '../components/AIAssistantWorkspace';
import { useWorkspacePage } from '../contexts/WorkspaceContext';

export default function AIAssistant() {
    const { t } = useTranslation();
    const location = useLocation();
    useWorkspacePage(useMemo(() => ({
        title: t('aiAssistant.title'),
        subtitle: t('workspace.aiSubtitle', { defaultValue: 'Assistente contextual para explorar, revisar e conectar fluxos.' }),
        entityType: 'assistant',
        entityId: 'ai',
        sourceRoute: location.pathname,
        suggestedPrompts: [],
    }), [location.pathname, t]));
    return <AIAssistantWorkspace showPageHeader />;
}
