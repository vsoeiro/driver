import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const useAccountsQueryMock = vi.fn();
const useQuotaQueryMock = vi.fn();

vi.mock('../hooks/useAppQueries', () => ({
    useAccountsQuery: (...args) => useAccountsQueryMock(...args),
    useQuotaQuery: (...args) => useQuotaQueryMock(...args),
}));

import { renderWithProviders } from '../test/render';
import Sidebar from './Sidebar';

describe('Sidebar', () => {
    beforeEach(() => {
        useAccountsQueryMock.mockReset();
        useQuotaQueryMock.mockReset();
        useAccountsQueryMock.mockReturnValue({
            data: [{ id: 'acc-1' }],
        });
    });

    it('renders quota usage for drive routes and closes the mobile drawer', async () => {
        const user = userEvent.setup();
        const onNavigate = vi.fn();

        useQuotaQueryMock.mockReturnValue({
            data: { used: 1024, total: 4096 },
            isLoading: false,
            isError: false,
        });

        renderWithProviders(<Sidebar mobileOpen onNavigate={onNavigate} />, {
            route: '/drive/acc-1',
        });

        expect((await screen.findAllByText(/25% used/i)).length).toBeGreaterThan(0);
        expect(screen.getAllByText('1.00 KB / 4.00 KB').length).toBeGreaterThan(0);

        await user.click(screen.getByRole('button', { name: /close/i }));

        expect(onNavigate).toHaveBeenCalled();
    });

    it('hides the quota card outside account and drive routes', async () => {
        useQuotaQueryMock.mockReturnValue({
            data: null,
            isLoading: false,
            isError: true,
        });

        renderWithProviders(<Sidebar />, {
            route: '/all-files',
        });

        expect((await screen.findAllByRole('link', { name: /files/i })).length).toBeGreaterThan(0);
        expect(screen.queryByText(/25% used/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/quota/i)).not.toBeInTheDocument();
    });
});
