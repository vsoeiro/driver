import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    build: {
        rollupOptions: {
            output: {
                manualChunks(id) {
                    if (id.includes('node_modules/react') || id.includes('node_modules/react-dom')) return 'vendor-react'
                    if (id.includes('node_modules/@tanstack/react-query')) return 'vendor-query'
                    if (id.includes('node_modules/lucide-react')) return 'vendor-icons'
                    if (id.includes('node_modules/@radix-ui')) return 'vendor-radix'
                    return undefined
                },
            },
        },
    },
    server: {
        port: 5173,
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
                secure: false
            }
        }
    }
})
