import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const createComicReaderSessionMock = vi.fn();
const getComicReaderPageUrlMock = vi.fn();
const driveActionsMock = {
    createComicReaderSession: (...args) => createComicReaderSessionMock(...args),
    getComicReaderPageUrl: (...args) => getComicReaderPageUrlMock(...args),
};

vi.mock('./Modal', () => ({
    default: ({ isOpen, title, children }) => (
        isOpen ? (
            <div>
                <div>{title}</div>
                {children}
            </div>
        ) : null
    ),
}));

vi.mock('../features/drive/hooks/useDriveData', () => ({
    useDriveActions: () => driveActionsMock,
}));

import { renderWithProviders } from '../test/render';
import ComicReaderModal from './ComicReaderModal';

describe('ComicReaderModal', () => {
    beforeEach(() => {
        createComicReaderSessionMock.mockReset();
        getComicReaderPageUrlMock.mockReset();
        const fetchMock = vi.fn();
        window.fetch = fetchMock;
        global.fetch = fetchMock;
        let blobIndex = 0;
        window.URL.createObjectURL.mockImplementation(() => `blob:page-${blobIndex++}`);
        window.URL.revokeObjectURL.mockImplementation(() => {});
    });

    it('loads the session, renders cover first and advances to the next spread', async () => {
        const user = userEvent.setup();
        createComicReaderSessionMock.mockResolvedValue({
            session_id: 'session-1',
            item_id: 'item-1',
            item_name: 'Saga.cbz',
            extension: 'cbz',
            page_count: 3,
            pages: [
                { index: 0, width: 800, height: 1200 },
                { index: 1, width: 810, height: 1210 },
                { index: 2, width: 820, height: 1220 },
            ],
            expires_at: '2026-03-22T12:00:00Z',
            cache_hit: false,
        });
        getComicReaderPageUrlMock.mockImplementation((_accountId, sessionId, pageIndex) => `/reader/${sessionId}/${pageIndex}`);
        window.fetch
            .mockResolvedValueOnce(new Response(new Blob(['page-0']), { status: 200 }))
            .mockResolvedValueOnce(new Response(new Blob(['page-1']), { status: 200 }))
            .mockResolvedValueOnce(new Response(new Blob(['page-2']), { status: 200 }));

        renderWithProviders(
            <ComicReaderModal
                isOpen
                onClose={vi.fn()}
                accountId="acc-1"
                itemId="item-1"
                filename="Saga.cbz"
            />,
        );

        expect(await screen.findByText('Book mode')).toBeInTheDocument();
        await waitFor(() => expect(screen.getByText('Pages 1 of 3')).toBeInTheDocument());

        await user.click(screen.getByRole('button', { name: /next/i }));
        await waitFor(() => expect(screen.getByText('Pages 2-3 of 3')).toBeInTheDocument());
        expect(window.fetch).toHaveBeenCalledWith('/reader/session-1/0', { credentials: 'same-origin' });
        expect(window.fetch).toHaveBeenCalledWith('/reader/session-1/1', { credentials: 'same-origin' });
        expect(window.fetch).toHaveBeenCalledWith('/reader/session-1/2', { credentials: 'same-origin' });
    });

    it('recreates the session once when a page fetch returns 404', async () => {
        createComicReaderSessionMock
            .mockResolvedValueOnce({
                session_id: 'session-expired',
                item_id: 'item-1',
                item_name: 'Saga.cbz',
                extension: 'cbz',
                page_count: 1,
                pages: [{ index: 0, width: 800, height: 1200 }],
                expires_at: '2026-03-22T12:00:00Z',
                cache_hit: false,
            })
            .mockResolvedValueOnce({
                session_id: 'session-fresh',
                item_id: 'item-1',
                item_name: 'Saga.cbz',
                extension: 'cbz',
                page_count: 1,
                pages: [{ index: 0, width: 800, height: 1200 }],
                expires_at: '2026-03-22T12:05:00Z',
                cache_hit: false,
            });
        getComicReaderPageUrlMock.mockImplementation((_accountId, sessionId, pageIndex) => `/reader/${sessionId}/${pageIndex}`);
        window.fetch
            .mockResolvedValueOnce(new Response(null, { status: 404 }))
            .mockResolvedValueOnce(new Response(new Blob(['page-0']), { status: 200 }));

        renderWithProviders(
            <ComicReaderModal
                isOpen
                onClose={vi.fn()}
                accountId="acc-1"
                itemId="item-1"
                filename="Saga.cbz"
            />,
        );

        await waitFor(() => expect(createComicReaderSessionMock).toHaveBeenCalledTimes(2));
        await waitFor(() => expect(window.fetch).toHaveBeenLastCalledWith('/reader/session-fresh/0', { credentials: 'same-origin' }));
    });
});
