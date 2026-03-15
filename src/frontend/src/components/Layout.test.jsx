import userEvent from '@testing-library/user-event';
import { screen, waitFor } from '@testing-library/react';

import { renderWithProviders } from '../test/render';

import '../i18n';

const navigateMock = vi.fn();
const useAccountsQueryMock = vi.fn();
const useQuotaQueryMock = vi.fn();
let currentPathname = '/drive/acc-1';

vi.mock('react-router-dom', async () => {
    const actual = await vi.importActual('react-router-dom');
    return {
        ...actual,
        Outlet: () => <div>Outlet Content</div>,
        useLocation: () => ({ pathname: currentPathname }),
        useNavigate: () => navigateMock,
    };
});

vi.mock('../hooks/useAppQueries', () => ({
    useAccountsQuery: (...args) => useAccountsQueryMock(...args),
    useQuotaQuery: (...args) => useQuotaQueryMock(...args),
}));

vi.mock('./AccountSwitcher', () => ({
    __esModule: true,
    default: ({ selectedAccountId, onSelectAccount }) => (
        <button type="button" onClick={() => onSelectAccount('acc-2')}>
            Account switcher {selectedAccountId}
        </button>
    ),
}));

vi.mock('./Sidebar', () => ({
    __esModule: true,
    default: ({ mobileOpen, desktopCollapsed }) => (
        <div>
            <div>{mobileOpen ? 'Sidebar open' : 'Sidebar closed'}</div>
            <div>{desktopCollapsed ? 'Desktop collapsed' : 'Desktop expanded'}</div>
        </div>
    ),
}));

vi.mock('./NotificationBell', () => ({
    __esModule: true,
    default: () => <div>Notification Bell</div>,
}));

vi.mock('./ProviderPickerModal', () => ({
    __esModule: true,
    default: ({ isOpen, onClose }) => (isOpen ? <button onClick={onClose}>Close provider picker</button> : null),
}));

vi.mock('./AIAssistantWorkspace', () => ({
    __esModule: true,
    default: ({ onCompactClose }) => (
        <div>
            Quick AI Workspace
            <button onClick={onCompactClose}>Dismiss AI</button>
        </div>
    ),
}));

import Layout from './Layout';

describe('Layout', () => {
    beforeEach(() => {
        currentPathname = '/drive/acc-1';
        navigateMock.mockReset();
        useAccountsQueryMock.mockReset();
        useQuotaQueryMock.mockReset();
        useAccountsQueryMock.mockReturnValue({ data: [{ id: 'acc-1' }] });
        useQuotaQueryMock.mockReturnValue({
            data: { used: 1024, total: 4096 },
            isLoading: false,
            isError: false,
        });
        window.localStorage.clear();
        window.requestIdleCallback = vi.fn(() => 1);
        window.cancelIdleCallback = vi.fn();
    });

    it('renders the drive shell, opens lazy overlays and persists the selected account', async () => {
        const user = userEvent.setup();
        renderWithProviders(<Layout />);

        expect(await screen.findByText('Account switcher acc-1')).toBeInTheDocument();
        expect(window.localStorage.getItem('driver-last-account-id')).toBe('acc-1');

        await user.click(screen.getByText('Account switcher acc-1'));
        expect(navigateMock).toHaveBeenCalledWith('/drive/acc-2');

        await user.click(screen.getByRole('button', { name: 'Link Account' }));
        expect(await screen.findByText('Close provider picker')).toBeInTheDocument();
        await user.click(screen.getByText('Close provider picker'));
        await waitFor(() => expect(screen.queryByText('Close provider picker')).not.toBeInTheDocument());

        await user.click(screen.getByRole('button', { name: 'Settings' }));
        expect(navigateMock).toHaveBeenCalledWith('/admin/settings');

        await user.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
        await waitFor(() => expect(screen.getByRole('button', { name: 'Expand sidebar' })).toBeInTheDocument());
        expect(window.localStorage.getItem('driver-sidebar-collapsed-v1')).toBe('1');

        await user.click(screen.getByRole('button', { name: 'Expand sidebar' }));
        await waitFor(() => expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeInTheDocument());
        expect(window.localStorage.getItem('driver-sidebar-collapsed-v1')).toBe('0');

        await user.click(screen.getByRole('button', { name: 'AI (Experimental)' }));
        expect(await screen.findByText('Quick AI Workspace')).toBeInTheDocument();
        await user.click(screen.getByText('Dismiss AI'));
        await waitFor(() => expect(screen.queryByText('Quick AI Workspace')).not.toBeInTheDocument());
    });

    it('hides the quick AI launcher on the dedicated AI route', () => {
        currentPathname = '/ai';

        renderWithProviders(<Layout />);

        expect(screen.queryByRole('button', { name: 'AI (Experimental)' })).not.toBeInTheDocument();
        expect(screen.queryByText(/account switcher/i)).not.toBeInTheDocument();
    });
});
