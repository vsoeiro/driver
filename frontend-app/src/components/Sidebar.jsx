import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { getAccounts, getQuota } from '../services/api';
import { HardDrive, Plus, Cloud, Loader2 } from 'lucide-react';

export default function Sidebar() {
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
                    console.error(`Failed to fetch quota for ${acc.id}`, e);
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
                <nav className="space-y-4">
                    {accounts.map(acc => {
                        const quota = quotas[acc.id];
                        const usedPct = quota ? (quota.used / quota.total) * 100 : 0;

                        return (
                            <div key={acc.id} className="flex flex-col gap-1">
                                <NavLink
                                    to={`/drive/${acc.id}`}
                                    className={({ isActive }) => `
                                        flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors
                                        ${isActive
                                            ? 'bg-primary text-primary-foreground shadow-sm'
                                            : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                                        }
                                    `}
                                >
                                    <HardDrive size={18} />
                                    <div className="flex-1 min-w-0">
                                        <div className="truncate">{acc.display_name}</div>
                                    </div>
                                </NavLink>

                                {quota && (
                                    <div className="px-3 text-xs text-muted-foreground">
                                        <div className="flex justify-between mb-1">
                                            <span>{formatBytes(quota.used)}</span>
                                            <span>{formatBytes(quota.total)}</span>
                                        </div>
                                        <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-primary/70 rounded-full transition-all duration-500"
                                                style={{ width: `${usedPct}%` }}
                                            />
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </nav>
            </div>

            <div className="p-4 border-t">
                <button
                    onClick={handleLinkAccount}
                    className="flex w-full items-center justify-center gap-2 bg-primary/10 text-primary hover:bg-primary/20 px-4 py-2 rounded-md text-sm font-medium transition-colors"
                >
                    <Plus size={16} />
                    Link Account
                </button>
            </div>
        </aside>
    );
}
