import { Routes, Route } from 'react-router-dom'
import FileBrowser from './pages/FileBrowser'
import AllFiles from './pages/AllFiles'
import Jobs from './pages/Jobs'
import Layout from './components/Layout'
import { ToastProvider } from './contexts/ToastContext'
import JobStatusNotifier from './components/JobStatusNotifier'
import MetadataManager from './pages/MetadataManager'
import RulesManager from './pages/RulesManager'
import AdminSettings from './pages/AdminSettings'
import PluginsManager from './pages/PluginsManager'

function App() {
    return (
        <ToastProvider>
            <JobStatusNotifier />
            <div className="min-h-screen bg-background text-foreground font-sans antialiased">
                <Routes>
                    <Route element={<Layout />}>
                        <Route path="/" element={
                            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                                <p>Select an account from the sidebar to view files.</p>
                            </div>
                        } />
                        <Route path="/drive/:accountId" element={<FileBrowser />} />
                        <Route path="/drive/:accountId/:folderId" element={<FileBrowser />} />
                        <Route path="/all-files" element={<AllFiles />} />
                        <Route path="/jobs" element={<Jobs />} />
                        <Route path="/metadata" element={<MetadataManager />} />
                        <Route path="/plugins" element={<PluginsManager />} />
                        <Route path="/rules" element={<RulesManager />} />
                        <Route path="/admin/settings" element={<AdminSettings />} />
                    </Route>
                </Routes>
            </div>
        </ToastProvider>
    )
}

export default App
