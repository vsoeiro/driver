import { useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { queryKeys } from '../../../lib/queryKeys';
import { accountsService } from '../../../services/accounts';

export function useAccountsQuery(options = {}) {
    return useQuery({
        queryKey: queryKeys.accounts.all(),
        queryFn: ({ signal }) => accountsService.getAccounts({ signal }),
        staleTime: 60000,
        ...options,
    });
}

export function useAccountsActions() {
    const queryClient = useQueryClient();

    const getAccounts = useCallback((options = {}) => accountsService.getAccounts(options), []);

    const linkAccount = useCallback((provider = 'microsoft') => {
        const targetUrl = accountsService.linkAccount(provider);
        if (typeof targetUrl === 'string' && typeof window !== 'undefined') {
            window.location.assign(targetUrl);
        }
        return targetUrl;
    }, []);

    const unlinkAccount = useCallback(async (accountId) => {
        await accountsService.unlinkAccount(accountId);
        await queryClient.invalidateQueries({ queryKey: queryKeys.accounts.all() });
    }, [queryClient]);

    return useMemo(() => ({
        getAccounts,
        linkAccount,
        unlinkAccount,
    }), [getAccounts, linkAccount, unlinkAccount]);
}

export default useAccountsQuery;
