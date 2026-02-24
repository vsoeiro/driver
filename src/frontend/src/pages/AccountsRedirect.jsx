import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountsService } from '../services/accounts';

const { getAccounts } = accountsService;
const LAST_ACCOUNT_STORAGE_KEY = 'driver-last-account-id';

export default function AccountsRedirect() {
    const navigate = useNavigate();

    useEffect(() => {
        let active = true;

        const resolveAndRedirect = async () => {
            try {
                const accounts = await getAccounts();
                if (!active) return;

                if (!accounts.length) {
                    navigate('/all-files', { replace: true });
                    return;
                }

                const savedId = window.localStorage.getItem(LAST_ACCOUNT_STORAGE_KEY);
                const savedIsValid = savedId && accounts.some((account) => account.id === savedId);
                const targetId = savedIsValid ? savedId : accounts[0].id;
                navigate(`/drive/${targetId}`, { replace: true });
            } catch {
                if (!active) return;
                navigate('/all-files', { replace: true });
            }
        };

        resolveAndRedirect();
        return () => {
            active = false;
        };
    }, [navigate]);

    return null;
}
