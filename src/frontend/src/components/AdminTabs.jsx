import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

export default function AdminTabs() {
    const { t } = useTranslation();
    const tabs = [
        { to: '/admin/dashboard', label: t('adminTabs.dashboard') },
        { to: '/admin/settings', label: t('adminTabs.settings') },
    ];

    return (
        <div className="inline-flex flex-wrap rounded-md border border-border bg-muted/40 p-0.5">
            {tabs.map((tab) => (
                <NavLink
                    key={tab.to}
                    to={tab.to}
                    className={({ isActive }) => `px-2.5 py-1 text-xs rounded-sm font-medium transition-colors ${
                        isActive
                            ? 'bg-background text-foreground shadow-sm'
                            : 'text-muted-foreground hover:text-foreground hover:bg-accent/70'
                    }`}
                >
                    {tab.label}
                </NavLink>
            ))}
        </div>
    );
}
