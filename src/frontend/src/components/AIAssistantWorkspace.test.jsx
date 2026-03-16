import userEvent from '@testing-library/user-event';
import { screen, waitFor } from '@testing-library/react';

const listChatSessionsMock = vi.fn();
const createChatSessionMock = vi.fn();
const listSessionMessagesMock = vi.fn();
const postChatMessageMock = vi.fn();
const resolveConfirmationMock = vi.fn();
const deleteChatSessionMock = vi.fn();
const generateSessionTitleMock = vi.fn();
const showToastMock = vi.fn();

vi.mock('../services/ai', () => ({
    aiService: {
        listChatSessions: (...args) => listChatSessionsMock(...args),
        createChatSession: (...args) => createChatSessionMock(...args),
        listSessionMessages: (...args) => listSessionMessagesMock(...args),
        postChatMessage: (...args) => postChatMessageMock(...args),
        resolveConfirmation: (...args) => resolveConfirmationMock(...args),
        deleteChatSession: (...args) => deleteChatSessionMock(...args),
        generateSessionTitle: (...args) => generateSessionTitleMock(...args),
    },
}));

vi.mock('../contexts/ToastContext', () => ({
    ToastProvider: ({ children }) => children,
    useToast: () => ({ showToast: showToastMock }),
}));

import { renderWithProviders } from '../test/render';
import AIAssistantWorkspace from './AIAssistantWorkspace';

describe('AIAssistantWorkspace', () => {
    let sessions;
    let messagesBySession;

    beforeEach(() => {
        listChatSessionsMock.mockReset();
        createChatSessionMock.mockReset();
        listSessionMessagesMock.mockReset();
        postChatMessageMock.mockReset();
        resolveConfirmationMock.mockReset();
        deleteChatSessionMock.mockReset();
        generateSessionTitleMock.mockReset();
        showToastMock.mockReset();

        sessions = [];
        messagesBySession = {};

        listChatSessionsMock.mockImplementation(async () => sessions);
        createChatSessionMock.mockImplementation(async () => {
            const created = {
                id: 'sess-1',
                title: 'Session 1',
                updated_at: '2026-03-10T12:00:00Z',
                title_pending: false,
            };
            sessions = [created];
            return created;
        });
        listSessionMessagesMock.mockImplementation(async (sessionId) => messagesBySession[sessionId] || []);
        postChatMessageMock.mockImplementation(async (sessionId) => {
            const response = {
                assistant_message: {
                    id: 'assistant-1',
                    session_id: sessionId,
                    role: 'assistant',
                    content_redacted: 'Done',
                    created_at: '2026-03-10T12:00:00Z',
                },
                pending_confirmation: null,
                tool_trace: [{ status: 'failed' }],
            };
            messagesBySession[sessionId] = [response.assistant_message];
            return response;
        });
        resolveConfirmationMock.mockResolvedValue({ pending_confirmation: null });
        deleteChatSessionMock.mockResolvedValue(undefined);
        generateSessionTitleMock.mockResolvedValue(undefined);
    });

    it('creates a session from draft mode, sends a message and surfaces tool failures', async () => {
        const user = userEvent.setup();
        renderWithProviders(<AIAssistantWorkspace />);

        expect(screen.queryByText('Current context')).not.toBeInTheDocument();
        const composer = await screen.findByPlaceholderText('Type your message...');
        await waitFor(() => expect(composer).not.toBeDisabled());

        await user.type(composer, 'Hello AI');
        await user.click(screen.getByRole('button', { name: 'Send' }));

        await waitFor(() => expect(createChatSessionMock).toHaveBeenCalledWith(null));
        await waitFor(() =>
            expect(postChatMessageMock).toHaveBeenCalledWith(
                'sess-1',
                'Hello AI',
                expect.objectContaining({ signal: expect.any(AbortSignal) }),
            ),
        );
        expect(await screen.findByText('Done')).toBeInTheDocument();
        expect(generateSessionTitleMock).toHaveBeenCalledWith('sess-1');
        expect(showToastMock).toHaveBeenCalledWith('One or more tool calls failed', 'warning');
    });

    it('handles pending confirmations and deletes an existing session', async () => {
        const user = userEvent.setup();
        sessions = [
            {
                id: 'sess-1',
                title: 'Session 1',
                updated_at: '2026-03-10T12:00:00Z',
                title_pending: false,
            },
        ];
        postChatMessageMock.mockImplementation(async () => ({
            assistant_message: null,
            pending_confirmation: {
                id: 'confirm-1',
                status: 'pending',
                tool_name: 'delete_item',
                input_redacted: { path: '/Books' },
            },
            tool_trace: [],
        }));

        renderWithProviders(<AIAssistantWorkspace />);

        expect(await screen.findByText('Session 1')).toBeInTheDocument();
        const composer = await screen.findByPlaceholderText('Type your message...');
        await waitFor(() => expect(composer).not.toBeDisabled());

        await user.type(composer, 'Delete it');
        await user.click(screen.getByRole('button', { name: 'Send' }));

        expect(await screen.findByText('Confirmation required')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Approve' }));
        await waitFor(() => expect(resolveConfirmationMock).toHaveBeenCalledWith('sess-1', 'confirm-1', true));

        await user.click(screen.getByTitle('Delete session'));
        await waitFor(() => expect(deleteChatSessionMock).toHaveBeenCalledWith('sess-1'));
    });

    it('expands tool traces, lists extracted sources and closes compact mode', async () => {
        const user = userEvent.setup();
        const onCompactClose = vi.fn();
        sessions = [
            {
                id: 'sess-1',
                title: 'Session 1',
                updated_at: '2026-03-10T12:00:00Z',
                title_pending: false,
            },
        ];
        messagesBySession = {
            'sess-1': [
                {
                    id: 'tool-1',
                    session_id: 'sess-1',
                    role: 'tool',
                    content_redacted: JSON.stringify({
                        tool_name: 'find_similar_files',
                        status: 'completed',
                        duration_ms: 42,
                        arguments: { query: 'Saga' },
                        result_summary: {
                            accounts: [{ id: 'acc-1', email: 'reader@example.com' }],
                            items: [{ name: 'Comic One.cbz', account_id: 'acc-1', path: '/Comics/Comic One.cbz' }],
                            groups: [{ signature: 'Saga', items: [{ name: 'Comic One.cbz', path: '/Comics/Comic One.cbz' }] }],
                        },
                    }),
                    created_at: '2026-03-10T12:00:00Z',
                },
            ],
        };

        renderWithProviders(<AIAssistantWorkspace compact onCompactClose={onCompactClose} />);

        await user.click(await screen.findByRole('button', { name: /find_similar_files/i }));

        expect(await screen.findByText('Sources')).toBeInTheDocument();
        expect(screen.getByText(/account: reader@example.com \(acc-1\)/i)).toBeInTheDocument();
        expect(screen.getByText(/file: Comic One\.cbz \(acc-1\)/i)).toBeInTheDocument();
        expect(screen.getByText(/group: Saga \(\/Comics\/Comic One\.cbz\)/i)).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: 'Close' }));
        expect(onCompactClose).toHaveBeenCalledTimes(1);
    });

    it('surfaces send failures and cleans up the optimistic draft session', async () => {
        const user = userEvent.setup();
        postChatMessageMock.mockRejectedValueOnce({
            response: { data: { detail: 'Cannot create session' } },
        });

        renderWithProviders(<AIAssistantWorkspace startWithDraft />);

        const composer = await screen.findByPlaceholderText('Type your message...');
        await waitFor(() => expect(composer).not.toBeDisabled());

        await user.type(composer, 'Hello AI');
        await user.click(screen.getByRole('button', { name: 'Send' }));

        await waitFor(() => {
            expect(showToastMock).toHaveBeenCalledWith('Cannot create session', 'error');
        });
        await waitFor(() => expect(deleteChatSessionMock).toHaveBeenCalledWith('sess-1'));
    });

    it('shows confirmation and delete errors, and allows switching back to a draft session', async () => {
        const user = userEvent.setup();
        sessions = [
            {
                id: 'sess-1',
                title: 'Session 1',
                updated_at: '2026-03-10T12:00:00Z',
                title_pending: false,
            },
        ];
        postChatMessageMock.mockResolvedValue({
            assistant_message: null,
            pending_confirmation: {
                id: 'confirm-1',
                status: 'pending',
                tool_name: 'delete_item',
                input_redacted: { path: '/Books' },
            },
            tool_trace: [],
        });
        resolveConfirmationMock.mockRejectedValueOnce({
            response: { data: { detail: 'Cannot reject confirmation' } },
        });
        deleteChatSessionMock.mockRejectedValueOnce({
            response: { data: { detail: 'Cannot delete session' } },
        });

        renderWithProviders(<AIAssistantWorkspace />);

        expect(await screen.findByText('Session 1')).toBeInTheDocument();
        await user.click(screen.getByTitle('New session'));
        expect(screen.getByText('New session')).toBeInTheDocument();

        await user.click(screen.getByText('Session 1'));
        const composer = await screen.findByPlaceholderText('Type your message...');
        await waitFor(() => expect(composer).not.toBeDisabled());

        await user.type(composer, 'Delete it');
        await user.click(screen.getByRole('button', { name: 'Send' }));

        expect(await screen.findByText('Confirmation required')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Reject' }));
        await waitFor(() => expect(resolveConfirmationMock).toHaveBeenCalledWith('sess-1', 'confirm-1', false));
        expect(showToastMock).toHaveBeenCalledWith('Cannot reject confirmation', 'error');

        await user.click(screen.getByTitle('Delete session'));
        await waitFor(() => expect(deleteChatSessionMock).toHaveBeenCalledWith('sess-1'));
        expect(showToastMock).toHaveBeenCalledWith('Cannot delete session', 'error');
    });
});
