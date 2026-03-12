import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const useJobActivityMock = vi.fn();
const useObservabilityQueryMock = vi.fn();

vi.mock('../contexts/JobActivityContext', () => ({
    useJobActivity: (...args) => useJobActivityMock(...args),
}));

vi.mock('../hooks/useAppQueries', () => ({
    useObservabilityQuery: (...args) => useObservabilityQueryMock(...args),
}));

import { renderWithProviders } from '../test/render';
import NotificationBell from './NotificationBell';

describe('NotificationBell', () => {
    let dateNowSpy;

    beforeEach(() => {
        window.localStorage.clear();
        dateNowSpy = vi.spyOn(Date, 'now').mockReturnValue(new Date('2026-03-10T12:06:00Z').valueOf());
        useJobActivityMock.mockReset();
        useObservabilityQueryMock.mockReset();
    });

    afterEach(() => {
        dateNowSpy.mockRestore();
    });

    it('merges alerts and completed jobs, then dismisses one or all notifications', async () => {
        const user = userEvent.setup();
        const refetchRecentJobsMock = vi.fn();
        const refetchAlertsMock = vi.fn();

        useJobActivityMock.mockReturnValue({
            jobs: [
                {
                    id: 'job-12345678',
                    type: 'sync_items',
                    status: 'COMPLETED',
                    created_at: '2026-03-10T12:00:00Z',
                    completed_at: '2026-03-10T12:05:00Z',
                },
                {
                    id: 'job-running',
                    type: 'sync_items',
                    status: 'RUNNING',
                    created_at: '2026-03-10T12:05:00Z',
                },
            ],
            refetch: refetchRecentJobsMock,
            canRefresh: true,
        });
        useObservabilityQueryMock.mockReturnValue({
            data: {
                recent_alerts: [
                    {
                        code: 'quota_high',
                        severity: 'warning',
                        message: 'Quota nearly full',
                        created_at: '2026-03-10T12:04:00Z',
                    },
                ],
            },
            isLoading: false,
            refetch: refetchAlertsMock,
        });

        renderWithProviders(<NotificationBell />);

        expect(screen.getByText('2')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /notifications/i }));

        expect(await screen.findByText(/warning - quota_high/i)).toBeInTheDocument();
        expect(screen.getByText(/job sync_items completed/i)).toBeInTheDocument();
        expect(refetchAlertsMock).toHaveBeenCalled();
        expect(refetchRecentJobsMock).toHaveBeenCalled();

        await user.click(screen.getAllByRole('button', { name: /^dismiss$/i })[0]);
        await waitFor(() => expect(screen.getByText('1')).toBeInTheDocument());

        await user.click(screen.getByRole('button', { name: /dismiss all/i }));
        expect(await screen.findByText(/no notifications/i)).toBeInTheDocument();
    });

    it('respects dismissed ids from storage and closes when clicking outside', async () => {
        const alertId = 'alert:quota_high:2026-03-10T12:04:00Z';
        const jobId = 'job:job-12345678:COMPLETED:2026-03-10T12:05:00Z';
        const user = userEvent.setup();

        window.localStorage.setItem('driver-notifications-dismissed-v1', JSON.stringify([alertId, jobId]));
        useJobActivityMock.mockReturnValue({
            jobs: [
                {
                    id: 'job-12345678',
                    type: 'sync_items',
                    status: 'COMPLETED',
                    created_at: '2026-03-10T12:00:00Z',
                    completed_at: '2026-03-10T12:05:00Z',
                },
            ],
            refetch: vi.fn(),
            canRefresh: false,
        });
        useObservabilityQueryMock.mockReturnValue({
            data: {
                recent_alerts: [
                    {
                        code: 'quota_high',
                        severity: 'warning',
                        message: 'Quota nearly full',
                        created_at: '2026-03-10T12:04:00Z',
                    },
                ],
            },
            isLoading: false,
            refetch: vi.fn(),
        });

        renderWithProviders(<NotificationBell />);

        await user.click(screen.getByRole('button', { name: /notifications/i }));
        expect(await screen.findByText(/no notifications/i)).toBeInTheDocument();

        fireEvent.mouseDown(document.body);

        await waitFor(() => {
            expect(screen.queryByText(/no notifications/i)).not.toBeInTheDocument();
        });
    });
});
