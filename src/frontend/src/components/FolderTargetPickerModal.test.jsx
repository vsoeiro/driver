import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const getAccountsMock = vi.fn();
const getFilesMock = vi.fn();
const getFolderFilesMock = vi.fn();

vi.mock('../services/accounts', () => ({
    accountsService: {
        getAccounts: (...args) => getAccountsMock(...args),
    },
}));

vi.mock('../services/drive', () => ({
    driveService: {
        getFiles: (...args) => getFilesMock(...args),
        getFolderFiles: (...args) => getFolderFilesMock(...args),
    },
}));

import { renderWithProviders } from '../test/render';
import FolderTargetPickerModal from './FolderTargetPickerModal';

describe('FolderTargetPickerModal', () => {
    beforeEach(() => {
        getAccountsMock.mockReset();
        getFilesMock.mockReset();
        getFolderFilesMock.mockReset();

        getAccountsMock.mockResolvedValue([
            { id: 'acc-1', display_name: 'Primary', email: 'primary@example.com' },
            { id: 'acc-2', display_name: 'Archive', email: 'archive@example.com' },
        ]);
        getFilesMock.mockImplementation(async (accountId) => ({
            items: accountId === 'acc-1'
                ? [
                    { id: 'folder-1', name: 'Covers', item_type: 'folder' },
                    { id: 'file-1', name: 'ignore.txt', item_type: 'file' },
                ]
                : [],
        }));
        getFolderFilesMock.mockResolvedValue({
            items: [{ id: 'folder-2', name: 'Variants', item_type: 'folder' }],
        });
    });

    it('does not render when closed', () => {
        renderWithProviders(
            <FolderTargetPickerModal
                isOpen={false}
                initialValue={null}
                onClose={vi.fn()}
                onConfirm={vi.fn()}
            />,
        );

        expect(screen.queryByText(/select target folder/i)).not.toBeInTheDocument();
    });

    it('loads accounts, navigates folders and confirms the selected path', async () => {
        const user = userEvent.setup();
        const onConfirm = vi.fn();

        renderWithProviders(
            <FolderTargetPickerModal
                isOpen
                initialValue={null}
                onClose={vi.fn()}
                onConfirm={onConfirm}
            />,
        );

        expect(await screen.findByText(/select target folder/i)).toBeInTheDocument();
        await waitFor(() => expect(getFilesMock).toHaveBeenCalledWith('acc-1', expect.any(Object)));

        await user.click(await screen.findByRole('button', { name: /covers/i }));
        await waitFor(() => expect(getFolderFilesMock).toHaveBeenCalledWith('acc-1', 'folder-1', expect.any(Object)));

        await user.click(screen.getByRole('button', { name: /use this folder/i }));

        expect(onConfirm).toHaveBeenCalledWith({
            account_id: 'acc-1',
            folder_id: 'folder-1',
            folder_path: 'Root/Covers',
        });
    });

    it('switches accounts and renders the empty state when no folders exist', async () => {
        const user = userEvent.setup();

        renderWithProviders(
            <FolderTargetPickerModal
                isOpen
                initialValue={{ account_id: 'acc-2', folder_id: 'root', folder_path: 'Root' }}
                onClose={vi.fn()}
                onConfirm={vi.fn()}
            />,
        );

        expect(await screen.findByText(/select target folder/i)).toBeInTheDocument();
        await waitFor(() => expect(getFilesMock).toHaveBeenCalledWith('acc-2', expect.any(Object)));
        expect(await screen.findByText(/no folders found/i)).toBeInTheDocument();

        await user.selectOptions(screen.getByRole('combobox'), 'acc-1');
        await waitFor(() => expect(getFilesMock).toHaveBeenCalledWith('acc-1', expect.any(Object)));
        expect(await screen.findByRole('button', { name: /covers/i })).toBeInTheDocument();
    });
});
