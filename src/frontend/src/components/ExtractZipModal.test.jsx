import userEvent from '@testing-library/user-event';
import { screen, waitFor } from '@testing-library/react';

const getAccountsMock = vi.fn();
const getFilesMock = vi.fn();
const getFolderFilesMock = vi.fn();
const getPathMock = vi.fn();

vi.mock('../services/accounts', () => ({
    accountsService: {
        getAccounts: (...args) => getAccountsMock(...args),
    },
}));

vi.mock('../services/drive', () => ({
    driveService: {
        getFiles: (...args) => getFilesMock(...args),
        getFolderFiles: (...args) => getFolderFilesMock(...args),
        getPath: (...args) => getPathMock(...args),
    },
}));

import { renderWithProviders } from '../test/render';
import ExtractZipModal from './ExtractZipModal';

describe('ExtractZipModal', () => {
    beforeEach(() => {
        getAccountsMock.mockReset();
        getFilesMock.mockReset();
        getFolderFilesMock.mockReset();
        getPathMock.mockReset();

        getAccountsMock.mockResolvedValue([
            { id: 'acc-1', display_name: 'Primary', email: 'primary@example.com' },
            { id: 'acc-2', display_name: 'Archive', email: 'archive@example.com' },
        ]);
        getFilesMock.mockImplementation(async (accountId) => ({
            items: accountId === 'acc-1'
                ? [{ id: 'folder-1', name: 'Covers', item_type: 'folder' }]
                : [{ id: 'folder-2', name: 'Archive', item_type: 'folder' }],
        }));
        getFolderFilesMock.mockResolvedValue({
            items: [{ id: 'folder-3', name: 'Nested', item_type: 'folder' }],
        });
        getPathMock.mockResolvedValue({
            breadcrumb: [
                { id: 'root', name: 'Root' },
                { id: 'folder-2', name: 'Archive' },
            ],
        });
    });

    it('loads the inline folder picker and confirms the selected destination', async () => {
        const user = userEvent.setup();
        const onConfirm = vi.fn();

        renderWithProviders(
            <ExtractZipModal
                isOpen
                onClose={vi.fn()}
                onConfirm={onConfirm}
                selectedItems={[
                    { account_id: 'acc-1', item_id: 'zip-1', name: 'bundle.zip' },
                ]}
            />,
        );

        expect(await screen.findByText('Extract ZIP')).toBeInTheDocument();
        expect(screen.getByText('1 ZIP file(s) selected')).toBeInTheDocument();
        await waitFor(() => expect(getFilesMock).toHaveBeenCalledWith('acc-1', expect.any(Object)));

        await user.click(screen.getByRole('button', { name: /covers/i }));
        await waitFor(() => expect(getFolderFilesMock).toHaveBeenCalledWith('acc-1', 'folder-1', expect.any(Object)));

        await user.click(screen.getByRole('checkbox'));
        await user.click(screen.getByRole('button', { name: /queue extraction/i }));

        expect(onConfirm).toHaveBeenCalledWith({
            target: {
                account_id: 'acc-1',
                folder_id: 'folder-1',
                folder_path: 'Root/Covers',
            },
            deleteSourceAfterExtract: true,
        });
    });

    it('restores the initial destination and switches accounts inline', async () => {
        const user = userEvent.setup();

        renderWithProviders(
            <ExtractZipModal
                isOpen
                onClose={vi.fn()}
                onConfirm={vi.fn()}
                selectedItems={[
                    { account_id: 'acc-1', item_id: 'zip-1', name: 'bundle.zip' },
                ]}
                initialTarget={{ account_id: 'acc-2', folder_id: 'folder-2', folder_path: 'Root/Archive' }}
            />,
        );

        await waitFor(() => expect(getPathMock).toHaveBeenCalledWith('acc-2', 'folder-2', expect.any(Object)));
        expect(await screen.findByText('Root/Archive')).toBeInTheDocument();

        await user.selectOptions(screen.getByRole('combobox'), 'acc-1');
        await waitFor(() => expect(getFilesMock).toHaveBeenCalledWith('acc-1', expect.any(Object)));
        expect(screen.getAllByText('Root').length).toBeGreaterThan(0);
    });
});
