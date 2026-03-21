import { useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { queryKeys } from '../../../lib/queryKeys';
import { metadataService } from '../../../services/metadata';

export function useMetadataCategoriesQuery(options = {}) {
    return useQuery({
        queryKey: queryKeys.metadata.categories(),
        queryFn: ({ signal }) => metadataService.listCategories({ signal }),
        staleTime: 30000,
        ...options,
    });
}

export function useMetadataLibrariesQuery(options = {}) {
    return useQuery({
        queryKey: queryKeys.metadata.libraries(),
        queryFn: ({ signal }) => metadataService.listMetadataLibraries({ signal }),
        staleTime: 30000,
        ...options,
    });
}

export function useMetadataCategoryStatsQuery(options = {}) {
    return useQuery({
        queryKey: queryKeys.metadata.categoryStats(),
        queryFn: () => metadataService.getCategoryStats(),
        ...options,
    });
}

export function useMetadataCategoryDashboardQuery(categoryId, options = {}) {
    return useQuery({
        queryKey: queryKeys.metadata.categoryDashboard(categoryId),
        queryFn: () => metadataService.getCategoryDashboard(categoryId),
        enabled: Boolean(categoryId) && (options.enabled ?? true),
        staleTime: 30000,
        ...options,
    });
}

export function useMetadataFormLayoutsQuery(options = {}) {
    return useQuery({
        queryKey: queryKeys.metadata.formLayouts(),
        queryFn: () => metadataService.listFormLayouts(),
        ...options,
    });
}

export function useMetadataActions() {
    const getCategories = useCallback((options = {}) => metadataService.getCategories(options), []);
    const listCategories = useCallback((options = {}) => metadataService.listCategories(options), []);
    const createCategory = useCallback((name, description) => metadataService.createCategory(name, description), []);
    const deleteCategory = useCallback((categoryId) => metadataService.deleteCategory(categoryId), []);
    const createAttribute = useCallback((categoryId, attribute) => metadataService.createAttribute(categoryId, attribute), []);
    const deleteAttribute = useCallback((attributeId) => metadataService.deleteAttribute(attributeId), []);
    const updateAttribute = useCallback((attributeId, attribute) => metadataService.updateAttribute(attributeId, attribute), []);
    const getItemMetadata = useCallback((accountId, itemId) => metadataService.getItemMetadata(accountId, itemId), []);
    const saveItemMetadata = useCallback((metadata) => metadataService.saveItemMetadata(metadata), []);
    const updateItemMetadataField = useCallback(
        (accountId, itemId, attributeId, payload) => metadataService.updateItemMetadataField(accountId, itemId, attributeId, payload),
        [],
    );
    const deleteItemMetadata = useCallback((accountId, itemId) => metadataService.deleteItemMetadata(accountId, itemId), []);
    const batchDeleteMetadata = useCallback((accountId, itemIds) => metadataService.batchDeleteMetadata(accountId, itemIds), []);
    const getItemMetadataHistory = useCallback((accountId, itemId) => metadataService.getItemMetadataHistory(accountId, itemId), []);
    const undoMetadataBatch = useCallback((batchId) => metadataService.undoMetadataBatch(batchId), []);
    const listRules = useCallback(() => metadataService.listRules(), []);
    const createRule = useCallback((rule) => metadataService.createRule(rule), []);
    const updateRule = useCallback((ruleId, rule) => metadataService.updateRule(ruleId, rule), []);
    const deleteRule = useCallback((ruleId) => metadataService.deleteRule(ruleId), []);
    const previewRule = useCallback((payload) => metadataService.previewRule(payload), []);
    const getCategoryStats = useCallback(() => metadataService.getCategoryStats(), []);
    const listFormLayouts = useCallback(() => metadataService.listFormLayouts(), []);
    const getFormLayout = useCallback((categoryId) => metadataService.getFormLayout(categoryId), []);
    const saveFormLayout = useCallback((categoryId, payload) => metadataService.saveFormLayout(categoryId, payload), []);
    const getSeriesSummary = useCallback((categoryId, params = {}) => metadataService.getSeriesSummary(categoryId, params), []);
    const getCategoryDashboard = useCallback((categoryId) => metadataService.getCategoryDashboard(categoryId), []);
    const listMetadataLibraries = useCallback((options = {}) => metadataService.listMetadataLibraries(options), []);
    const activateMetadataLibrary = useCallback((libraryKey) => metadataService.activateMetadataLibrary(libraryKey), []);
    const deactivateMetadataLibrary = useCallback((libraryKey) => metadataService.deactivateMetadataLibrary(libraryKey), []);

    return useMemo(() => ({
        getCategories,
        listCategories,
        createCategory,
        deleteCategory,
        createAttribute,
        deleteAttribute,
        updateAttribute,
        getItemMetadata,
        saveItemMetadata,
        updateItemMetadataField,
        deleteItemMetadata,
        batchDeleteMetadata,
        getItemMetadataHistory,
        undoMetadataBatch,
        listRules,
        createRule,
        updateRule,
        deleteRule,
        previewRule,
        getCategoryStats,
        listFormLayouts,
        getFormLayout,
        saveFormLayout,
        getSeriesSummary,
        getCategoryDashboard,
        listMetadataLibraries,
        activateMetadataLibrary,
        deactivateMetadataLibrary,
    }), [
        activateMetadataLibrary,
        batchDeleteMetadata,
        createAttribute,
        createCategory,
        createRule,
        deactivateMetadataLibrary,
        deleteAttribute,
        deleteCategory,
        deleteItemMetadata,
        deleteRule,
        getCategories,
        listCategories,
        getCategoryDashboard,
        getCategoryStats,
        getFormLayout,
        getItemMetadata,
        getItemMetadataHistory,
        getSeriesSummary,
        listFormLayouts,
        listMetadataLibraries,
        listRules,
        previewRule,
        saveFormLayout,
        saveItemMetadata,
        undoMetadataBatch,
        updateAttribute,
        updateItemMetadataField,
        updateRule,
    ]);
}

export default useMetadataCategoriesQuery;
