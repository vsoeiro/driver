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
    // Redirect to backend auth endpoint
    // Adjust URL based on environment if needed, but relative path should work with proxy
    window.location.href = `http://localhost:8000/api/v1/auth/${provider}/login`;
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
