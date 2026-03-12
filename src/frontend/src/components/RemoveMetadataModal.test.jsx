import userEvent from '@testing-library/user-event';
import { screen, waitFor } from '@testing-library/react';

const batchDeleteMetadataMock = vi.fn();
const removeMetadataRecursiveMock = vi.fn();

vi.mock('../services/metadata', () => ({
    metadataService: {
        batchDeleteMetadata: (...args) => batchDeleteMetadataMock(...args),
    },
}));

vi.mock('../services/jobs', () => ({
    jobsService: {
        removeMetadataRecursive: (...args) => removeMetadataRecursiveMock(...args),
    },
}));

import { renderWithProviders } from '../test/render';
import RemoveMetadataModal from './RemoveMetadataModal';

describe('RemoveMetadataModal', () => {
    beforeEach(() => {
        batchDeleteMetadataMock.mockReset();
        removeMetadataRecursiveMock.mockReset();
        batchDeleteMetadataMock.mockResolvedValue(undefined);
        removeMetadataRecursiveMock.mockResolvedValue({ id: 'job-1' });
    });

    it('shows the empty state when there is nothing to remove', () => {
        renderWithProviders(
            <RemoveMetadataModal
                isOpen
                onClose={vi.fn()}
                selectedItems={[]}
                onSuccess={vi.fn()}
                showToast={vi.fn()}
            />,
        );

        expect(screen.getByText(/no selected items have metadata to remove/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /remove metadata/i })).toBeDisabled();
    });

    it('removes direct metadata and queues recursive folder jobs', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        const onSuccess = vi.fn();
        const showToast = vi.fn();

        renderWithProviders(
            <RemoveMetadataModal
                isOpen
                onClose={onClose}
                onSuccess={onSuccess}
                showToast={showToast}
                selectedItems={[
                    {
                        id: 'row-file-1',
                        item_id: 'file-1',
                        account_id: 'acc-1',
                        item_type: 'file',
                        name: 'issue-01.cbz',
                        metadata: { category_name: 'Comics' },
                    },
                    {
                        id: 'row-folder-1',
                        item_id: 'folder-1',
                        account_id: 'acc-1',
                        item_type: 'folder',
                        name: 'Books',
                        path: '/Books',
                        metadata: { category_name: 'Comics' },
                    },
                    {
                        id: 'row-folder-2',
                        item_id: 'folder-2',
                        account_id: 'acc-2',
                        item_type: 'folder',
                        name: 'Photos',
                        path: '/Photos',
                        metadata: null,
                    },
                ]}
            />,
        );

        expect(screen.getByText(/files with metadata \(1\)/i)).toBeInTheDocument();
        expect(screen.getByText(/2 folder\(s\) selected/i)).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /remove metadata/i }));

        await waitFor(() => {
            expect(batchDeleteMetadataMock).toHaveBeenCalledWith('acc-1', ['file-1', 'folder-1']);
        });
        expect(removeMetadataRecursiveMock).toHaveBeenCalledWith('acc-1', '/Books');
        expect(removeMetadataRecursiveMock).toHaveBeenCalledWith('acc-2', '/Photos');
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining('2 item(s) cleared'), 'success');
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining('2 folder job(s) queued'), 'success');
        expect(onSuccess).toHaveBeenCalledTimes(1);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('surfaces failures while removing metadata', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        const onSuccess = vi.fn();
        const showToast = vi.fn();
        batchDeleteMetadataMock.mockRejectedValue(new Error('boom'));

        renderWithProviders(
            <RemoveMetadataModal
                isOpen
                onClose={onClose}
                onSuccess={onSuccess}
                showToast={showToast}
                selectedItems={[
                    {
                        id: 'row-file-1',
                        item_id: 'file-1',
                        account_id: 'acc-1',
                        item_type: 'file',
                        name: 'issue-01.cbz',
                        metadata: { category_name: 'Comics' },
                    },
                ]}
            />,
        );

        await user.click(screen.getByRole('button', { name: /remove metadata/i }));

        await waitFor(() => {
            expect(showToast).toHaveBeenCalledWith('Failed to remove metadata: boom', 'error');
        });
        expect(onSuccess).not.toHaveBeenCalled();
        expect(onClose).not.toHaveBeenCalled();
    });
});
