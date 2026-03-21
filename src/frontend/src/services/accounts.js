import api from './api';

/**
 * Get all linked accounts
 */
export const getAccounts = async (options = {}) => {
    const response = await api.get('/accounts', {
        signal: options.signal,
    });
    return response.data.accounts;
};

/**
 * Initiate OAuth flow for a provider
 */
export const linkAccount = (provider = 'microsoft') => {
    return `/api/v1/auth/${provider}/login`;
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
