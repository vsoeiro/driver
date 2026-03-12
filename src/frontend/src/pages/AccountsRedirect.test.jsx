import { waitFor } from '@testing-library/react';

const navigateMock = vi.fn();
const getAccountsMock = vi.fn();

vi.mock('react-router-dom', async () => {
    const actual = await vi.importActual('react-router-dom');
    return {
        ...actual,
        useNavigate: () => navigateMock,
    };
});

vi.mock('../services/accounts', () => ({
    accountsService: {
        getAccounts: (...args) => getAccountsMock(...args),
    },
}));

import { renderWithProviders } from '../test/render';
import AccountsRedirect from './AccountsRedirect';

describe('AccountsRedirect', () => {
    beforeEach(() => {
        navigateMock.mockReset();
        getAccountsMock.mockReset();
        window.localStorage.clear();
    });

    it('redirects to the saved account when it is still available', async () => {
        window.localStorage.setItem('driver-last-account-id', 'acc-2');
        getAccountsMock.mockResolvedValue([
            { id: 'acc-1' },
            { id: 'acc-2' },
        ]);

        renderWithProviders(<AccountsRedirect />);

        await waitFor(() => {
            expect(navigateMock).toHaveBeenCalledWith('/drive/acc-2', { replace: true });
        });
    });

    it('falls back to the library view when there are no accounts or the request fails', async () => {
        getAccountsMock.mockResolvedValueOnce([]);
        renderWithProviders(<AccountsRedirect />);

        await waitFor(() => {
            expect(navigateMock).toHaveBeenCalledWith('/all-files', { replace: true });
        });

        navigateMock.mockReset();
        getAccountsMock.mockRejectedValueOnce(new Error('boom'));
        renderWithProviders(<AccountsRedirect />);

        await waitFor(() => {
            expect(navigateMock).toHaveBeenCalledWith('/all-files', { replace: true });
        });
    });

    it('does not navigate after the component unmounts', async () => {
        let resolveAccounts;
        getAccountsMock.mockReturnValue(
            new Promise((resolve) => {
                resolveAccounts = resolve;
            }),
        );

        const view = renderWithProviders(<AccountsRedirect />);
        view.unmount();
        resolveAccounts([{ id: 'acc-1' }]);

        await Promise.resolve();
        await Promise.resolve();

        expect(navigateMock).not.toHaveBeenCalled();
    });
});
