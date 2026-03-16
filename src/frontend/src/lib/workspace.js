/**
 * Cross-module navigation contract used by workspace actions, activity items and
 * contextual shortcuts.
 *
 * @typedef {Object} CrossLinkTarget
 * @property {string} to
 * @property {string} label
 * @property {string} [description]
 * @property {Object | null} [state]
 */

/**
 * Shared route action contract exposed by the workspace context bar.
 *
 * @typedef {Object} WorkspaceAction
 * @property {string} id
 * @property {string} label
 * @property {string} to
 * @property {Object | null} [state]
 */

export const WORKSPACE_ACTION_IDS = {
    ACCOUNTS: 'accounts',
    DRIVE: 'drive',
    LIBRARY: 'library',
    METADATA: 'metadata',
    RULES: 'rules',
    JOBS: 'jobs',
    AI: 'ai',
    ADMIN: 'admin',
};

function tx(t, key, defaultValue, options = {}) {
    return t(key, { defaultValue, ...options });
}

export function createCrossLinkTarget({ to, label, description = '', state = null }) {
    return { to, label, description, state };
}

export function createWorkspaceAction({ id, label, to, state = null }) {
    return { id, label, to, state };
}

export function buildAssistantContext(workspace = {}, overrides = {}) {
    return {
        route: workspace.sourceRoute || '',
        title: workspace.title || '',
        description: workspace.subtitle || '',
        entityType: workspace.entityType || '',
        entityId: workspace.entityId || '',
        selectedIds: Array.isArray(workspace.selectedIds) ? workspace.selectedIds : [],
        activeFilters: Array.isArray(workspace.activeFilters) ? workspace.activeFilters : [],
        suggestedPrompts: Array.isArray(workspace.suggestedPrompts) ? workspace.suggestedPrompts : [],
        ...overrides,
    };
}

export function getAssistantSuggestedPrompts(workspace = {}, t) {
    const basePrompts = [
        tx(t, 'workspace.aiPrompts.summarize', 'Resuma o contexto atual e destaque riscos.'),
        tx(t, 'workspace.aiPrompts.recommend', 'Sugira as proximas acoes com maior impacto.'),
    ];

    if (workspace.entityType === 'account' || workspace.entityType === 'folder') {
        return [
            tx(t, 'workspace.aiPrompts.accountCleanup', 'Como organizar melhor esta conta e reduzir ruido?'),
            tx(t, 'workspace.aiPrompts.driveGaps', 'Quais lacunas de classificacao ou organizacao existem aqui?'),
            ...basePrompts,
        ];
    }

    if (workspace.entityType === 'library') {
        return [
            tx(t, 'workspace.aiPrompts.duplicates', 'Quais grupos de duplicados devo priorizar primeiro?'),
            tx(t, 'workspace.aiPrompts.metadataCoverage', 'Onde a cobertura de metadata esta fraca?'),
            ...basePrompts,
        ];
    }

    if (workspace.entityType === 'metadata') {
        return [
            tx(t, 'workspace.aiPrompts.metadataCoverage', 'Onde a cobertura de metadata esta fraca?'),
            tx(t, 'workspace.aiPrompts.metadataLayout', 'Como simplificar a leitura e edicao desta categoria?'),
            ...basePrompts,
        ];
    }

    if (workspace.entityType === 'automation') {
        return [
            tx(t, 'workspace.aiPrompts.ruleReview', 'Revise esta automacao e aponte riscos ou melhorias.'),
            tx(t, 'workspace.aiPrompts.jobReview', 'Explique o que aconteceu nestes jobs e o que fazer agora.'),
            ...basePrompts,
        ];
    }

    if (workspace.entityType === 'jobs') {
        return [
            tx(t, 'workspace.aiPrompts.jobReview', 'Explique o que aconteceu nestes jobs e o que fazer agora.'),
            tx(t, 'workspace.aiPrompts.recommend', 'Sugira as proximas acoes com maior impacto.'),
            basePrompts[0],
        ];
    }

    return basePrompts;
}

export function getDefaultWorkspaceActions(t, workspace = {}) {
    const assistantContext = buildAssistantContext(workspace);
    const state = { assistantContext };
    const actions = [
        createWorkspaceAction({
            id: WORKSPACE_ACTION_IDS.LIBRARY,
            label: tx(t, 'workspace.actions.library', 'Biblioteca'),
            to: '/all-files',
            state,
        }),
        createWorkspaceAction({
            id: WORKSPACE_ACTION_IDS.METADATA,
            label: tx(t, 'workspace.actions.metadata', 'Metadata'),
            to: '/metadata',
            state,
        }),
        createWorkspaceAction({
            id: WORKSPACE_ACTION_IDS.RULES,
            label: tx(t, 'workspace.actions.rules', 'Regras'),
            to: '/rules',
            state,
        }),
        createWorkspaceAction({
            id: WORKSPACE_ACTION_IDS.JOBS,
            label: tx(t, 'workspace.actions.jobs', 'Jobs'),
            to: '/jobs',
            state,
        }),
        createWorkspaceAction({
            id: WORKSPACE_ACTION_IDS.AI,
            label: tx(t, 'workspace.actions.ai', 'IA'),
            to: '/ai',
            state,
        }),
    ];

    if (workspace.entityType === 'account' && workspace.entityId) {
        actions.unshift(
            createWorkspaceAction({
                id: WORKSPACE_ACTION_IDS.DRIVE,
                label: tx(t, 'workspace.actions.drive', 'Drive'),
                to: `/drive/${workspace.entityId}`,
                state,
            }),
        );
    }

    if (workspace.sourceRoute !== '/accounts') {
        actions.unshift(
            createWorkspaceAction({
                id: WORKSPACE_ACTION_IDS.ACCOUNTS,
                label: tx(t, 'workspace.actions.accounts', 'Contas'),
                to: '/accounts',
                state,
            }),
        );
    }

    if (!String(workspace.sourceRoute || '').startsWith('/admin')) {
        actions.push(
            createWorkspaceAction({
                id: WORKSPACE_ACTION_IDS.ADMIN,
                label: tx(t, 'workspace.actions.admin', 'Admin'),
                to: '/admin/dashboard',
                state,
            }),
        );
    }

    return actions;
}

export function getJobCrossLinkTarget(job, t) {
    const type = String(job?.type || '').toLowerCase();
    const payload = job?.payload && typeof job.payload === 'object' ? job.payload : {};

    if (payload.account_id) {
        return createCrossLinkTarget({
            to: `/drive/${payload.account_id}`,
            label: tx(t, 'workspace.links.openDrive', 'Abrir drive'),
            description: tx(t, 'workspace.links.openDriveDescription', 'Voltar para a origem desta conta'),
        });
    }

    if (payload.rule_id || type === 'apply_metadata_rule') {
        return createCrossLinkTarget({
            to: '/rules',
            label: tx(t, 'workspace.links.openRuleCenter', 'Abrir regras'),
            description: tx(t, 'workspace.links.openRuleCenterDescription', 'Ir para o workspace de automacao'),
        });
    }

    if (type.includes('duplicate')) {
        return createCrossLinkTarget({
            to: '/all-files',
            label: tx(t, 'workspace.links.openDuplicates', 'Abrir duplicados'),
            description: tx(t, 'workspace.links.openDuplicatesDescription', 'Ir para a aba de arquivos semelhantes'),
            state: { focusTab: 'similar' },
        });
    }

    if (type.includes('metadata') || type.includes('comic') || type.includes('image') || type.includes('book')) {
        return createCrossLinkTarget({
            to: '/metadata',
            label: tx(t, 'workspace.links.openMetadata', 'Abrir metadata'),
            description: tx(t, 'workspace.links.openMetadataDescription', 'Ir para o workspace de metadata'),
        });
    }

    return createCrossLinkTarget({
        to: '/jobs',
        label: tx(t, 'workspace.links.openJobs', 'Abrir jobs'),
        description: tx(t, 'workspace.links.openJobsDescription', 'Ir para o historico operacional'),
    });
}

export function formatWorkspaceFilterLabel(filter) {
    if (!filter) return '';
    if (typeof filter === 'string') return filter;
    if (typeof filter === 'object') {
        if (filter.label) return filter.label;
        if (filter.key && filter.value !== undefined && filter.value !== null && filter.value !== '') {
            return `${filter.key}: ${filter.value}`;
        }
    }
    return String(filter);
}
