import { useEffect, useState } from 'react';
import { accountsService } from '../services/accounts';
const { getAccounts, linkAccount } = accountsService;
import { Link } from 'react-router-dom';
import { Plus, HardDrive, Calendar, ArrowRight } from 'lucide-react';
import ProviderIcon from '../components/ProviderIcon';
import ProviderPickerModal from '../components/ProviderPickerModal';

export default function Dashboard() {
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
        <div className="container mx-auto p-6 max-w-5xl">
            <header className="flex justify-between items-center mb-8">
                <h1 className="text-3xl font-bold tracking-tight">Connected Accounts</h1>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setPickerOpen(true)}
                        className="flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded-md hover:bg-primary/90 transition-colors"
                    >
                        <Plus size={20} />
                        Link Account
                    </button>
                </div>
            </header>

            {loading ? (
                <div className="flex justify-center p-12">
                    <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
                </div>
            ) : accounts.length === 0 ? (
                <div className="text-center p-12 border border-dashed rounded-lg bg-muted/50">
                    <HardDrive className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                    <h3 className="text-lg font-medium">No accounts linked</h3>
                    <p className="text-muted-foreground mb-6">Connect a cloud account to get started.</p>
                    <button
                        onClick={() => setPickerOpen(true)}
                        className="bg-primary text-primary-foreground px-4 py-2 rounded-md hover:bg-primary/90"
                    >
                        Link Account
                    </button>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {accounts.map(acc => (
                        <Link
                            to={`/drive/${acc.id}`}
                            key={acc.id}
                            className="group block border rounded-xl p-6 hover:shadow-lg transition-all bg-card hover:border-primary/50"
                        >
                            <div className="flex items-start justify-between mb-4">
                                <div className="p-3 bg-blue-100 dark:bg-blue-900/30 rounded-lg text-blue-600 dark:text-blue-400">
                                    <ProviderIcon provider={acc.provider} className="w-6 h-6" />
                                </div>
                                <span className="bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 text-xs font-medium px-2.5 py-0.5 rounded-full">
                                    Active
                                </span>
                            </div>

                            <h3 className="font-semibold text-lg mb-1">{acc.display_name}</h3>
                            <p className="text-sm text-muted-foreground mb-4 truncate">{acc.email}</p>

                            <div className="flex items-center justify-between text-xs text-muted-foreground mt-4 pt-4 border-t">
                                <div className="flex items-center gap-1">
                                    <Calendar size={12} />
                                    {new Date(acc.created_at).toLocaleDateString()}
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
