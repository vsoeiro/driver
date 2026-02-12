```
import React, { useEffect, useState } from 'react';
import { NavLink, useParams } from 'react-router-dom';
import { getAccounts, getQuota } from '../services/api';
import { HardDrive, Plus, Cloud, Loader2, User } from 'lucide-react';

export default function Sidebar() {
    const { accountId } = useParams();
    const [accounts, setAccounts] = useState([]);
    const [quotas, setQuotas] = useState({});

    useEffect(() => {
        getAccounts().then(async (data) => {
            setAccounts(data);
            // Fetch quota for each account
            const quotaMap = {};
            await Promise.all(data.map(async (acc) => {
                try {
                    const q = await getQuota(acc.id);
                    quotaMap[acc.id] = q;
                } catch (e) {
                    console.error(`Failed to fetch quota for ${ acc.id }`, e);
                }
            }));
            setQuotas(quotaMap);
        }).catch(console.error);
    }, []);

    const handleLinkAccount = () => {
        window.location.href = 'http://localhost:8000/api/v1/auth/microsoft/login';
    };

    const formatBytes = (bytes) => {
        if (!bytes) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    };

    const activeAccount = accounts.find(a => a.id === accountId);
    const activeQuota = activeAccount ? quotas[activeAccount.id] : null;

    return (
        <aside className="w-64 border-r bg-muted/10 flex flex-col h-screen sticky top-0">
            <div className="p-4 border-b flex items-center gap-2">
                <div className="p-2 bg-primary text-primary-foreground rounded-lg">
                    <Cloud size={20} />
                </div>
                <span className="font-bold text-lg">Driver</span>
            </div>

            <div className="p-4 flex-1 overflow-y-auto">
                <div className="text-xs font-semibold text-muted-foreground mb-3 text-center uppercase tracking-wider">
                    Accounts
                </div>
                <nav className="space-y-2">
                    {accounts.map(acc => (
                        <NavLink
                            key={acc.id}
                            to={`/ drive / ${ acc.id }`}
                            className={({ isActive }) => `
                                flex items - center gap - 3 px - 3 py - 2 rounded - md text - sm font - medium transition - colors
                                ${
    isActive
        ? 'bg-primary text-primary-foreground shadow-sm'
        : 'text-muted-foreground hover:bg-accent hover:text-foreground'
}
`}
                        >
                            <User size={18} className="shrink-0" />
                            <div className="flex-1 min-w-0 flex flex-col">
                                <span className="truncate font-medium leading-none">{acc.display_name}</span>
                                <span className={`text - xs truncate ${ acc.id === accountId ? 'text-primary-foreground/80' : 'text-muted-foreground' } `}>
                                    {acc.email}
                                </span>
                            </div>
                        </NavLink>
                    ))}
                </nav>
            </div>

            <div className="p-4 border-t space-y-4">
                {activeQuota && (
                    <div className="bg-card p-3 rounded-md border shadow-sm">
                        <div className="text-xs font-semibold text-muted-foreground mb-2 flex justify-between">
                            <span>Storage</span>
                            <span>{Math.round((activeQuota.used / activeQuota.total) * 100)}%</span>
                        </div>
                        <div className="flex justify-between text-xs mb-1">
                            <span>{formatBytes(activeQuota.used)}</span>
                            <span className="text-muted-foreground">of {formatBytes(activeQuota.total)}</span>
                        </div>
                        <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                            <div 
                                className={`h - full rounded - full transition - all duration - 500 ${
    (activeQuota.used / activeQuota.total) > 0.9 ? 'bg-destructive' : 'bg-primary'
} `}
                                style={{ width: `${ (activeQuota.used / activeQuota.total) * 100 }% ` }}
                            />
                        </div>
                    </div>
                )}

                <button
                    onClick={handleLinkAccount}
                </button>
            </div>
        </aside>
    );
}
