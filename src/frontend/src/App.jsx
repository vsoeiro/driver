import { Routes, Route, Navigate } from 'react-router-dom';
import FileBrowser from './pages/FileBrowser';
import AllFiles from './pages/AllFiles';
import Jobs from './pages/Jobs';
import Layout from './components/Layout';
import { ToastProvider } from './contexts/ToastContext';
import JobStatusNotifier from './components/JobStatusNotifier';
import MetadataManager from './pages/MetadataManager';
import RulesManager from './pages/RulesManager';
import AdminSettings from './pages/AdminSettings';
import AdminDashboard from './pages/AdminDashboard';
import AccountsRedirect from './pages/AccountsRedirect';

function App() {
    return (
        <ToastProvider>
            <JobStatusNotifier />
            <div className="min-h-screen text-foreground font-sans antialiased">
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
            </div>
        </ToastProvider>
    );
}

export default App;
