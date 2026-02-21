import { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

const SIDEBAR_COLLAPSED_STORAGE_KEY = 'driver-sidebar-collapsed';

export default function Layout() {
    const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
        if (typeof window === 'undefined') {
            return false;
        }

        return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === 'true';
    });

    useEffect(() => {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(sidebarCollapsed));
    }, [sidebarCollapsed]);

    return (
        <div className="flex min-h-screen bg-background text-foreground">
            <Sidebar
                collapsed={sidebarCollapsed}
                onToggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
            />
            <main className="flex-1 min-w-0 overflow-auto">
                <Outlet />
            </main>
        </div>
    );
}
