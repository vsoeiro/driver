import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const getSimilarReportMock = vi.fn();
const batchDeleteItemsMock = vi.fn();
const createRemoveDuplicatesJobMock = vi.fn();

vi.mock('../services/items', () => ({
    itemsService: {
        getSimilarReport: (...args) => getSimilarReportMock(...args),
    },
}));

vi.mock('../services/drive', () => ({
    driveService: {
        batchDeleteItems: (...args) => batchDeleteItemsMock(...args),
    },
}));

vi.mock('../services/jobs', () => ({
    jobsService: {
        createRemoveDuplicatesJob: (...args) => createRemoveDuplicatesJobMock(...args),
    },
}));

import { renderWithProviders } from '../test/render';
import SimilarFilesReportTab from './SimilarFilesReportTab';

const ACCOUNTS = [
    { id: 'acc-1', email: 'primary@example.com', display_name: 'Primary' },
    { id: 'acc-2', email: 'archive@example.com', display_name: 'Archive' },
];

function buildReport(overrides = {}) {
    return {
        groups: [
            {
                name: 'Issue 001',
                match_type: 'with_extension',
                size: 2048,
                total_items: 3,
                total_accounts: 2,
                potential_savings_bytes: 1024,
                priority_level: 'high',
                has_same_account_matches: true,
                has_cross_account_matches: true,
                low_priority_reasons: [],
                extensions: ['cbz'],
                items: [
                    {
                        account_id: 'acc-1',
                        item_id: 'item-1',
                        extension: 'cbz',
                        size: 2048,
                        path: '/Series/Issue 001.cbz',
                    },
                    {
                        account_id: 'acc-2',
                        item_id: 'item-2',
                        extension: 'cbz',
                        size: 2048,
                        path: '/Archive/Issue 001.cbz',
                    },
                    {
                        account_id: 'acc-1',
                        item_id: 'item-3',
                        extension: 'cbz',
                        size: 2048,
                        path: '/Series/Copies/Issue 001.cbz',
                    },
                ],
                ...overrides.group,
            },
        ],
        total_groups: 1,
        total_items: 3,
        total_pages: 1,
        collapsed_records: 1,
        potential_savings_bytes: 1024,
        ...overrides,
    };
}

describe('SimilarFilesReportTab', () => {
    beforeEach(() => {
        getSimilarReportMock.mockReset();
        batchDeleteItemsMock.mockReset();
        createRemoveDuplicatesJobMock.mockReset();

        getSimilarReportMock.mockResolvedValue(buildReport());
        batchDeleteItemsMock.mockResolvedValue(undefined);
        createRemoveDuplicatesJobMock.mockResolvedValue({ id: 'job-12345678' });
    });

    it('loads the report, deletes selected duplicates, and creates a remove-duplicates job', async () => {
        const user = userEvent.setup();

        renderWithProviders(<SimilarFilesReportTab accounts={ACCOUNTS} />);

        expect(await screen.findByText('Issue 001')).toBeInTheDocument();
        expect(getSimilarReportMock).toHaveBeenCalledWith(expect.objectContaining({
            page: 1,
            page_size: 20,
            scope: 'all',
            account_id: '',
            sort_by: 'size',
            sort_order: 'desc',
            extensions: [],
            hide_low_priority: true,
        }), expect.any(Object));

        const table = screen.getByRole('table');
        const checkboxButtons = within(table).getAllByRole('button');
        await user.click(checkboxButtons[0]);
        expect(screen.getByText('2 selected')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /^delete selected$/i }));
        expect(await screen.findByText(/delete 2 selected duplicate file/i)).toBeInTheDocument();
        const confirmButtons = await screen.findAllByRole('button', { name: /^delete selected$/i });
        await user.click(confirmButtons[confirmButtons.length - 1]);

        await waitFor(() => expect(batchDeleteItemsMock).toHaveBeenCalledTimes(2));
        expect(batchDeleteItemsMock).toHaveBeenNthCalledWith(1, 'acc-2', ['item-2']);
        expect(batchDeleteItemsMock).toHaveBeenNthCalledWith(2, 'acc-1', ['item-3']);
        expect(await screen.findByText(/2 file\(s\) deleted/i)).toBeInTheDocument();
        await waitFor(() => expect(getSimilarReportMock).toHaveBeenCalledTimes(2));

        await user.click(screen.getByRole('button', { name: /create remove-duplicates job/i }));
        expect(await screen.findByText(/create a background job to remove duplicates/i)).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /^create job$/i }));

        await waitFor(() => {
            expect(createRemoveDuplicatesJobMock).toHaveBeenCalledWith({
                preferred_account_id: 'acc-1',
                account_id: null,
                scope: 'all',
                extensions: [],
                hide_low_priority: true,
            });
        });
        expect(await screen.findByText(/remove-duplicates job created \(job-1234\)/i)).toBeInTheDocument();
    });

    it('blocks unsafe deletions and surfaces job creation failures', async () => {
        const user = userEvent.setup();
        createRemoveDuplicatesJobMock.mockRejectedValueOnce({
            response: { data: { detail: 'backend exploded' } },
        });

        renderWithProviders(<SimilarFilesReportTab accounts={ACCOUNTS} />);

        expect(await screen.findByText('Issue 001')).toBeInTheDocument();

        const table = screen.getByRole('table');
        const checkboxButtons = within(table).getAllByRole('button');
        await user.click(checkboxButtons[1]);
        await user.click(checkboxButtons[2]);
        await user.click(checkboxButtons[3]);
        await user.click(screen.getByRole('button', { name: /^delete selected$/i }));

        expect(
            await screen.findByText(/safety rule: at least one file must remain in each duplicate group\./i),
        ).toBeInTheDocument();
        expect(screen.queryByRole('dialog', { name: /delete selected/i })).not.toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /create remove-duplicates job/i }));
        await user.click(screen.getByRole('button', { name: /^create job$/i }));

        expect(await screen.findByText('backend exploded')).toBeInTheDocument();
    });

    it('renders error and empty states from the report query', async () => {
        getSimilarReportMock.mockReset();
        getSimilarReportMock.mockRejectedValueOnce(new Error('boom'));

        const view = renderWithProviders(<SimilarFilesReportTab accounts={ACCOUNTS} />);

        expect(await screen.findByText(/failed to load similar files report/i)).toBeInTheDocument();

        view.unmount();
        getSimilarReportMock.mockReset();
        getSimilarReportMock.mockResolvedValueOnce(buildReport({ groups: [], total_groups: 0, total_items: 0 }));
        renderWithProviders(<SimilarFilesReportTab accounts={ACCOUNTS} />);

        expect(await screen.findByText(/no similar groups found/i)).toBeInTheDocument();
    });

    it('updates filters, refreshes results and paginates through the report', async () => {
        const user = userEvent.setup();
        getSimilarReportMock.mockResolvedValue(buildReport({ total_pages: 2 }));

        renderWithProviders(<SimilarFilesReportTab accounts={ACCOUNTS} />);

        expect(await screen.findByText('Issue 001')).toBeInTheDocument();

        const [scopeSelect, sortBySelect, accountSelect] = screen.getAllByRole('combobox').slice(0, 3);
        await user.selectOptions(scopeSelect, 'same_account');
        await user.selectOptions(sortBySelect, 'name');
        await user.click(screen.getByRole('button', { name: /sort order/i }));
        await user.selectOptions(accountSelect, 'acc-2');
        await user.clear(screen.getByPlaceholderText(/extensions/i));
        await user.type(screen.getByPlaceholderText(/extensions/i), 'cbz, pdf');
        await user.click(screen.getByRole('checkbox', { name: /hide low priority/i }));

        await waitFor(() => {
            expect(getSimilarReportMock).toHaveBeenLastCalledWith(expect.objectContaining({
                page: 1,
                page_size: 20,
                scope: 'same_account',
                account_id: 'acc-2',
                sort_by: 'name',
                sort_order: 'asc',
                extensions: ['cbz', 'pdf'],
                hide_low_priority: false,
            }), expect.any(Object));
        });

        const callCountAfterFilters = getSimilarReportMock.mock.calls.length;
        await user.click(screen.getByRole('button', { name: /refresh/i }));
        await waitFor(() => expect(getSimilarReportMock.mock.calls.length).toBeGreaterThan(callCountAfterFilters));

        const paginationToolbar = screen.getByText(/page 1 of 2/i).parentElement;
        const [, nextPageButton] = paginationToolbar.querySelectorAll('button.p-1');
        await user.click(nextPageButton);
        await waitFor(() => {
            expect(getSimilarReportMock).toHaveBeenLastCalledWith(expect.objectContaining({
                page: 2,
                page_size: 20,
                scope: 'same_account',
                account_id: 'acc-2',
                sort_by: 'name',
                sort_order: 'asc',
                extensions: ['cbz', 'pdf'],
                hide_low_priority: false,
            }), expect.any(Object));
        });

        await user.click(screen.getByRole('button', { name: /create remove-duplicates job/i }));
        expect(await screen.findByText(/preferred account/i)).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /^cancel$/i }));
        await waitFor(() => {
            expect(screen.queryByText(/preferred account/i)).not.toBeInTheDocument();
        });
    }, 15000);
});
