import { useEffect, useState } from 'react';
import { accountsService } from '../services/accounts';
const { getAccounts, linkAccount } = accountsService;
import { Link } from 'react-router-dom';
import { Plus, HardDrive, Calendar, ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import ProviderIcon from '../components/ProviderIcon';
import ProviderPickerModal from '../components/ProviderPickerModal';
import { formatDateOnly } from '../utils/dateTime';

export default function Dashboard() {
    const { t, i18n } = useTranslation();
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [pickerOpen, setPickerOpen] = useState(false);

    useEffect(() => {
        getAccounts().then(data => {
            setAccounts(data);
            setLoading(false);
        }).catch(err => {
            console.error(err);
            setLoading(false);
        });
    }, []);

    return (
        <div className="app-page mx-auto w-full max-w-6xl">
            <header className="page-header flex items-center justify-between">
                <h1 className="page-title">{t('dashboard.title')}</h1>
                <button
                    onClick={() => setPickerOpen(true)}
                    className="btn-minimal-primary"
                >
                    <Plus size={18} />
                    {t('dashboard.linkAccount')}
                </button>
            </header>

            {loading ? (
                <div className="flex justify-center p-12">
                    <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
                </div>
            ) : accounts.length === 0 ? (
                <div className="empty-state">
                    <HardDrive className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                    <h3 className="text-lg font-medium">{t('dashboard.noAccounts')}</h3>
                    <p className="text-muted-foreground mb-6">{t('dashboard.noAccountsHelp')}</p>
                    <button
                        onClick={() => setPickerOpen(true)}
                        className="btn-minimal-primary"
                    >
                        {t('dashboard.linkAccount')}
                    </button>
                </div>
            ) : (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {accounts.map(acc => (
                        <Link
                            to={`/drive/${acc.id}`}
                            key={acc.id}
                            className="group block rounded-sm border border-border/90 bg-card p-5 transition-colors hover:bg-muted/25"
                        >
                            <div className="flex items-start justify-between mb-4">
                                <div className="status-badge status-badge-info p-2">
                                    <ProviderIcon provider={acc.provider} className="w-6 h-6" />
                                </div>
                                <span className="status-badge status-badge-success">
                                    {t('dashboard.active')}
                                </span>
                            </div>

                            <h3 className="font-semibold text-lg mb-1">{acc.display_name}</h3>
                            <p className="text-sm text-muted-foreground mb-4 truncate">{acc.email}</p>

                            <div className="mt-4 flex items-center justify-between border-t pt-4 text-xs text-muted-foreground">
                                <div className="flex items-center gap-1">
                                    <Calendar size={12} />
                                    {formatDateOnly(acc.created_at, i18n.language)}
                                </div>
                                <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
                            </div>
                        </Link>
                    ))}
                </div>
            )}
            <ProviderPickerModal
                isOpen={pickerOpen}
                onClose={() => setPickerOpen(false)}
                onSelect={(provider) => {
                    setPickerOpen(false);
                    linkAccount(provider);
                }}
            />
        </div>
    );
}
