import { MemoryRouter, Outlet } from 'react-router-dom';
import { render, screen } from '@testing-library/react';

import './i18n';

vi.mock('./contexts/ToastContext', () => ({
    ToastProvider: ({ children }) => children,
}));

vi.mock('./contexts/JobActivityContext', () => ({
    JobActivityProvider: ({ children }) => children,
}));

vi.mock('./components/Layout', () => ({
    default: () => (
        <div>
            <div>Layout Shell</div>
            <Outlet />
        </div>
    ),
}));

vi.mock('./pages/FileBrowser', () => ({ default: () => <div>File Browser Page</div> }));
vi.mock('./pages/AllFiles', () => ({ default: () => <div>All Files Page</div> }));
vi.mock('./pages/Jobs', () => ({ default: () => <div>Jobs Page</div> }));
vi.mock('./pages/MetadataManager', () => ({ default: () => <div>Metadata Manager Page</div> }));
vi.mock('./pages/RulesManager', () => ({ default: () => <div>Rules Manager Page</div> }));
vi.mock('./pages/AdminSettings', () => ({ default: () => <div>Admin Settings Page</div> }));
vi.mock('./pages/AdminDashboard', () => ({ default: () => <div>Admin Dashboard Page</div> }));
vi.mock('./pages/AccountsRedirect', () => ({ default: () => <div>Accounts Redirect Page</div> }));
vi.mock('./pages/AIAssistant', () => ({ default: () => <div>AI Assistant Page</div> }));

import App from './App';

describe('App', () => {
    it('redirects the root route to the accounts landing page', async () => {
        render(
            <MemoryRouter initialEntries={['/']}>
                <App />
            </MemoryRouter>,
        );

        expect(await screen.findByText('Layout Shell')).toBeInTheDocument();
        expect(await screen.findByText('Accounts Redirect Page')).toBeInTheDocument();
    });

    it('redirects admin root to the dashboard and renders nested pages', async () => {
        render(
            <MemoryRouter initialEntries={['/admin']}>
                <App />
            </MemoryRouter>,
        );

        expect(await screen.findByText('Admin Dashboard Page')).toBeInTheDocument();
    });
});
