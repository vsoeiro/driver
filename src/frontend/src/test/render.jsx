import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import '../i18n';
import { ToastProvider } from '../contexts/ToastContext';

export function createTestQueryClient() {
    return new QueryClient({
        defaultOptions: {
            queries: {
                retry: false,
            },
            mutations: {
                retry: false,
            },
        },
    });
}

export function renderWithProviders(ui, { route = '/', queryClient = createTestQueryClient() } = {}) {
    return {
        queryClient,
        ...render(
            <QueryClientProvider client={queryClient}>
                <MemoryRouter initialEntries={[route]}>
                    <ToastProvider>{ui}</ToastProvider>
                </MemoryRouter>
            </QueryClientProvider>,
        ),
    };
}
