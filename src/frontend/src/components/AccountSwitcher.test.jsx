import userEvent from '@testing-library/user-event';
import { screen } from '@testing-library/react';

const useAccountsQueryMock = vi.fn();

vi.mock('../hooks/useAppQueries', () => ({
    useAccountsQuery: (...args) => useAccountsQueryMock(...args),
}));

vi.mock('./ProviderIcon', () => ({
    default: ({ provider }) => <span data-testid={`provider-${provider}`}>{provider}</span>,
}));

import { renderWithProviders } from '../test/render';
import AccountSwitcher from './AccountSwitcher';

describe('AccountSwitcher', () => {
    beforeEach(() => {
        useAccountsQueryMock.mockReset();
        useAccountsQueryMock.mockReturnValue({ data: [] });
    });

    it('renders the placeholder and disables the trigger when there are no accounts', () => {
        renderWithProviders(
            <AccountSwitcher
                selectedAccountId=""
                onSelectAccount={vi.fn()}
                accountLabel="Account"
                placeholderLabel="Select an account"
            />,
        );

        expect(screen.getByText('Account')).toBeInTheDocument();
        expect(screen.getByText('Select an account')).toBeInTheDocument();
        expect(screen.getByRole('button')).toBeDisabled();
    });

    it('shows the selected account and lets the user switch accounts', async () => {
        const user = userEvent.setup();
        const onSelectAccount = vi.fn();
        useAccountsQueryMock.mockReturnValue({
            data: [
                { id: 'acc-1', email: 'reader@example.com', provider: 'onedrive' },
                { id: 'acc-2', email: 'alt@example.com', provider: 'google' },
            ],
        });

        renderWithProviders(
            <AccountSwitcher
                selectedAccountId="acc-1"
                onSelectAccount={onSelectAccount}
                accountLabel="Account"
                placeholderLabel="Select an account"
            />,
        );

        expect(screen.getByText('reader@example.com')).toBeInTheDocument();
        expect(screen.getByTestId('provider-onedrive')).toBeInTheDocument();

        await user.click(screen.getByRole('button'));
        await user.click(await screen.findByText('alt@example.com'));

        expect(onSelectAccount).toHaveBeenCalledWith('acc-2');
    });
});
