import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const getAccountsMock = vi.fn();
const linkAccountMock = vi.fn();

vi.mock('../services/accounts', () => ({
    accountsService: {
        getAccounts: (...args) => getAccountsMock(...args),
        linkAccount: (...args) => linkAccountMock(...args),
    },
}));

import { renderWithProviders } from '../test/render';
import Dashboard from './Dashboard';

describe('Dashboard', () => {
    it('renders empty state when no accounts are returned', async () => {
        getAccountsMock.mockResolvedValueOnce([]);

        renderWithProviders(<Dashboard />);

        await waitFor(() => expect(screen.getByText(/no accounts linked/i)).toBeInTheDocument());
    });

    it('renders account cards when data loads', async () => {
        getAccountsMock.mockResolvedValueOnce([
            {
                id: 'acc-1',
                provider: 'microsoft',
                display_name: 'Work Drive',
                email: 'work@example.com',
                created_at: '2026-03-10T14:15:00Z',
            },
        ]);

        renderWithProviders(<Dashboard />);

        await waitFor(() => expect(screen.getByText('Work Drive')).toBeInTheDocument());
        expect(screen.getByRole('link', { name: /work drive/i })).toHaveAttribute('href', '/drive/acc-1');
    });

    it('opens the provider picker and links an account', async () => {
        const user = userEvent.setup();
        getAccountsMock.mockResolvedValueOnce([]);

        renderWithProviders(<Dashboard />);

        await waitFor(() => expect(screen.getAllByRole('button', { name: /link account/i }).length).toBeGreaterThan(0));
        await user.click(screen.getAllByRole('button', { name: /link account/i })[0]);
        await user.click(screen.getByRole('button', { name: /onedrive/i }));

        expect(linkAccountMock).toHaveBeenCalledWith('microsoft');
    });
});
