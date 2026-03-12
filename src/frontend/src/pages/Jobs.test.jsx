import userEvent from '@testing-library/user-event';
import { fireEvent, screen, waitFor } from '@testing-library/react';

const useQueryMock = vi.fn();
const invalidateQueriesMock = vi.fn(() => Promise.resolve());
const setQueryDataMock = vi.fn();
const getJobsMock = vi.fn();
const cancelJobMock = vi.fn();
const createMetadataUndoJobMock = vi.fn();
const deleteJobMock = vi.fn();
const getJobAttemptsMock = vi.fn();
const reprocessJobMock = vi.fn();
const showToastMock = vi.fn();

vi.mock('@tanstack/react-query', async () => {
    const actual = await vi.importActual('@tanstack/react-query');
    return {
        ...actual,
        useQuery: (options) => useQueryMock(options),
        useQueryClient: () => ({
            invalidateQueries: invalidateQueriesMock,
            setQueryData: setQueryDataMock,
        }),
    };
});

vi.mock('../services/jobs', () => ({
    cancelJob: (...args) => cancelJobMock(...args),
    createMetadataUndoJob: (...args) => createMetadataUndoJobMock(...args),
    deleteJob: (...args) => deleteJobMock(...args),
    getJobAttempts: (...args) => getJobAttemptsMock(...args),
    getJobs: (...args) => getJobsMock(...args),
    reprocessJob: (...args) => reprocessJobMock(...args),
}));

vi.mock('../contexts/ToastContext', () => ({
    ToastProvider: ({ children }) => children,
    useToast: () => ({ showToast: showToastMock }),
}));

import { renderWithProviders } from '../test/render';
import Jobs from './Jobs';

const baseJob = {
    id: 'job-1',
    status: 'COMPLETED',
    type: 'sync_items',
    payload: { account_id: 'acc-1' },
    result: { total: 3 },
    metrics: { success: 3, failed: 0, skipped: 0, total: 3 },
    progress_current: 3,
    progress_total: 3,
    progress_percent: 100,
    retry_count: 0,
    max_retries: 3,
    queue_position: null,
    estimated_start_at: null,
    estimated_wait_seconds: null,
    next_retry_at: null,
    dead_lettered_at: null,
    created_at: '2026-03-10T12:00:00Z',
    started_at: '2026-03-10T12:01:00Z',
    completed_at: '2026-03-10T12:02:00Z',
    duration_seconds: 60,
    error: null,
    error_items: [],
};

describe('Jobs page', () => {
    beforeEach(() => {
        invalidateQueriesMock.mockClear();
        setQueryDataMock.mockClear();
        getJobsMock.mockReset();
        cancelJobMock.mockReset();
        createMetadataUndoJobMock.mockReset();
        deleteJobMock.mockReset();
        showToastMock.mockReset();
        getJobAttemptsMock.mockReset();
        reprocessJobMock.mockReset();
        getJobsMock.mockResolvedValue([baseJob]);
        cancelJobMock.mockResolvedValue({ id: 'cancelled' });
        createMetadataUndoJobMock.mockResolvedValue({ id: 'undo-1' });
        deleteJobMock.mockResolvedValue(undefined);
        reprocessJobMock.mockResolvedValue({ id: 'job-retry' });
        useQueryMock.mockReturnValue({
            data: [baseJob],
            isLoading: false,
            isFetching: false,
            error: null,
            refetch: vi.fn(),
        });
    });

    it('renders empty state when there are no jobs', () => {
        useQueryMock.mockReturnValue({
            data: [],
            isLoading: false,
            isFetching: false,
            error: null,
            refetch: vi.fn(),
        });

        renderWithProviders(<Jobs />);

        expect(screen.getByText(/no jobs found/i)).toBeInTheDocument();
        expect(screen.getByText(/try changing the filters/i)).toBeInTheDocument();
    });

    it('renders jobs list and opens details modal', async () => {
        const user = userEvent.setup();
        useQueryMock.mockReturnValue({
            data: [baseJob],
            isLoading: false,
            isFetching: false,
            error: null,
            refetch: vi.fn(),
        });
        getJobAttemptsMock.mockResolvedValueOnce([
            {
                id: 'attempt-1',
                attempt_number: 1,
                status: 'COMPLETED',
                started_at: '2026-03-10T12:01:00Z',
                completed_at: '2026-03-10T12:02:00Z',
                duration_seconds: 60,
                error: null,
            },
        ]);

        const { container } = renderWithProviders(<Jobs />);

        await user.click(container.querySelector('button[title="View Details"]'));

        await waitFor(() => expect(screen.getByText(/attempt history/i)).toBeInTheDocument());
        expect(screen.getByText((text) => text.includes('"account_id": "acc-1"'))).toBeInTheDocument();
        expect(screen.getAllByText((text) => text.includes('"total": 3'))).toHaveLength(2);
    });

    it('shows a toast when query returns an error', async () => {
        useQueryMock.mockReturnValueOnce({
            data: [],
            isLoading: false,
            isFetching: false,
            error: new Error('boom'),
            refetch: vi.fn(),
        });

        renderWithProviders(<Jobs />);

        await waitFor(() => expect(showToastMock).toHaveBeenCalled());
    });

    it('updates filters, resizes columns and exercises pagination query state', async () => {
        const user = userEvent.setup();
        const pagedJobs = Array.from({ length: 50 }, (_, index) => ({
            ...baseJob,
            id: `job-${index}`,
            created_at: `2026-03-10T12:${String(index).padStart(2, '0')}:00Z`,
        }));
        useQueryMock.mockImplementation((options) => {
            void options.queryFn?.({ signal: new AbortController().signal });
            return {
                data: pagedJobs,
                isLoading: false,
                isFetching: false,
                error: null,
                refetch: vi.fn(),
            };
        });

        const { container } = renderWithProviders(<Jobs />);

        const [statusSelect, typeSelect, rangeSelect, pageSizeSelect] = await screen.findAllByRole('combobox');
        await user.selectOptions(statusSelect, 'RUNNING');
        await user.selectOptions(typeSelect, 'sync_items');
        await user.selectOptions(rangeSelect, '24h');
        await user.selectOptions(pageSizeSelect, '25');

        const resizeHandle = container.querySelector('.cursor-col-resize');
        fireEvent.mouseDown(resizeHandle, { clientX: 100 });
        fireEvent.mouseMove(window, { clientX: 140 });
        fireEvent.mouseUp(window);

        await user.click(screen.getByTitle('Next page'));
        await user.click(screen.getByTitle('Previous page'));

        expect(getJobsMock).toHaveBeenCalled();
    }, 15000);

    it('supports bulk and row-level actions for jobs', async () => {
        const user = userEvent.setup();
        const completedJob = {
            ...baseJob,
            id: 'job-completed',
            result: {
                total: 3,
                batch_id: 'batch-12345678',
                error_items: [{ item_id: 'item-1', reason: 'Broken metadata', stage: 'save' }],
            },
        };
        const runningJob = {
            ...baseJob,
            id: 'job-running',
            status: 'RUNNING',
            result: null,
            metrics: { success: 1, failed: 0, skipped: 0, total: 3 },
        };
        const failedJob = {
            ...baseJob,
            id: 'job-failed',
            status: 'FAILED',
            result: { error: 'Pipeline exploded', total: 1 },
            metrics: { success: 0, failed: 1, skipped: 0, total: 1 },
        };
        useQueryMock.mockReturnValue({
            data: [completedJob, runningJob, failedJob],
            isLoading: false,
            isFetching: false,
            error: null,
            refetch: vi.fn(),
        });
        getJobAttemptsMock.mockResolvedValue([
            {
                id: 'attempt-1',
                attempt_number: 1,
                status: 'FAILED',
                started_at: '2026-03-10T12:01:00Z',
                completed_at: '2026-03-10T12:02:00Z',
                duration_seconds: 60,
                error: 'attempt boom',
            },
        ]);

        const { container } = renderWithProviders(<Jobs />);

        await user.click(screen.getByRole('checkbox', { name: /select all on page/i }));
        await user.click(screen.getByRole('checkbox', { name: /job id job-comp/i }));
        await user.click(screen.getByRole('checkbox', { name: /job id job-fail/i }));
        await user.click(screen.getByRole('button', { name: 'Stop selected' }));
        await waitFor(() => expect(cancelJobMock).toHaveBeenCalledWith('job-running'));

        await user.click(screen.getByRole('checkbox', { name: /select all on page/i }));
        await user.click(screen.getByRole('checkbox', { name: /job id job-runn/i }));
        await user.click(screen.getByRole('checkbox', { name: /job id job-fail/i }));
        await user.click(screen.getByRole('button', { name: 'Delete selected' }));
        await waitFor(() => expect(deleteJobMock).toHaveBeenCalledWith('job-completed'));
        expect(showToastMock).toHaveBeenCalledWith('Deleted 1 job(s)', 'success');

        await user.click(container.querySelector('button[title="Undo Batch"]'));
        await waitFor(() => expect(createMetadataUndoJobMock).toHaveBeenCalledWith('batch-12345678'));

        await user.click(container.querySelector('button[title="Cancel job"]'));
        await waitFor(() => expect(cancelJobMock).toHaveBeenCalledWith('job-running'));

        await user.click(container.querySelector('button[title="Reprocess job"]'));
        await waitFor(() => expect(reprocessJobMock).toHaveBeenCalledWith('job-completed'));

        await user.click(container.querySelector('button[title="Delete from history"]'));
        await waitFor(() => expect(deleteJobMock).toHaveBeenCalledWith('job-completed'));

        await user.click(container.querySelector('button[title="View Details"]'));
        expect(await screen.findByText(/item details/i)).toBeInTheDocument();
        expect(screen.getAllByText(/broken metadata/i)).toHaveLength(2);
        await user.click(screen.getByRole('button', { name: 'Close modal' }));
        await waitFor(() => expect(screen.queryByText(/item details/i)).not.toBeInTheDocument());
    }, 15000);
});
