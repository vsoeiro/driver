import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';

const EMPTY_WORKSPACE = {
    title: '',
    subtitle: '',
    entityType: '',
    entityId: '',
    sourceRoute: '',
    selectedIds: [],
    activeFilters: [],
    availableActions: [],
    suggestedPrompts: [],
    metrics: [],
};

const WorkspaceContext = createContext({
    workspace: EMPTY_WORKSPACE,
    setWorkspace: () => undefined,
    clearWorkspace: () => undefined,
});

function isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function areWorkspaceValuesEqual(left, right) {
    if (Object.is(left, right)) return true;

    if (Array.isArray(left) && Array.isArray(right)) {
        if (left.length !== right.length) return false;
        return left.every((item, index) => areWorkspaceValuesEqual(item, right[index]));
    }

    if (isPlainObject(left) && isPlainObject(right)) {
        const leftKeys = Object.keys(left);
        const rightKeys = Object.keys(right);
        if (leftKeys.length !== rightKeys.length) return false;
        return leftKeys.every((key) => areWorkspaceValuesEqual(left[key], right[key]));
    }

    return false;
}

export function WorkspaceProvider({ children }) {
    const location = useLocation();
    const [workspace, setWorkspaceState] = useState({
        ...EMPTY_WORKSPACE,
        sourceRoute: location.pathname,
    });

    useEffect(() => {
        setWorkspaceState((prev) => (
            prev.sourceRoute === location.pathname
                ? prev
                : {
                    ...prev,
                    sourceRoute: location.pathname,
                }
        ));
    }, [location.pathname]);

    const setWorkspace = useCallback((nextWorkspace) => {
        setWorkspaceState((prev) => {
            const resolvedWorkspace = {
                ...prev,
                ...EMPTY_WORKSPACE,
                ...(typeof nextWorkspace === 'function' ? nextWorkspace(prev) : nextWorkspace),
                sourceRoute: location.pathname,
            };
            return areWorkspaceValuesEqual(prev, resolvedWorkspace) ? prev : resolvedWorkspace;
        });
    }, [location.pathname]);

    const clearWorkspace = useCallback(() => {
        setWorkspaceState((prev) => {
            const clearedWorkspace = {
                ...EMPTY_WORKSPACE,
                sourceRoute: location.pathname,
            };
            return areWorkspaceValuesEqual(prev, clearedWorkspace) ? prev : clearedWorkspace;
        });
    }, [location.pathname]);

    const value = useMemo(() => ({
        workspace,
        setWorkspace,
        clearWorkspace,
    }), [clearWorkspace, setWorkspace, workspace]);

    return (
        <WorkspaceContext.Provider value={value}>
            {children}
        </WorkspaceContext.Provider>
    );
}

export function useWorkspaceContext() {
    return useContext(WorkspaceContext);
}

export function useWorkspacePage(workspaceConfig) {
    const { setWorkspace, clearWorkspace } = useWorkspaceContext();

    useEffect(() => {
        if (!workspaceConfig) return;
        setWorkspace(workspaceConfig);
    }, [setWorkspace, workspaceConfig]);

    useEffect(() => () => {
        clearWorkspace();
    }, [clearWorkspace]);
}

export default WorkspaceContext;
