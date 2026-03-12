import userEvent from '@testing-library/user-event';

vi.mock('../services/accounts', () => ({
    accountsService: {
        linkAccount: vi.fn(),
    },
}));

import { screen } from '@testing-library/react';

import { accountsService } from '../services/accounts';
import { renderWithProviders } from '../test/render';
import ProviderPickerModal from './ProviderPickerModal';

describe('ProviderPickerModal', () => {
    it('does not render when closed', () => {
        renderWithProviders(<ProviderPickerModal isOpen={false} onClose={vi.fn()} />);

        expect(screen.queryByText('OneDrive')).not.toBeInTheDocument();
    });

    it('calls onSelect when provided', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        const onSelect = vi.fn();

        renderWithProviders(<ProviderPickerModal isOpen onClose={onClose} onSelect={onSelect} />);

        await user.click(screen.getByRole('button', { name: /google drive/i }));

        expect(onClose).toHaveBeenCalled();
        expect(onSelect).toHaveBeenCalledWith('google');
        expect(accountsService.linkAccount).not.toHaveBeenCalled();
    });

    it('links account directly when onSelect is absent', async () => {
        const user = userEvent.setup();

        renderWithProviders(<ProviderPickerModal isOpen onClose={vi.fn()} />);

        await user.click(screen.getByRole('button', { name: /dropbox/i }));

        expect(accountsService.linkAccount).toHaveBeenCalledWith('dropbox');
    });
});
