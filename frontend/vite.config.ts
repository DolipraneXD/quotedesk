import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the API runs on 8765 (python -m app); in production FastAPI serves dist/.
const apiTarget = process.env.QUOTEDESK_API ?? 'http://127.0.0.1:8765'

export default defineConfig({
  plugins: [react()],
  server: {
    host: process.env.VITE_HOST ?? '127.0.0.1',
    port: 5173,
    proxy: { '/api': apiTarget },
  },
  build: { outDir: 'dist', chunkSizeWarningLimit: 2000 },
})
