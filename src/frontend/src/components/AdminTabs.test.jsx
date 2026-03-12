import { screen } from '@testing-library/react';

import { renderWithProviders } from '../test/render';
import AdminTabs from './AdminTabs';

describe('AdminTabs', () => {
    it('renders the admin navigation links and marks the active tab', () => {
        renderWithProviders(<AdminTabs />, { route: '/admin/settings' });

        const dashboard = screen.getByRole('link', { name: /dashboard/i });
        const settings = screen.getByRole('link', { name: /settings/i });

        expect(dashboard).toHaveAttribute('href', '/admin/dashboard');
        expect(settings).toHaveAttribute('href', '/admin/settings');
        expect(settings).toHaveClass('bg-background');
        expect(dashboard).toHaveClass('text-muted-foreground');
    });
});
