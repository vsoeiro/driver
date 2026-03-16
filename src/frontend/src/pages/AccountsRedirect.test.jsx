import userEvent from '@testing-library/user-event';
import { screen, waitFor } from '@testing-library/react';

const navigateMock = vi.fn();
const createSyncJobMock = vi.fn();
const useAccountsQueryMock = vi.fn();
const useItemsListQueryMock = vi.fn();
const useQuotaQueryMock = vi.fn();
const useJobActivityMock = vi.fn();
const showToastMock = vi.fn();

vi.mock('react-router-dom', async () => {
    const actual = await vi.importActual('react-router-dom');
    return {
        ...actual,
        useNavigate: () => navigateMock,
    };
});

vi.mock('../hooks/useAppQueries', () => ({
    useAccountsQuery: (...args) => useAccountsQueryMock(...args),
    useItemsListQuery: (...args) => useItemsListQueryMock(...args),
    useQuotaQuery: (...args) => useQuotaQueryMock(...args),
}));

vi.mock('../contexts/JobActivityContext', () => ({
    useJobActivity: () => useJobActivityMock(),
}));

vi.mock('../contexts/ToastContext', () => ({
    ToastProvider: ({ children }) => children,
    useToast: () => ({ showToast: showToastMock }),
}));

vi.mock('../services/jobs', () => ({
    jobsService: {
        createSyncJob: (...args) => createSyncJobMock(...args),
    },
}));

vi.mock('../components/ProviderIcon', () => ({
    __esModule: true,
    default: () => <span>Provider</span>,
}));

import { renderWithProviders } from '../test/render';
import AccountsRedirect from './AccountsRedirect';

describe('AccountsRedirect', () => {
    beforeEach(() => {
        navigateMock.mockReset();
        createSyncJobMock.mockReset();
        useAccountsQueryMock.mockReset();
        useItemsListQueryMock.mockReset();
        useQuotaQueryMock.mockReset();
        useJobActivityMock.mockReset();
        showToastMock.mockReset();
        window.localStorage.clear();

        useAccountsQueryMock.mockReturnValue({
            data: [
                { id: 'acc-1', email: 'reader@example.com', display_name: 'Reader', provider: 'microsoft' },
                { id: 'acc-2', email: 'books@example.com', display_name: 'Books', provider: 'google' },
            ],
            isLoading: false,
        });
        useQuotaQueryMock.mockImplementation((accountId) => ({
            data: { used: accountId === 'acc-1' ? 1024 : 2048, total: 4096 },
            isLoading: false,
        }));
        useItemsListQueryMock.mockImplementation((params) => ({
            data: { total: params.account_id === 'acc-1' ? 12 : 4, items: [], total_pages: 1 },
            isLoading: false,
        }));
        useJobActivityMock.mockReturnValue({
            jobs: [
                { id: 'job-1', payload: { account_id: 'acc-1' }, status: 'COMPLETED', type: 'sync_items' },
            ],
            hasActiveJobs: true,
        });
        createSyncJobMock.mockResolvedValue({ id: 'job-sync' });
    });

    it('renders a real accounts hub with cross-workspace entry points', async () => {
        const user = userEvent.setup();
        window.localStorage.setItem('driver-last-account-id', 'acc-1');

        renderWithProviders(<AccountsRedirect />, { route: '/accounts' });

        expect(await screen.findByText('Connected accounts')).toBeInTheDocument();
        expect(screen.getByText('Reader')).toBeInTheDocument();
        expect(screen.getByText('Books')).toBeInTheDocument();
        expect(screen.getByText('Last used')).toBeInTheDocument();
        expect(screen.getAllByText('Files indexed')).toHaveLength(2);
        expect(screen.getByText('12 files')).toBeInTheDocument();
        expect(useItemsListQueryMock.mock.calls.every(([params]) => params.has_metadata === undefined)).toBe(true);

        await user.click(screen.getAllByRole('button', { name: 'Open drive' })[0]);
        expect(navigateMock).toHaveBeenCalledWith('/drive/acc-1');

        await user.click(screen.getAllByRole('button', { name: 'Sync now' })[0]);
        await waitFor(() => expect(createSyncJobMock).toHaveBeenCalledWith('acc-1'));
        expect(showToastMock).toHaveBeenCalledWith('Sync job queued successfully.', 'success');

        await user.click(screen.getByRole('button', { name: 'Open library' }));
        expect(navigateMock).toHaveBeenCalledWith('/all-files');
    });

    it('shows an empty state when there are no linked accounts', async () => {
        useAccountsQueryMock.mockReturnValue({ data: [], isLoading: false });

        renderWithProviders(<AccountsRedirect />, { route: '/accounts' });

        expect(await screen.findByText('No connected accounts')).toBeInTheDocument();
        expect(screen.getByText('Use the link account button in the header to get started.')).toBeInTheDocument();
    });
});
