import userEvent from '@testing-library/user-event';
import { screen, waitFor } from '@testing-library/react';

const getAccountsMock = vi.fn();
const getFilesMock = vi.fn();
const getFolderFilesMock = vi.fn();
const createMoveJobMock = vi.fn();
const showToastMock = vi.fn();

vi.mock('../services/accounts', () => ({
    getAccounts: (...args) => getAccountsMock(...args),
}));

vi.mock('../services/drive', () => ({
    getFiles: (...args) => getFilesMock(...args),
    getFolderFiles: (...args) => getFolderFilesMock(...args),
}));

vi.mock('../services/jobs', () => ({
    createMoveJob: (...args) => createMoveJobMock(...args),
}));

vi.mock('../contexts/ToastContext', () => ({
    ToastProvider: ({ children }) => children,
    useToast: () => ({ showToast: showToastMock }),
}));

import { renderWithProviders } from '../test/render';
import MoveModal from './MoveModal';

describe('MoveModal', () => {
    beforeEach(() => {
        getAccountsMock.mockReset();
        getFilesMock.mockReset();
        getFolderFilesMock.mockReset();
        createMoveJobMock.mockReset();
        showToastMock.mockReset();

        getAccountsMock.mockResolvedValue([
            { id: 'acc-1', display_name: 'Reader', email: 'reader@example.com' },
            { id: 'acc-2', display_name: 'Archive', email: 'archive@example.com' },
        ]);
        getFilesMock.mockResolvedValue({
            items: [
                { id: 'folder-1', item_type: 'folder', name: 'Books' },
                { id: 'file-1', item_type: 'file', name: 'cover.png' },
            ],
        });
        getFolderFilesMock.mockResolvedValue({
            items: [{ id: 'folder-2', item_type: 'folder', name: 'Nested' }],
        });
        createMoveJobMock.mockResolvedValue({ id: 'job-1' });
    });

    it('loads accounts, navigates folders and starts a move job', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        const onSuccess = vi.fn();

        renderWithProviders(
            <MoveModal
                isOpen
                onClose={onClose}
                item={{ id: 'item-1', name: 'issue-01.cbz' }}
                sourceAccountId="acc-1"
                onSuccess={onSuccess}
            />,
        );

        expect(await screen.findByText('Books')).toBeInTheDocument();
        expect(screen.getByText('cover.png')).toBeInTheDocument();
        expect(screen.getByText('File')).toBeInTheDocument();

        await user.click(screen.getByText('Books'));
        await waitFor(() => {
            expect(getFolderFilesMock).toHaveBeenCalledWith('acc-1', 'folder-1');
        });
        expect(await screen.findByText('Nested')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /move here/i }));

        await waitFor(() => {
            expect(createMoveJobMock).toHaveBeenCalledWith('acc-1', 'item-1', 'acc-1', 'folder-1');
        });
        expect(showToastMock).toHaveBeenCalledWith('Move job started for issue-01.cbz', 'success');
        expect(onSuccess).toHaveBeenCalledTimes(1);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('resets the folder path when switching destination accounts and can go back to root', async () => {
        const user = userEvent.setup();

        const firstView = renderWithProviders(
            <MoveModal
                isOpen
                onClose={vi.fn()}
                item={{ id: 'item-1', name: 'issue-01.cbz' }}
                sourceAccountId="acc-1"
                onSuccess={vi.fn()}
            />,
        );

        await screen.findByText('Books');
        await user.click(screen.getByText('Books'));
        expect(await screen.findByText('Nested')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /go up/i }));
        expect(await screen.findByText('Books')).toBeInTheDocument();

        await user.selectOptions(screen.getByRole('combobox'), 'acc-2');
        await waitFor(() => {
            expect(getFilesMock).toHaveBeenCalledWith('acc-2');
        });
    });

    it('surfaces account, folder and move errors', async () => {
        const user = userEvent.setup();
        getAccountsMock.mockRejectedValueOnce(new Error('accounts failed'));

        const firstView = renderWithProviders(
            <MoveModal
                isOpen
                onClose={vi.fn()}
                item={{ id: 'item-1', name: 'issue-01.cbz' }}
                sourceAccountId="acc-1"
                onSuccess={vi.fn()}
            />,
        );

        await waitFor(() => {
            expect(showToastMock).toHaveBeenCalledWith('Failed to load accounts', 'error');
        });

        firstView.unmount();
        getAccountsMock.mockResolvedValueOnce([{ id: 'acc-1', display_name: 'Reader', email: 'reader@example.com' }]);
        getFilesMock.mockResolvedValueOnce({ items: [{ item_type: 'folder', name: 'Broken folder' }] });
        showToastMock.mockReset();

        renderWithProviders(
            <MoveModal
                isOpen
                onClose={vi.fn()}
                item={{ id: 'item-1', name: 'issue-01.cbz' }}
                sourceAccountId="acc-1"
                onSuccess={vi.fn()}
            />,
        );

        await user.click(await screen.findByText('Broken folder'));
        expect(showToastMock).toHaveBeenCalledWith('Missing destination folder id', 'error');

        createMoveJobMock.mockRejectedValueOnce(new Error('boom'));
        await user.click(screen.getByRole('button', { name: /move here/i }));
        await waitFor(() => {
            expect(showToastMock).toHaveBeenCalledWith('Failed to start move: boom', 'error');
        });
    });
});
