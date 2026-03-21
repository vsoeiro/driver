import { useCallback, useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { queryKeys } from '../../../lib/queryKeys';
import { aiService } from '../../../services/ai';

export function useAiSessionsQuery({ limit = 50, offset = 0, ...options } = {}) {
    return useQuery({
        queryKey: queryKeys.ai.sessions(limit, offset),
        queryFn: () => aiService.listChatSessions(limit, offset),
        retry: false,
        ...options,
    });
}

export function useAiMessagesQuery(sessionId, { limit = 300, ...options } = {}) {
    return useQuery({
        queryKey: queryKeys.ai.messages(sessionId, limit),
        queryFn: () => aiService.listSessionMessages(sessionId, limit),
        enabled: Boolean(sessionId) && (options.enabled ?? true),
        retry: false,
        ...options,
    });
}

export function useCreateChatSessionMutation(options = {}) {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: () => aiService.createChatSession(null),
        onSuccess: async (...args) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.ai.sessionsRoot() });
            await options.onSuccess?.(...args);
        },
        onError: options.onError,
        onMutate: options.onMutate,
        onSettled: options.onSettled,
    });
}

export function useGenerateSessionTitleMutation(options = {}) {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (sessionId) => aiService.generateSessionTitle(sessionId),
        onMutate: options.onMutate,
        onSuccess: options.onSuccess,
        onError: options.onError,
        onSettled: async (...args) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.ai.sessionsRoot() });
            await options.onSettled?.(...args);
        },
    });
}

export function usePostChatMessageMutation(options = {}) {
    return useMutation({
        mutationFn: (payload) => aiService.postChatMessage(payload.sessionId, payload.message, { signal: payload.signal }),
        onMutate: options.onMutate,
        onSuccess: options.onSuccess,
        onError: options.onError,
        onSettled: options.onSettled,
    });
}

export function useResolveAiConfirmationMutation(options = {}) {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ sessionId, confirmationId, approve }) => aiService.resolveConfirmation(sessionId, confirmationId, approve),
        onSuccess: async (...args) => {
            await options.onSuccess?.(...args);
            const variables = args[1];
            if (variables?.sessionId) {
                await queryClient.invalidateQueries({ queryKey: queryKeys.ai.messagesRoot(variables.sessionId) });
            }
            await queryClient.invalidateQueries({ queryKey: queryKeys.ai.sessionsRoot() });
        },
        onError: options.onError,
        onMutate: options.onMutate,
        onSettled: options.onSettled,
    });
}

export function useDeleteChatSessionMutation(options = {}) {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (sessionId) => aiService.deleteChatSession(sessionId),
        onSuccess: async (...args) => {
            const sessionId = args[1];
            await queryClient.invalidateQueries({ queryKey: queryKeys.ai.sessionsRoot() });
            if (sessionId) {
                await queryClient.invalidateQueries({ queryKey: queryKeys.ai.messagesRoot(sessionId) });
            }
            await options.onSuccess?.(...args);
        },
        onError: options.onError,
        onMutate: options.onMutate,
        onSettled: options.onSettled,
    });
}

export function useAiActions() {
    const queryClient = useQueryClient();

    const listChatSessions = useCallback((limit = 30, offset = 0) => aiService.listChatSessions(limit, offset), []);
    const listSessionMessages = useCallback((sessionId, limit = 200) => aiService.listSessionMessages(sessionId, limit), []);
    const createChatSession = useCallback((title = null) => aiService.createChatSession(title), []);
    const deleteChatSession = useCallback((sessionId) => aiService.deleteChatSession(sessionId), []);
    const generateSessionTitle = useCallback((sessionId) => aiService.generateSessionTitle(sessionId), []);
    const postChatMessage = useCallback((sessionId, message, options = {}) => aiService.postChatMessage(sessionId, message, options), []);
    const resolveConfirmation = useCallback((sessionId, confirmationId, approve) => aiService.resolveConfirmation(sessionId, confirmationId, approve), []);
    const getToolsCatalog = useCallback(() => aiService.getToolsCatalog(), []);
    const invalidateSessions = useCallback(() => queryClient.invalidateQueries({ queryKey: queryKeys.ai.sessionsRoot() }), [queryClient]);
    const invalidateMessages = useCallback((sessionId) => queryClient.invalidateQueries({ queryKey: queryKeys.ai.messagesRoot(sessionId) }), [queryClient]);
    const setMessagesData = useCallback((sessionId, updater) => {
        queryClient.setQueryData(queryKeys.ai.messages(sessionId, 300), (prev) => updater(Array.isArray(prev) ? prev : []));
    }, [queryClient]);

    return useMemo(() => ({
        listChatSessions,
        listSessionMessages,
        createChatSession,
        deleteChatSession,
        generateSessionTitle,
        postChatMessage,
        resolveConfirmation,
        getToolsCatalog,
        invalidateSessions,
        invalidateMessages,
        setMessagesData,
    }), [
        createChatSession,
        deleteChatSession,
        generateSessionTitle,
        getToolsCatalog,
        invalidateMessages,
        invalidateSessions,
        listChatSessions,
        listSessionMessages,
        postChatMessage,
        resolveConfirmation,
        setMessagesData,
    ]);
}

export default useAiSessionsQuery;
