import { NavLink, useLocation } from 'react-router-dom';
import {
    Cloud,
    Activity,
    Database,
    FileText,
    Wand2,
    HardDrive,
} from 'lucide-react';

export default function Sidebar() {
    const location = useLocation();
    const quickLinks = [
        { to: '/accounts', label: 'Accounts', icon: HardDrive },
        { to: '/all-files', label: 'Files', icon: FileText },
        { to: '/metadata', label: 'Metadata', icon: Database },
        { to: '/rules', label: 'Rules', icon: Wand2 },
        { to: '/jobs', label: 'Jobs', icon: Activity },
    ];

    return (
        <aside className="sticky top-0 flex h-full w-64 shrink-0 flex-col border-r border-border/70 bg-card/72 backdrop-blur-xl">
            <div className="border-b border-border/70 px-4 py-4">
                <div className="inline-flex items-center gap-3 min-w-0">
                    <div className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-cyan-500 text-primary-foreground shadow-lg shadow-primary/20">
                        <Cloud size={18} />
                    </div>
                    <div className="min-w-0">
                        <div className="text-base font-semibold">Driver Hub</div>
                        <div className="text-xs text-muted-foreground">Storage orchestration</div>
                    </div>
                </div>
            </div>

            <div className="flex-1 min-h-0 flex flex-col px-3 pt-3 pb-3">
                <div className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    Navigation
                </div>
                <nav className="space-y-1.5">
                    {quickLinks.map(({ to, label, icon: Icon }) => (
                        <NavLink
                            key={to}
                            to={to}
                            title={label}
                            className={({ isActive }) => {
                                const activeByDrive = to === '/accounts' && location.pathname.startsWith('/drive/');
                                const isLinkActive = isActive || activeByDrive;
                                return `
                                    group flex items-center rounded-lg border px-3 py-2 text-sm font-medium transition-all
                                    gap-3
                                    ${isLinkActive
                                        ? 'border-primary/35 bg-primary/12 text-primary'
                                        : 'border-transparent text-muted-foreground hover:border-border/80 hover:bg-accent/70 hover:text-foreground'
                                    }
                                `;
                            }}
                        >
                            <Icon size={16} className="shrink-0" />
                            <span>{label}</span>
                        </NavLink>
                    ))}
                </nav>
            </div>
        </aside>
    );
}
