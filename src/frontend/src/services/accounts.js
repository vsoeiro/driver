import api from './api';

/**
 * Get all linked accounts
 */
export const getAccounts = async () => {
    const response = await api.get('/accounts');
    return response.data.accounts;
};

/**
 * Initiate OAuth flow for a provider
 */
export const linkAccount = (provider = 'microsoft') => {
    window.location.href = `/api/v1/auth/${provider}/login`;
};

/**
 * Unlink an account
 */
export const unlinkAccount = async (accountId) => {
    await api.delete(`/accounts/${accountId}`);
};

export const accountsService = {
    getAccounts,
    linkAccount,
    unlinkAccount
};

export default accountsService;
