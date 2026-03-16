import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import '../i18n';
import { ToastProvider } from '../contexts/ToastContext';
import { WorkspaceProvider } from '../contexts/WorkspaceContext';

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
                    <ToastProvider>
                        <WorkspaceProvider>{ui}</WorkspaceProvider>
                    </ToastProvider>
                </MemoryRouter>
            </QueryClientProvider>,
        ),
    };
}
