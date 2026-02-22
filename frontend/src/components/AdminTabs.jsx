import { NavLink } from 'react-router-dom';

const tabs = [
    { to: '/admin/dashboard', label: 'Dashboard' },
    { to: '/admin/settings', label: 'Settings' },
];

export default function AdminTabs() {
    return (
        <div className="inline-flex rounded-xl border border-border/70 bg-card/85 p-1 backdrop-blur-sm shadow-sm">
            {tabs.map((tab) => (
                <NavLink
                    key={tab.to}
                    to={tab.to}
                    className={({ isActive }) => `px-3 py-1.5 text-sm rounded-lg font-medium transition-all ${
                        isActive
                            ? 'bg-primary text-primary-foreground shadow-sm'
                            : 'text-muted-foreground hover:text-foreground hover:bg-accent/70'
                    }`}
                >
                    {tab.label}
                </NavLink>
            ))}
        </div>
    );
}
