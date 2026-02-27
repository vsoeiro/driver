import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

export default function AdminTabs() {
    const { t } = useTranslation();
    const tabs = [
        { to: '/admin/dashboard', label: t('adminTabs.dashboard') },
        { to: '/admin/settings', label: t('adminTabs.settings') },
    ];

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
