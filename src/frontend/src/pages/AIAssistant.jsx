import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bot, ChevronRight, Loader2, Plus, Send, ShieldAlert, Square, Trash2, Wrench } from 'lucide-react';
import { aiService } from '../services/ai';
import { useToast } from '../contexts/ToastContext';

const DRAFT_SESSION_ID = '__draft__';

function formatDate(value) {
    if (!value) return '';
    try {
        return new Date(value).toLocaleString();
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

export default function AIAssistant() {
    const queryClient = useQueryClient();
    const { showToast } = useToast();
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

    const sessionsQuery = useQuery({
        queryKey: ['ai-sessions'],
        queryFn: () => aiService.listChatSessions(50, 0),
        refetchInterval: (query) => {
            const data = query.state.data || [];
            return data.some((session) => session.title_pending) ? 3000 : false;
        },
        retry: false,
    });

    const messagesQuery = useQuery({
        queryKey: ['ai-messages', selectedSessionId],
        queryFn: () => aiService.listSessionMessages(selectedSessionId, 300),
        enabled: !!selectedSessionId && selectedSessionId !== DRAFT_SESSION_ID,
        retry: false,
    });

    useEffect(() => {
        if (!selectedSessionId && sessionsQuery.data?.length) {
            setSelectedSessionId(sessionsQuery.data[0].id);
        }
    }, [selectedSessionId, sessionsQuery.data]);

    const sessions = useMemo(() => {
        const persisted = sessionsQuery.data || [];
        if (!hasDraftSession) return persisted;
        return [
            {
                id: DRAFT_SESSION_ID,
                title: 'New Session',
                updated_at: null,
                title_pending: false,
            },
            ...persisted,
        ];
    }, [sessionsQuery.data, hasDraftSession]);

    const createSessionMutation = useMutation({
        mutationFn: () => aiService.createChatSession(null),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['ai-sessions'] });
        },
        onError: (error) => {
            showToast(error?.response?.data?.detail || 'Failed to create chat session', 'error');
        },
    });

    const generateTitleMutation = useMutation({
        mutationFn: (sessionId) => aiService.generateSessionTitle(sessionId),
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
            queryClient.invalidateQueries({ queryKey: ['ai-sessions'] });
        },
    });

    const postMessageMutation = useMutation({
        mutationFn: (payload) => aiService.postChatMessage(payload.sessionId, payload.message, { signal: payload.signal }),
        onSuccess: (response, variables) => {
            setPendingConfirmation(response.pending_confirmation || null);
            setOptimisticMessages((prev) => prev.filter((msg) => !msg.isOptimistic));
            if (response.assistant_message) {
                queryClient.setQueryData(['ai-messages', variables.sessionId], (prev) => {
                    const current = Array.isArray(prev) ? [...prev] : [];
                    if (!current.some((item) => item.id === response.assistant_message.id)) {
                        current.push(response.assistant_message);
                    }
                    return current;
                });
            }
            queryClient.invalidateQueries({ queryKey: ['ai-messages', variables.sessionId] });
            queryClient.invalidateQueries({ queryKey: ['ai-sessions'] });
            if (!generatingTitleSessionIds.has(variables.sessionId)) {
                generateTitleMutation.mutate(variables.sessionId);
            }
            if (response.tool_trace?.some((trace) => trace.status === 'failed')) {
                showToast('Some tool calls failed. Check the trace details.', 'warning');
            }
        },
        onError: (error) => {
            if (error?.code === 'ERR_CANCELED') return;
            setOptimisticMessages((prev) => prev.filter((msg) => !msg.isOptimistic));
            showToast(error?.response?.data?.detail || 'Failed to send message', 'error');
        },
        onSettled: () => {
            activeRequestRef.current = null;
        },
    });

    const confirmationMutation = useMutation({
        mutationFn: ({ approve }) => aiService.resolveConfirmation(selectedSessionId, pendingConfirmation.id, approve),
        onSuccess: (response) => {
            setPendingConfirmation(response.pending_confirmation?.status === 'pending' ? response.pending_confirmation : null);
            queryClient.invalidateQueries({ queryKey: ['ai-messages', selectedSessionId] });
            queryClient.invalidateQueries({ queryKey: ['ai-sessions'] });
        },
        onError: (error) => {
            showToast(error?.response?.data?.detail || 'Failed to resolve confirmation', 'error');
        },
    });

    const deleteSessionMutation = useMutation({
        mutationFn: (sessionId) => aiService.deleteChatSession(sessionId),
        onSuccess: (_, sessionId) => {
            queryClient.invalidateQueries({ queryKey: ['ai-sessions'] });
            queryClient.invalidateQueries({ queryKey: ['ai-messages', sessionId] });
            if (selectedSessionId === sessionId) {
                setSelectedSessionId('');
                setPendingConfirmation(null);
                setOptimisticMessages([]);
            }
        },
        onError: (error) => {
            showToast(error?.response?.data?.detail || 'Failed to delete chat session', 'error');
        },
    });

    const isSending = postMessageMutation.isPending;
    const isConfirming = confirmationMutation.isPending;
    const isBusy = isSending || isConfirming;

    useEffect(() => {
        postMessageMutation.reset();
    }, [selectedSessionId, postMessageMutation]);

    useEffect(() => {
        setOptimisticMessages([]);
        setExpandedToolIds(new Set());
    }, [selectedSessionId]);

    const messages = useMemo(() => {
        const persisted = messagesQuery.data || [];
        return [...persisted, ...optimisticMessages];
    }, [messagesQuery.data, optimisticMessages]);

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

            const nowIso = new Date().toISOString();
            const tempId = `temp-user-${Date.now()}`;
            setOptimisticMessages((prev) => [
                ...prev,
                {
                    id: tempId,
                    session_id: targetSessionId,
                    role: 'user',
                    content_redacted: message,
                    created_at: nowIso,
                    isOptimistic: true,
                },
            ]);
            setInputMessage('');
            const controller = new AbortController();
            activeRequestRef.current = controller;

            try {
                await postMessageMutation.mutateAsync({ sessionId: targetSessionId, message, signal: controller.signal });
            } catch {
                if (!createdSessionId) return;
                try {
                    await aiService.deleteChatSession(createdSessionId);
                    queryClient.invalidateQueries({ queryKey: ['ai-sessions'] });
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
        showToast('Response interrupted.', 'info', 2500);
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
        <div className="app-page">
            <div className="page-header">
                <h1 className="page-title">AI Assistant</h1>
                <p className="page-subtitle">Operational chat with tool execution trace and sources.</p>
            </div>

            <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
                <section className="surface-card flex min-h-0 flex-col p-3">
                    <div className="mb-3 flex items-center justify-between">
                        <div className="text-sm font-semibold">Sessions</div>
                        <button
                            type="button"
                            className="ghost-icon-button"
                            onClick={() => {
                                setHasDraftSession(true);
                                setSelectedSessionId(DRAFT_SESSION_ID);
                                setPendingConfirmation(null);
                                setOptimisticMessages([]);
                            }}
                            title="New session"
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
                                        <div className="truncate font-medium">{session.title || 'New Session'}</div>
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
                                        title="Delete session"
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

                <section className="surface-card flex min-h-0 flex-col">
                    <header className="flex h-14 items-center gap-2 border-b border-border/70 px-4">
                        <Bot size={16} className="text-primary" />
                        <h1 className="text-sm font-semibold">AI Assistant</h1>
                    </header>

                    <div ref={messagesContainerRef} className="min-h-0 flex-1 space-y-3 overflow-auto px-4 py-4">
                        {!selectedSessionId && (
                            <div className="text-sm text-muted-foreground">Create a session to start chatting.</div>
                        )}
                        {selectedSessionId && messages.map((message) => (
                            <div key={message.id} className={animatedMessageIds.has(message.id) ? 'ai-message-fade-in' : ''}>
                                {message.role === 'tool' ? (
                                    (() => {
                                        const payload = parseToolPayload(message.content_redacted);
                                        const sources = extractToolSources(payload);
                                        const expanded = expandedToolIds.has(message.id);
                                        const fnName = payload?.tool_name || 'tool';
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
                                                        {payload?.status || 'unknown'} • {payload?.duration_ms ?? '-'} ms
                                                    </div>
                                                </button>

                                                {expanded && (
                                                    <div className="space-y-3 border-t border-slate-600/70 px-3 py-3 text-xs">
                                                        <div>
                                                            <div className="mb-1 font-semibold uppercase tracking-[0.08em] text-slate-300">Input</div>
                                                            <pre className="max-h-40 overflow-auto rounded bg-slate-950 px-2 py-1.5 text-[11px] text-slate-100">
                                                                {JSON.stringify(payload?.arguments || {}, null, 2)}
                                                            </pre>
                                                        </div>
                                                        <div>
                                                            <div className="mb-1 font-semibold uppercase tracking-[0.08em] text-slate-300">Output</div>
                                                            <pre className="max-h-44 overflow-auto rounded bg-slate-950 px-2 py-1.5 text-[11px] text-slate-100">
                                                                {JSON.stringify(payload?.result_summary || payload?.error_summary || {}, null, 2)}
                                                            </pre>
                                                        </div>
                                                        {sources.length > 0 && (
                                                            <div>
                                                                <div className="mb-1 font-semibold uppercase tracking-[0.08em] text-slate-300">Sources</div>
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
                                        <div className="whitespace-pre-wrap">{message.content_redacted}</div>
                                    </div>
                                )}
                            </div>
                        ))}
                        <div ref={messageEndRef} />
                    </div>

                    <div className="border-t border-border/70 px-4 py-3">
                        {pendingConfirmation && (
                            <div className="mb-3 rounded-lg border border-amber-500/35 bg-amber-500/10 p-3">
                                <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-amber-200">
                                    <ShieldAlert size={14} />
                                    Confirmation required
                                </div>
                                <div className="text-xs text-amber-100">
                                    Tool: <strong>{pendingConfirmation.tool_name}</strong>
                                </div>
                                <pre className="mt-2 max-h-32 overflow-auto rounded bg-black/20 p-2 text-[11px]">
                                    {JSON.stringify(pendingConfirmation.input_redacted || {}, null, 2)}
                                </pre>
                                <div className="mt-2 flex gap-2">
                                    <button
                                        type="button"
                                        className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white"
                                        onClick={() => confirmationMutation.mutate({ approve: true })}
                                        disabled={confirmationMutation.isPending}
                                    >
                                        Approve
                                    </button>
                                    <button
                                        type="button"
                                        className="rounded-md bg-zinc-700 px-3 py-1.5 text-xs font-semibold text-white"
                                        onClick={() => confirmationMutation.mutate({ approve: false })}
                                        disabled={confirmationMutation.isPending}
                                    >
                                        Reject
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
                                placeholder="Ask anything about your library and operations..."
                                className="input-shell h-12 min-h-12 max-h-12 flex-1 resize-none px-3 py-3 text-sm"
                                disabled={!selectedSessionId || isConfirming}
                            />
                            {isSending ? (
                                <button
                                    type="button"
                                    onClick={stopMessage}
                                    className="inline-flex h-12 items-center gap-2 rounded-md bg-rose-600 px-3 text-xs font-semibold text-white"
                                >
                                    <Square size={12} />
                                    Stop
                                </button>
                            ) : (
                                <button
                                    type="submit"
                                    className="inline-flex h-12 items-center gap-2 rounded-md bg-primary px-3 text-xs font-semibold text-primary-foreground disabled:opacity-50"
                                    disabled={!selectedSessionId || isBusy || !inputMessage.trim()}
                                >
                                    <Send size={14} />
                                    Send
                                </button>
                            )}
                        </form>
                    </div>
                </section>
            </div>
        </div>
    );
}
