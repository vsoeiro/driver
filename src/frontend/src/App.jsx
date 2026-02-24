import { Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import { ToastProvider } from './contexts/ToastContext';
import JobStatusNotifier from './components/JobStatusNotifier';

const FileBrowser = lazy(() => import('./pages/FileBrowser'));
const AllFiles = lazy(() => import('./pages/AllFiles'));
const Jobs = lazy(() => import('./pages/Jobs'));
const MetadataManager = lazy(() => import('./pages/MetadataManager'));
const RulesManager = lazy(() => import('./pages/RulesManager'));
const AdminSettings = lazy(() => import('./pages/AdminSettings'));
const AdminDashboard = lazy(() => import('./pages/AdminDashboard'));
const AccountsRedirect = lazy(() => import('./pages/AccountsRedirect'));

function App() {
    return (
        <ToastProvider>
            <JobStatusNotifier />
            <div className="min-h-screen text-foreground font-sans antialiased">
                <Suspense fallback={<div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Loading workspace...</div>}>
                    <Routes>
                        <Route element={<Layout />}>
                            <Route path="/" element={<Navigate to="/accounts" replace />} />
                            <Route path="/accounts" element={<AccountsRedirect />} />
                            <Route path="/drive/:accountId" element={<FileBrowser />} />
                            <Route path="/drive/:accountId/:folderId" element={<FileBrowser />} />
                            <Route path="/all-files" element={<AllFiles />} />
                            <Route path="/jobs" element={<Jobs />} />
                            <Route path="/metadata" element={<MetadataManager />} />
                            <Route path="/rules" element={<RulesManager />} />
                            <Route path="/admin" element={<Navigate to="/admin/dashboard" replace />} />
                            <Route path="/admin/dashboard" element={<AdminDashboard />} />
                            <Route path="/admin/settings" element={<AdminSettings />} />
                        </Route>
                    </Routes>
                </Suspense>
            </div>
        </ToastProvider>
    );
}

export default App;
