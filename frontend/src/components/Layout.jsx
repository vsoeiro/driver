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
        <div className="app-shell">
            <div className="min-h-screen p-3 sm:p-4">
                <div className="app-panel flex h-[calc(100vh-1.5rem)] overflow-hidden">
                    <Sidebar
                        collapsed={sidebarCollapsed}
                        onToggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
                    />
                    <main className="flex-1 min-w-0 min-h-0 overflow-auto">
                        <Outlet />
                    </main>
                </div>
            </div>
        </div>
    );
}
