import userEvent from '@testing-library/user-event';
import { screen, waitFor } from '@testing-library/react';

import { renderWithProviders } from '../test/render';

import '../i18n';

const navigateMock = vi.fn();
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
    default: ({ mobileOpen }) => (
        <div>
            <div>{mobileOpen ? 'Sidebar open' : 'Sidebar closed'}</div>
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
