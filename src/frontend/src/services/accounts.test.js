vi.mock('./api', () => ({
    default: {
        get: vi.fn(),
        delete: vi.fn(),
    },
}));

import api from './api';
import { getAccounts, linkAccount, unlinkAccount } from './accounts';

describe('accounts service', () => {
    it('returns account list from the API response', async () => {
        api.get.mockResolvedValue({ data: { accounts: [{ id: 'acc-1' }] } });

        await expect(getAccounts({ signal: 'abort-signal' })).resolves.toEqual([{ id: 'acc-1' }]);
        expect(api.get).toHaveBeenCalledWith('/accounts', { signal: 'abort-signal' });
    });

    it('returns the login URL for account linking', () => {
        expect(linkAccount('google')).toBe('/api/v1/auth/google/login');
    });

    it('deletes an account', async () => {
        api.delete.mockResolvedValue({});

        await unlinkAccount('acc-1');

        expect(api.delete).toHaveBeenCalledWith('/accounts/acc-1');
    });
});
