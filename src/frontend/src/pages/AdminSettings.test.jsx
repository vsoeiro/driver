import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const getRuntimeSettingsMock = vi.fn();
const updateRuntimeSettingsMock = vi.fn();
const getAccountsMock = vi.fn();
const createReindexComicCoversJobMock = vi.fn();
const createConvertLibraryComicArchivesJobMock = vi.fn();
const showToastMock = vi.fn();

let runtimeSettingsState = null;
let accountsState = [];

function clone(value) {
    return JSON.parse(JSON.stringify(value));
}

function buildRuntimeSettings(overrides = {}) {
    return {
        enable_daily_sync_scheduler: true,
        daily_sync_cron: '0 0 * * *',
        worker_job_timeout_seconds: 1800,
        ai_model_default: 'llama3.1:8b',
        ai_provider_mode: 'local',
        ai_base_url_remote: '',
        ai_api_key_remote: '',
        plugin_settings: [
            {
                plugin_key: 'comics_core',
                plugin_name: 'Comics',
                plugin_description: 'Comics runtime settings',
                capabilities: {
                    supported_input_types: ['number', 'folder_target'],
                    actions: ['reindex_covers', 'convert_archives'],
                },
                fields: [
                    {
                        key: 'max_candidates',
                        label: 'Max candidates',
                        input_type: 'number',
                        value: 10,
                        minimum: 1,
                        maximum: 30,
                        description: 'Maximum candidate matches.',
                    },
                    {
                        key: 'covers_folder',
                        label: 'Covers folder',
                        input_type: 'folder_target',
                        value: null,
                        description: 'Target folder for covers.',
                    },
                ],
            },
        ],
        ...overrides,
    };
}

function applyPayloadToRuntimeSettings(payload) {
    return {
        ...runtimeSettingsState,
        ...payload,
        plugin_settings: runtimeSettingsState.plugin_settings.map((group) => ({
            ...group,
            fields: group.fields.map((field) => ({
                ...field,
                value: payload.plugin_settings?.[group.plugin_key]?.[field.key] ?? field.value,
            })),
        })),
    };
}

vi.mock('../services/settings', () => ({
    settingsService: {
        getRuntimeSettings: (...args) => getRuntimeSettingsMock(...args),
        updateRuntimeSettings: (...args) => updateRuntimeSettingsMock(...args),
    },
}));

vi.mock('../services/accounts', () => ({
    accountsService: {
        getAccounts: (...args) => getAccountsMock(...args),
    },
}));

vi.mock('../services/jobs', () => ({
    jobsService: {
        createReindexComicCoversJob: (...args) => createReindexComicCoversJobMock(...args),
        createConvertLibraryComicArchivesJob: (...args) => createConvertLibraryComicArchivesJobMock(...args),
    },
}));

vi.mock('../contexts/ToastContext', () => ({
    ToastProvider: ({ children }) => children,
    useToast: () => ({ showToast: showToastMock }),
}));

vi.mock('../components/AdminTabs', () => ({
    default: () => <div>Admin Tabs</div>,
}));

vi.mock('../components/FolderTargetPickerModal', () => ({
    default: ({ isOpen, initialValue, onClose, onConfirm }) => (
        isOpen ? (
            <div role="dialog" aria-label="Folder picker">
                <div>{initialValue?.folder_path || 'No folder selected'}</div>
                <button
                    type="button"
                    onClick={() => onConfirm({
                        account_id: 'acc-2',
                        folder_id: 'folder-9',
                        folder_path: 'Root/Covers',
                    })}
                >
                    Confirm folder
                </button>
                <button type="button" onClick={onClose}>Close picker</button>
            </div>
        ) : null
    ),
}));

import { renderWithProviders } from '../test/render';
import AdminSettings from './AdminSettings';

describe('AdminSettings page', () => {
    beforeEach(() => {
        runtimeSettingsState = buildRuntimeSettings();
        accountsState = [
            { id: 'acc-1', display_name: 'Primary', email: 'primary@example.com' },
            { id: 'acc-2', display_name: 'Archive', email: 'archive@example.com' },
        ];

        getRuntimeSettingsMock.mockReset();
        updateRuntimeSettingsMock.mockReset();
        getAccountsMock.mockReset();
        createReindexComicCoversJobMock.mockReset();
        createConvertLibraryComicArchivesJobMock.mockReset();
        showToastMock.mockReset();

        getRuntimeSettingsMock.mockImplementation(async () => clone(runtimeSettingsState));
        getAccountsMock.mockImplementation(async () => clone(accountsState));
        updateRuntimeSettingsMock.mockImplementation(async (payload) => {
            runtimeSettingsState = applyPayloadToRuntimeSettings(payload);
            return clone(runtimeSettingsState);
        });
        createReindexComicCoversJobMock.mockResolvedValue({ total_jobs: 3, total_items: 640, chunk_size: 250, job_ids: ['job-cover-7'] });
        createConvertLibraryComicArchivesJobMock.mockResolvedValue({ total_jobs: 2, total_items: 120, chunk_size: 100, job_ids: ['job-convert-1'] });
    });

    it('loads settings and saves scheduler, worker and AI changes', async () => {
        const user = userEvent.setup();

        renderWithProviders(<AdminSettings />);

        expect(await screen.findByText(/admin settings/i)).toBeInTheDocument();
        expect(await screen.findByDisplayValue('0 0 * * *')).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /workers/i }));
        const workerTimeoutInput = screen.getByRole('spinbutton');
        await user.clear(workerTimeoutInput);
        await user.type(workerTimeoutInput, '2400');

        await user.click(screen.getByRole('button', { name: /^ai /i }));
        await user.selectOptions(screen.getByRole('combobox'), 'gemini');
        const modelInput = screen.getByPlaceholderText(/llama3\.1:8b/i);
        await user.clear(modelInput);
        await user.type(modelInput, 'gemini-2.0-flash');

        await user.click(screen.getByRole('button', { name: /^save$/i }));

        await waitFor(() => {
            expect(updateRuntimeSettingsMock).toHaveBeenCalledWith(expect.objectContaining({
                enable_daily_sync_scheduler: true,
                daily_sync_cron: '0 0 * * *',
                worker_job_timeout_seconds: 2400,
                ai_provider_mode: 'gemini',
                ai_model_default: 'gemini-2.0-flash',
                plugin_settings: {
                    comics_core: {
                        max_candidates: 10,
                        covers_folder: null,
                    },
                },
            }));
        });
        expect(showToastMock).toHaveBeenCalledWith('Settings saved successfully', 'success');
    });

    it('filters groups, updates plugin fields, picks folders and triggers library actions', async () => {
        const user = userEvent.setup();

        renderWithProviders(<AdminSettings />);

        await screen.findByText(/admin settings/i);

        await user.type(screen.getByPlaceholderText(/search settings/i), 'metadata');
        await user.click(screen.getByRole('button', { name: /metadata library/i }));

        expect(await screen.findByText('Comics')).toBeInTheDocument();
        expect(screen.getByText(/supported field types: number, folder_target/i)).toBeInTheDocument();

        const candidateInput = screen.getAllByRole('spinbutton')[1];
        await user.clear(candidateInput);
        await user.type(candidateInput, '15');

        await user.click(screen.getByRole('button', { name: /select account and folder/i }));
        expect(screen.getByRole('dialog', { name: /folder picker/i })).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /confirm folder/i }));

        expect(await screen.findByText(/archive \(archive@example\.com\)/i)).toBeInTheDocument();
        expect(screen.getByText(/root\/covers/i)).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /re-index covers/i }));
        await waitFor(() => expect(createReindexComicCoversJobMock).toHaveBeenCalledWith('comics_core', 250));
        expect(showToastMock).toHaveBeenCalledWith('Cover re-index started in 3 jobs for 640 items.', 'success');

        await user.selectOptions(screen.getByRole('combobox', { name: /source format/i }), 'zip');
        await user.selectOptions(screen.getByRole('combobox', { name: /target format/i }), 'cbr');
        const conversionChunkInput = screen.getByRole('spinbutton', { name: /chunk size/i });
        fireEvent.change(conversionChunkInput, { target: { value: '100' } });
        await user.click(screen.getByRole('checkbox', { name: /delete source after successful conversion/i }));
        await user.click(screen.getByRole('button', { name: /convert archives/i }));
        await waitFor(() => expect(createConvertLibraryComicArchivesJobMock).toHaveBeenCalledWith('zip', 'cbr', 100, true));
        expect(showToastMock).toHaveBeenCalledWith('Archive conversion zip -> cbr started in 2 jobs for 120 items.', 'success');

        await user.click(screen.getByRole('button', { name: /^save$/i }));
        await waitFor(() => {
            expect(updateRuntimeSettingsMock).toHaveBeenCalledWith(expect.objectContaining({
                plugin_settings: {
                    comics_core: {
                        max_candidates: 15,
                        covers_folder: {
                            account_id: 'acc-2',
                            folder_id: 'folder-9',
                            folder_path: 'Root/Covers',
                        },
                    },
                },
            }));
        });
    });

    it('shows a toast when the admin settings fail to load', async () => {
        const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        getRuntimeSettingsMock.mockRejectedValueOnce(new Error('load failed'));

        renderWithProviders(<AdminSettings />);

        await waitFor(() => {
            expect(showToastMock).toHaveBeenCalledWith('Failed to load admin settings', 'error');
        });

        consoleErrorSpy.mockRestore();
    });
});
