import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const useObservabilityQueryMock = vi.fn();
const getObservabilitySnapshotMock = vi.fn();
const reprocessJobMock = vi.fn();
const showToastMock = vi.fn();

vi.mock('../hooks/useAppQueries', () => ({
    useObservabilityQuery: (...args) => useObservabilityQueryMock(...args),
}));

vi.mock('../services/settings', () => ({
    settingsService: {
        getObservabilitySnapshot: (...args) => getObservabilitySnapshotMock(...args),
    },
}));

vi.mock('../services/jobs', () => ({
    jobsService: {
        reprocessJob: (...args) => reprocessJobMock(...args),
    },
}));

vi.mock('../contexts/ToastContext', () => ({
    ToastProvider: ({ children }) => children,
    useToast: () => ({ showToast: showToastMock }),
}));

vi.mock('../components/AdminTabs', () => ({
    default: () => <div>Admin Tabs</div>,
}));

import { renderWithProviders } from '../test/render';
import AdminDashboard from './AdminDashboard';

function buildSnapshot(overrides = {}) {
    return {
        queue_depth: 12,
        pending_jobs: 5,
        running_jobs: 2,
        retry_scheduled_jobs: 1,
        throughput_last_hour: 7,
        throughput_window: 21,
        avg_duration_seconds_window: 14,
        p95_duration_seconds_window: 30,
        metrics_total_window: 40,
        metrics_success_window: 32,
        metrics_failed_window: 6,
        metrics_skipped_window: 2,
        success_rate_window: 0.8,
        dead_letter_jobs_window: 1,
        generated_at: '2026-03-10T15:00:00Z',
        cache_hit: true,
        cache_ttl_seconds: 25,
        period_label: 'Last 24h',
        provider_request_usage: [
            {
                provider: 'openai',
                provider_label: 'OpenAI',
                utilization_ratio: 0.55,
                requests_in_window: 55,
                max_requests: 100,
                window_seconds: 60,
                total_requests_since_start: 180,
                throttled_responses: 1,
                docs_url: 'https://example.com/openai',
            },
        ],
        integration_health: [
            {
                key: 'jobs',
                label: 'Jobs API',
                detail: 'Healthy',
                status: 'ok',
            },
        ],
        dead_letter_jobs: [
            {
                id: 'job-dead-1',
                type: 'sync_library',
                dead_letter_reason: 'Timeout',
                dead_lettered_at: '2026-03-10T14:00:00Z',
                retry_count: 3,
                max_retries: 5,
            },
        ],
        ...overrides,
    };
}

describe('AdminDashboard page', () => {
    beforeEach(() => {
        useObservabilityQueryMock.mockReset();
        getObservabilitySnapshotMock.mockReset();
        reprocessJobMock.mockReset();
        showToastMock.mockReset();
    });

    it('renders the empty state when no snapshot data is available', async () => {
        useObservabilityQueryMock.mockReturnValue({
            data: null,
            isLoading: false,
            error: null,
        });

        renderWithProviders(<AdminDashboard />);

        expect(await screen.findByText(/no dashboard data available/i)).toBeInTheDocument();
        expect(screen.getByText(/try reloading to fetch a fresh observability snapshot/i)).toBeInTheDocument();
    });

    it('renders observability data, refreshes and reprocesses a dead-letter job', async () => {
        const user = userEvent.setup();
        useObservabilityQueryMock.mockImplementation(({ period }) => ({
            data: buildSnapshot({
                period_label: period === '7d' ? 'Last 7 days' : 'Last 24h',
                throughput_window: period === '7d' ? 70 : 21,
            }),
            isLoading: false,
            error: null,
        }));
        getObservabilitySnapshotMock.mockResolvedValue(buildSnapshot({ queue_depth: 18 }));
        reprocessJobMock.mockResolvedValue({ id: 'job-reprocess-9' });

        renderWithProviders(<AdminDashboard />);

        expect(await screen.findByText(/admin dashboard/i)).toBeInTheDocument();
        expect(screen.getByText(/cache: hit/i)).toBeInTheDocument();
        expect(screen.getByText(/provider api usage/i)).toBeInTheDocument();
        expect(screen.getByRole('link', { name: /docs/i })).toHaveAttribute('href', 'https://example.com/openai');

        await user.selectOptions(screen.getByLabelText(/select period window/i), '7d');
        await waitFor(() => {
            expect(useObservabilityQueryMock).toHaveBeenLastCalledWith(expect.objectContaining({
                period: '7d',
            }));
        });
        expect(screen.getByText(/job metrics \(last 7 days\)/i)).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /reload/i }));
        await waitFor(() => {
            expect(getObservabilitySnapshotMock).toHaveBeenCalledWith({
                period: '7d',
                forceRefresh: true,
            });
        });

        await user.click(screen.getByRole('button', { name: /reprocess/i }));
        await waitFor(() => expect(reprocessJobMock).toHaveBeenCalledWith('job-dead-1'));
        expect(showToastMock).toHaveBeenCalledWith('Reprocess job queued (job-reprocess-9).', 'success');
    });

    it('surfaces snapshot loading errors through toast messages', async () => {
        useObservabilityQueryMock.mockReturnValue({
            data: null,
            isLoading: false,
            error: {
                response: {
                    data: {
                        detail: 'snapshot failed',
                    },
                },
            },
        });

        renderWithProviders(<AdminDashboard />);

        await waitFor(() => {
            expect(showToastMock).toHaveBeenCalledWith('snapshot failed', 'error');
        });
    });
});
