import { useEffect, useMemo, useRef, useState } from 'react';
import { Bot, ChevronRight, Loader2, Plus, Send, ShieldAlert, Square, Trash2, Wrench, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useToast } from '../contexts/ToastContext';
import { formatDateTime } from '../utils/dateTime';
import {
    useAiActions,
    useAiMessagesQuery,
    useAiSessionsQuery,
    useCreateChatSessionMutation,
    useDeleteChatSessionMutation,
    useGenerateSessionTitleMutation,
    usePostChatMessageMutation,
    useResolveAiConfirmationMutation,
} from '../features/ai/hooks/useAiData';

const DRAFT_SESSION_ID = '__draft__';

function formatDate(value) {
    if (!value) return '';
    try {
        return formatDateTime(value);
    } catch {
        return value;
    }
}

function parseToolPayload(messageContent) {
    try {
        const parsed = JSON.parse(messageContent || '{}');
        return typeof parsed === 'object' && parsed !== null ? parsed : null;
    } catch {
        return null;
    }
}

function extractToolSources(payload) {
    if (!payload || typeof payload !== 'object') return [];
    const result = payload.result_summary || {};
    const sources = [];
    const items = Array.isArray(result.items) ? result.items : [];
    const accounts = Array.isArray(result.accounts) ? result.accounts : [];
    const groups = Array.isArray(result.groups) ? result.groups : [];

    for (const account of accounts.slice(0, 5)) {
        sources.push({
            type: 'account',
            label: account.email || account.display_name || account.id || 'Account',
            detail: account.id || null,
        });
    }
    for (const item of items.slice(0, 8)) {
        sources.push({
            type: 'file',
            label: item.name || item.path || item.item_id || 'File',
            detail: item.account_id || item.path || null,
        });
    }
    for (const group of groups.slice(0, 4)) {
        const first = Array.isArray(group.items) ? group.items[0] : null;
        sources.push({
            type: 'group',
            label: group.signature || group.group_key || first?.name || 'Similar group',
            detail: first?.path || null,
        });
    }
    return sources;
}

export default function AIAssistantWorkspace({
    showPageHeader = true,
    className = '',
    compact = false,
    startWithDraft = false,
    onCompactClose = null,
}) {
    const { t } = useTranslation();
    const { showToast } = useToast();
    const {
        deleteChatSession,
        invalidateMessages,
        invalidateSessions,
        setMessagesData,
    } = useAiActions();
    const [selectedSessionId, setSelectedSessionId] = useState('');
    const [hasDraftSession, setHasDraftSession] = useState(false);
    const [inputMessage, setInputMessage] = useState('');
    const [pendingConfirmation, setPendingConfirmation] = useState(null);
    const [optimisticMessages, setOptimisticMessages] = useState([]);
    const [generatingTitleSessionIds, setGeneratingTitleSessionIds] = useState(new Set());
    const [animatedMessageIds, setAnimatedMessageIds] = useState(new Set());
    const [expandedToolIds, setExpandedToolIds] = useState(new Set());
    const activeRequestRef = useRef(null);
    const knownMessageIdsRef = useRef(new Set());
    const messagesContainerRef = useRef(null);
    const messageEndRef = useRef(null);

    const sessionsQuery = useAiSessionsQuery({
        refetchInterval: (query) => {
            const data = query.state.data || [];
            return data.some((session) => session.title_pending) ? 3000 : false;
        },
    });

    const messagesQuery = useAiMessagesQuery(selectedSessionId, {
        enabled: !!selectedSessionId && selectedSessionId !== DRAFT_SESSION_ID,
    });

    useEffect(() => {
        if (startWithDraft && !selectedSessionId) {
            setHasDraftSession(true);
            setSelectedSessionId(DRAFT_SESSION_ID);
            setPendingConfirmation(null);
        }
    }, [startWithDraft, selectedSessionId]);

    useEffect(() => {
        if (!selectedSessionId && sessionsQuery.data?.length && !hasDraftSession) {
            setSelectedSessionId(sessionsQuery.data[0].id);
        }
    }, [selectedSessionId, sessionsQuery.data, hasDraftSession]);

    useEffect(() => {
        if (sessionsQuery.isLoading) return;
        if (selectedSessionId) return;
        if ((sessionsQuery.data || []).length > 0) return;
        setHasDraftSession(true);
        setSelectedSessionId(DRAFT_SESSION_ID);
    }, [sessionsQuery.isLoading, sessionsQuery.data, selectedSessionId]);

    const sessions = useMemo(() => {
        const persisted = sessionsQuery.data || [];
        if (!hasDraftSession) return persisted;
        return [
            {
                id: DRAFT_SESSION_ID,
                title: t('aiAssistant.newSession'),
                updated_at: null,
                title_pending: false,
            },
            ...persisted,
        ];
    }, [sessionsQuery.data, hasDraftSession, t]);

    const createSessionMutation = useCreateChatSessionMutation({
        onError: (error) => {
            showToast(error?.response?.data?.detail || t('aiAssistant.failedCreateSession'), 'error');
        },
    });

    const generateTitleMutation = useGenerateSessionTitleMutation({
        onMutate: (sessionId) => {
            setGeneratingTitleSessionIds((prev) => {
                const next = new Set(prev);
                next.add(sessionId);
                return next;
            });
        },
        onSettled: (_, __, sessionId) => {
            setGeneratingTitleSessionIds((prev) => {
                const next = new Set(prev);
                next.delete(sessionId);
                return next;
            });
        },
    });

    const postMessageMutation = usePostChatMessageMutation({
        onMutate: (variables) => {
            const nowIso = new Date().toISOString();
            const baseId = Date.now();
            const tempUserId = `temp-user-${baseId}`;
            const tempAssistantId = `temp-assistant-${baseId}`;
            setOptimisticMessages((prev) => [
                ...prev,
                {
                    id: tempUserId,
                    session_id: variables.sessionId,
                    role: 'user',
                    content_redacted: variables.message,
                    created_at: nowIso,
                    isOptimistic: true,
                },
                {
                    id: tempAssistantId,
                    session_id: variables.sessionId,
                    role: 'assistant',
                    content_redacted: '',
                    created_at: nowIso,
                    isLoadingPlaceholder: true,
                    isOptimistic: true,
                },
            ]);
            return { tempUserId, tempAssistantId, sessionId: variables.sessionId };
        },
        onSuccess: (response, variables, context) => {
            setPendingConfirmation(response.pending_confirmation || null);
            setOptimisticMessages((prev) =>
                prev.filter((msg) => msg.id !== context?.tempUserId && msg.id !== context?.tempAssistantId)
            );
            if (response.assistant_message) {
                setMessagesData(variables.sessionId, (prev) => {
                    const current = Array.isArray(prev) ? [...prev] : [];
                    if (!current.some((item) => item.id === response.assistant_message.id)) {
                        current.push(response.assistant_message);
                    }
                    return current;
                });
            }
            void invalidateMessages(variables.sessionId);
            void invalidateSessions();
            if (!generatingTitleSessionIds.has(variables.sessionId)) {
                generateTitleMutation.mutate(variables.sessionId);
            }
            if (response.tool_trace?.some((trace) => trace.status === 'failed')) {
                showToast(t('aiAssistant.toolFailed'), 'warning');
            }
        },
        onError: (error, _, context) => {
            if (error?.code === 'ERR_CANCELED') return;
            setOptimisticMessages((prev) =>
                prev.filter((msg) => msg.id !== context?.tempUserId && msg.id !== context?.tempAssistantId)
            );
            showToast(error?.response?.data?.detail || t('aiAssistant.failedSend'), 'error');
        },
        onSettled: () => {
            activeRequestRef.current = null;
        },
    });

    const confirmationMutation = useResolveAiConfirmationMutation({
        onSuccess: (response) => {
            setPendingConfirmation(response.pending_confirmation?.status === 'pending' ? response.pending_confirmation : null);
        },
        onError: (error) => {
            showToast(error?.response?.data?.detail || t('aiAssistant.failedConfirm'), 'error');
        },
    });

    const deleteSessionMutation = useDeleteChatSessionMutation({
        onSuccess: (_, sessionId) => {
            if (selectedSessionId === sessionId) {
                setSelectedSessionId('');
                setPendingConfirmation(null);
                setOptimisticMessages([]);
            }
        },
        onError: (error) => {
            showToast(error?.response?.data?.detail || t('aiAssistant.failedDeleteSession'), 'error');
        },
    });

    const isSending = postMessageMutation.isPending;
    const isConfirming = confirmationMutation.isPending;
    const isBusy = isSending || isConfirming;

    useEffect(() => {
        postMessageMutation.reset();
    }, [selectedSessionId, postMessageMutation]);

    useEffect(() => {
        setExpandedToolIds(new Set());
    }, [selectedSessionId]);

    const messages = useMemo(() => {
        const persisted = messagesQuery.data || [];
        const optimisticForSession = optimisticMessages.filter((msg) => msg.session_id === selectedSessionId);
        return [...persisted, ...optimisticForSession];
    }, [messagesQuery.data, optimisticMessages, selectedSessionId]);

    useEffect(() => {
        const newIds = [];
        for (const message of messages) {
            if (!knownMessageIdsRef.current.has(message.id)) {
                knownMessageIdsRef.current.add(message.id);
                if (message.role !== 'user') {
                    newIds.push(message.id);
                }
            }
        }
        if (newIds.length === 0) return;
        setAnimatedMessageIds((prev) => {
            const next = new Set(prev);
            newIds.forEach((id) => next.add(id));
            return next;
        });
        const timeout = window.setTimeout(() => {
            setAnimatedMessageIds((prev) => {
                const next = new Set(prev);
                newIds.forEach((id) => next.delete(id));
                return next;
            });
        }, 320);
        return () => window.clearTimeout(timeout);
    }, [messages]);

    useEffect(() => {
        const container = messagesContainerRef.current;
        if (!container) return;
        const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
        const shouldStickToBottom = distanceFromBottom < 140;
        if (!shouldStickToBottom) return;
        messageEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, [messages]);

    const submitMessage = () => {
        const execute = async () => {
            const message = inputMessage.trim();
            if (!message || !selectedSessionId || isBusy) return;

            let targetSessionId = selectedSessionId;
            let createdSessionId = null;
            if (selectedSessionId === DRAFT_SESSION_ID) {
                const created = await createSessionMutation.mutateAsync();
                targetSessionId = created.id;
                createdSessionId = created.id;
                setSelectedSessionId(created.id);
                setHasDraftSession(false);
                setPendingConfirmation(null);
            }

            setInputMessage('');
            const controller = new AbortController();
            activeRequestRef.current = controller;

            try {
                await postMessageMutation.mutateAsync({ sessionId: targetSessionId, message, signal: controller.signal });
            } catch {
                if (!createdSessionId) return;
                try {
                    await deleteChatSession(createdSessionId);
                    await invalidateSessions();
                    setSelectedSessionId(DRAFT_SESSION_ID);
                    setHasDraftSession(true);
                } catch {
                    // ignore cleanup failures
                }
            }
        };

        void execute();
    };

    const stopMessage = () => {
        if (!activeRequestRef.current) return;
        activeRequestRef.current.abort();
        activeRequestRef.current = null;
        showToast(t('aiAssistant.responseInterrupted'), 'info', 2500);
    };

    const toggleToolCard = (messageId) => {
        setExpandedToolIds((prev) => {
            const next = new Set(prev);
            if (next.has(messageId)) next.delete(messageId);
            else next.add(messageId);
            return next;
        });
    };

    return (
        <div className={`${showPageHeader ? 'app-page' : ''} h-full min-h-0 ${className}`.trim()}>
            {showPageHeader && (
                <div className="page-header">
                    <h1 className="page-title">{t('aiAssistant.title')}</h1>
                    <p className="page-subtitle">{t('aiAssistant.subtitle')}</p>
                </div>
            )}

            <div className={`${compact ? 'flex' : 'grid min-h-0 grid-cols-1 gap-4 xl:grid-cols-[300px_minmax(0,1fr)]'} ${showPageHeader ? 'flex-1' : 'h-full'}`}>
                {!compact && (
                    <section className="surface-card flex min-h-0 flex-col overflow-hidden p-3">
                        <div className="mb-3 flex items-center justify-between">
                            <div className="text-sm font-semibold">{t('aiAssistant.sessions')}</div>
                            <button
                                type="button"
                                className="ghost-icon-button"
                                onClick={() => {
                                    setHasDraftSession(true);
                                    setSelectedSessionId(DRAFT_SESSION_ID);
                                    setPendingConfirmation(null);
                                    setOptimisticMessages([]);
                                }}
                                title={t('aiAssistant.newSession')}
                            >
                                <Plus size={16} />
                            </button>
                        </div>
                        <div className="min-h-0 flex-1 space-y-1 overflow-auto pr-1">
                            {sessions.map((session) => (
                                <div
                                    key={session.id}
                                    className={`group w-full rounded-md border px-2 py-2 text-left text-sm ${
                                        session.id === selectedSessionId
                                            ? 'border-primary/45 bg-primary/10 text-foreground'
                                            : 'border-transparent text-muted-foreground hover:border-border/60 hover:bg-accent/50 hover:text-foreground'
                                    }`}
                                >
                                    <div className="flex items-start gap-2">
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setSelectedSessionId(session.id);
                                                setHasDraftSession(session.id === DRAFT_SESSION_ID);
                                                setPendingConfirmation(null);
                                            }}
                                            className="min-w-0 flex-1 text-left"
                                        >
                                            <div className="truncate font-medium">{session.title || t('aiAssistant.newSession')}</div>
                                            <div className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                                                {(session.title_pending || generatingTitleSessionIds.has(session.id)) && (
                                                    <Loader2 size={12} className="animate-spin" />
                                                )}
                                                <span>{formatDate(session.updated_at)}</span>
                                            </div>
                                        </button>
                                        <button
                                            type="button"
                                            className="ghost-icon-button h-7 w-7 p-0 opacity-0 group-hover:opacity-100"
                                            title={t('aiAssistant.deleteSession')}
                                            onClick={() => deleteSessionMutation.mutate(session.id)}
                                            disabled={session.id === DRAFT_SESSION_ID}
                                        >
                                            <Trash2 size={13} />
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>
                )}

                <section className={`surface-card flex min-h-0 flex-col overflow-hidden ${compact ? 'w-full' : ''}`}>
                    <header className="flex h-14 items-center gap-2 border-b border-border/70 px-4">
                        <Bot size={16} className="text-primary" />
                        {compact && typeof onCompactClose === 'function' ? (
                            <button
                                type="button"
                                onClick={onCompactClose}
                                className="ghost-icon-button h-8 w-8 p-0"
                                title={t('common.close')}
                                aria-label={t('common.close')}
                            >
                                <X size={14} />
                            </button>
                        ) : (
                            <h1 className="text-sm font-semibold">{t('aiAssistant.title')}</h1>
                        )}
                    </header>

                    <div ref={messagesContainerRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
                        {!selectedSessionId && (
                            <div className="text-sm text-muted-foreground">{t('aiAssistant.createSessionHelp')}</div>
                        )}
                        {selectedSessionId && messages.map((message) => (
                            <div key={message.id} className={animatedMessageIds.has(message.id) ? 'ai-message-fade-in' : ''}>
                                {message.role === 'tool' ? (
                                    (() => {
                                        const payload = parseToolPayload(message.content_redacted);
                                        const sources = extractToolSources(payload);
                                        const expanded = expandedToolIds.has(message.id);
                                        const fnName = payload?.tool_name || t('aiAssistant.tool');
                                        return (
                                            <div className="max-w-[94%] rounded-lg border border-slate-500/60 bg-slate-900 text-slate-100">
                                                <button
                                                    type="button"
                                                    onClick={() => toggleToolCard(message.id)}
                                                    className="flex w-full items-center justify-between px-3 py-2 text-left"
                                                >
                                                    <div className="inline-flex items-center gap-2 text-sm font-medium">
                                                        <ChevronRight
                                                            size={14}
                                                            className={`transition-transform ${expanded ? 'rotate-90' : ''}`}
                                                        />
                                                        <Wrench size={13} />
                                                        <span>{fnName}</span>
                                                    </div>
                                                    <div className="text-xs text-slate-300">
                                                        {payload?.status || t('aiAssistant.unknown')} • {payload?.duration_ms ?? '-'} ms
                                                    </div>
                                                </button>

                                                {expanded && (
                                                    <div className="space-y-3 border-t border-slate-600/70 px-3 py-3 text-xs">
                                                        <div>
                                                            <div className="mb-1 font-semibold uppercase tracking-[0.08em] text-slate-300">{t('aiAssistant.input')}</div>
                                                            <pre className="max-h-40 overflow-auto rounded bg-slate-950 px-2 py-1.5 text-[11px] text-slate-100">
                                                                {JSON.stringify(payload?.arguments || {}, null, 2)}
                                                            </pre>
                                                        </div>
                                                        <div>
                                                            <div className="mb-1 font-semibold uppercase tracking-[0.08em] text-slate-300">{t('aiAssistant.output')}</div>
                                                            <pre className="max-h-44 overflow-auto rounded bg-slate-950 px-2 py-1.5 text-[11px] text-slate-100">
                                                                {JSON.stringify(payload?.result_summary || payload?.error_summary || {}, null, 2)}
                                                            </pre>
                                                        </div>
                                                        {sources.length > 0 && (
                                                            <div>
                                                                <div className="mb-1 font-semibold uppercase tracking-[0.08em] text-slate-300">{t('aiAssistant.sources')}</div>
                                                                <div className="space-y-1 text-[11px] text-slate-200">
                                                                    {sources.map((source, index) => (
                                                                        <div key={`${message.id}-source-${index}`}>
                                                                            {source.type}: {source.label}
                                                                            {source.detail ? ` (${source.detail})` : ''}
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            </div>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })()
                                ) : (
                                    <div
                                        className={`max-w-[86%] rounded-lg border px-3 py-2 text-sm ${
                                            message.role === 'user' ? 'ml-auto border-primary/35 bg-primary/10' : 'border-border/70 bg-background/60'
                                        }`}
                                    >
                                        <div className="mb-1 text-[11px] uppercase tracking-[0.08em] text-muted-foreground">{message.role}</div>
                                        {message.isLoadingPlaceholder ? (
                                            <div className="space-y-2 py-1">
                                                <div className="h-2.5 w-40 animate-pulse rounded bg-muted/60" />
                                                <div className="h-2.5 w-32 animate-pulse rounded bg-muted/60" />
                                            </div>
                                        ) : (
                                            <div className="whitespace-pre-wrap">{message.content_redacted}</div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                        <div ref={messageEndRef} />
                    </div>

                    <div className="border-t border-border/70 px-4 py-3">
                        {pendingConfirmation && (
                            <div className="mb-3 rounded-sm border border-border/90 bg-muted/20 p-3">
                                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
                                    <ShieldAlert size={14} />
                                    {t('aiAssistant.confirmationRequired')}
                                </div>
                                <div className="text-xs text-muted-foreground">
                                    {t('aiAssistant.toolLabel')}: <strong>{pendingConfirmation.tool_name}</strong>
                                </div>
                                <pre className="mt-2 max-h-32 overflow-auto rounded-sm bg-muted/45 p-2 text-[11px]">
                                    {JSON.stringify(pendingConfirmation.input_redacted || {}, null, 2)}
                                </pre>
                                <div className="mt-2 flex gap-2">
                                    <button
                                        type="button"
                                        className="btn-minimal-primary text-xs"
                                        onClick={() => confirmationMutation.mutate({
                                            sessionId: selectedSessionId,
                                            confirmationId: pendingConfirmation.id,
                                            approve: true,
                                        })}
                                        disabled={confirmationMutation.isPending}
                                    >
                                        {t('aiAssistant.approve')}
                                    </button>
                                    <button
                                        type="button"
                                        className="btn-minimal text-xs"
                                        onClick={() => confirmationMutation.mutate({
                                            sessionId: selectedSessionId,
                                            confirmationId: pendingConfirmation.id,
                                            approve: false,
                                        })}
                                        disabled={confirmationMutation.isPending}
                                    >
                                        {t('aiAssistant.reject')}
                                    </button>
                                </div>
                            </div>
                        )}

                        <form
                            onSubmit={(event) => {
                                event.preventDefault();
                                submitMessage();
                            }}
                            className="flex items-stretch gap-2"
                        >
                            <textarea
                                value={inputMessage}
                                onChange={(event) => setInputMessage(event.target.value)}
                                onKeyDown={(event) => {
                                    if (event.key === 'Enter' && !event.shiftKey) {
                                        event.preventDefault();
                                        submitMessage();
                                    }
                                }}
                                placeholder={t('aiAssistant.placeholder')}
                                className="input-shell h-12 min-h-12 max-h-12 flex-1 resize-none px-3 py-3 text-sm"
                                disabled={!selectedSessionId || isConfirming}
                            />
                            {isSending ? (
                                <button
                                    type="button"
                                    onClick={stopMessage}
                                    className="btn-minimal-danger h-12 text-xs"
                                >
                                    <Square size={12} />
                                    {t('aiAssistant.stop')}
                                </button>
                            ) : (
                                <button
                                    type="submit"
                                    className="btn-minimal-primary h-12 text-xs disabled:opacity-50"
                                    disabled={!selectedSessionId || isBusy || !inputMessage.trim()}
                                >
                                    <Send size={14} />
                                    {t('aiAssistant.send')}
                                </button>
                            )}
                        </form>
                    </div>
                </section>
            </div>
        </div>
    );
}
