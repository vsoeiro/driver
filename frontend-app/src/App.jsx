import React from 'react'
import { Routes, Route } from 'react-router-dom'
import FileBrowser from './pages/FileBrowser'
import Layout from './components/Layout'

function App() {
    return (
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
                </Route>
            </Routes>
        </div>
    )
}

export default App
