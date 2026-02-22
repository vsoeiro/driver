import { Routes, Route, Navigate } from 'react-router-dom';
import { Cloud } from 'lucide-react';
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

function App() {
    return (
        <ToastProvider>
            <JobStatusNotifier />
            <div className="min-h-screen text-foreground font-sans antialiased">
                <Routes>
                    <Route element={<Layout />}>
                        <Route
                            path="/"
                            element={(
                                <div className="app-page items-center justify-center">
                                    <div className="empty-state w-full max-w-xl">
                                        <div className="empty-state-icon">
                                            <Cloud size={28} />
                                        </div>
                                        <h1 className="empty-state-title">Choose an account to begin</h1>
                                        <p className="empty-state-text">
                                            Select a connected provider on the left to browse files, metadata and jobs.
                                        </p>
                                    </div>
                                </div>
                            )}
                        />
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
