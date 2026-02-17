import { NavLink } from 'react-router-dom';

const tabs = [
    { to: '/admin/dashboard', label: 'Dashboard' },
    { to: '/admin/settings', label: 'Settings' },
];

export default function AdminTabs() {
    return (
        <div className="inline-flex rounded-lg border bg-background p-1">
            {tabs.map((tab) => (
                <NavLink
                    key={tab.to}
                    to={tab.to}
                    className={({ isActive }) => `px-3 py-1.5 text-sm rounded-md transition-colors ${
                        isActive
                            ? 'bg-primary text-primary-foreground'
                            : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                    }`}
                >
                    {tab.label}
                </NavLink>
            ))}
        </div>
    );
}
