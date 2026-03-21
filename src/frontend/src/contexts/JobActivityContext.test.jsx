import { useState } from 'react';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const useQueryMock = vi.fn();
const getJobsMock = vi.fn();

vi.mock('@tanstack/react-query', async () => {
    const actual = await vi.importActual('@tanstack/react-query');
    return {
        ...actual,
        useQuery: (...args) => useQueryMock(...args),
    };
});

vi.mock('../services/jobs', () => ({
    jobsService: {
        getJobs: (...args) => getJobsMock(...args),
    },
}));

import { renderWithProviders } from '../test/render';
import { JobActivityProvider, useJobActivity } from './JobActivityContext';

function Consumer() {
    const { jobs, hasActiveJobs, canRefresh, isLoading, refetch } = useJobActivity();
    const [refetchCount, setRefetchCount] = useState(null);

    return (
        <div>
            <div>jobs:{jobs.length}</div>
            <div>active:{String(hasActiveJobs)}</div>
            <div>loading:{String(isLoading)}</div>
            <div>can-refresh:{String(canRefresh)}</div>
            <button
                type="button"
                onClick={async () => {
                    const rows = await refetch();
                    setRefetchCount(Array.isArray(rows) ? rows.length : -1);
                }}
            >
                Manual refetch
            </button>
            {refetchCount !== null ? <div>refetched:{refetchCount}</div> : null}
        </div>
    );
}

function Host() {
    const [, setVersion] = useState(0);

    return (
        <div>
            <button type="button" onClick={() => setVersion((value) => value + 1)}>
                Force rerender
            </button>
            <JobActivityProvider>
                <Consumer />
            </JobActivityProvider>
        </div>
    );
}

describe('JobActivityContext', () => {
    let currentQueryResult;
    let lastQueryConfig;
    let refetchJobsMock;

    beforeEach(() => {
        getJobsMock.mockReset();
        useQueryMock.mockReset();

        refetchJobsMock = vi.fn().mockResolvedValue({
            data: [{ id: 'job-r', status: 'RUNNING', type: 'sync_items' }],
        });

        currentQueryResult = {
            data: [
                { id: 'job-1', status: 'RUNNING', type: 'move_items' },
                { id: 'job-2', status: 'RUNNING', type: 'sync_items' },
            ],
            isLoading: false,
            refetch: refetchJobsMock,
        };

        useQueryMock.mockImplementation((config) => {
            lastQueryConfig = config;
            return currentQueryResult;
        });
        getJobsMock.mockResolvedValue([]);
    });

    it('tracks active jobs, shows completion and failure notifications, and refreshes on focus', async () => {
        const user = userEvent.setup();
        const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

        renderWithProviders(<Host />, { route: '/accounts/acc-1/drive' });

        expect(screen.getByText('jobs:2')).toBeInTheDocument();
        expect(screen.getByText('active:true')).toBeInTheDocument();
        expect(screen.getByText('can-refresh:true')).toBeInTheDocument();
        expect(lastQueryConfig.enabled).toBe(true);
        expect(
            lastQueryConfig.refetchInterval({
                state: { data: currentQueryResult.data },
            }),
        ).toBe(10000);
        expect(
            lastQueryConfig.refetchInterval({
                state: { data: [{ id: 'idle', status: 'COMPLETED', type: 'move_items' }] },
            }),
        ).toBe(60000);

        await lastQueryConfig.queryFn({ signal: 'abort-signal' });
        expect(getJobsMock).toHaveBeenCalledWith(
            50,
            0,
            [],
            {},
            { includeEstimates: false, signal: 'abort-signal' },
        );

        currentQueryResult = {
            ...currentQueryResult,
            data: [
                { id: 'job-1', status: 'COMPLETED', type: 'move_items' },
                { id: 'job-2', status: 'FAILED', type: 'sync_items' },
            ],
        };
        await user.click(screen.getByRole('button', { name: /force rerender/i }));

        expect(await screen.findByText(/job move items completed successfully!/i)).toBeInTheDocument();
        expect(await screen.findByText(/job sync items failed\./i)).toBeInTheDocument();
        expect(
            dispatchSpy.mock.calls.some(([event]) => event?.type === 'job-completed' && event.detail?.job?.id === 'job-1'),
        ).toBe(true);

        window.dispatchEvent(new Event('focus'));
        await waitFor(() => expect(refetchJobsMock).toHaveBeenCalledTimes(1));

        dispatchSpy.mockRestore();
    });

    it('disables polling controls on the jobs page and returns cached jobs when refetch is requested', async () => {
        const user = userEvent.setup();

        renderWithProviders(<Host />, { route: '/jobs' });

        expect(screen.getByText('can-refresh:false')).toBeInTheDocument();
        expect(lastQueryConfig.enabled).toBe(false);
        expect(lastQueryConfig.refetchInterval({ state: { data: currentQueryResult.data } })).toBe(false);

        await user.click(screen.getByRole('button', { name: /manual refetch/i }));

        expect(screen.getByText('refetched:2')).toBeInTheDocument();
        expect(refetchJobsMock).not.toHaveBeenCalled();
    });
});
