import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { getAccounts } from '../services/api';
import { HardDrive, Plus, Cloud } from 'lucide-react';

export default function Sidebar() {
    const [accounts, setAccounts] = useState([]);

    useEffect(() => {
        getAccounts().then(setAccounts).catch(console.error);
    }, []);

    const handleLinkAccount = () => {
        window.location.href = 'http://localhost:8000/api/v1/auth/microsoft/login';
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
                <nav className="space-y-1">
                    {accounts.map(acc => (
                        <NavLink
                            key={acc.id}
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
                    ))}
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
