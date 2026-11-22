import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dev server proxies API calls to the backend, so the browser sees one origin (no CORS).
const API = process.env.SKARBONKA_API_URL ?? 'http://127.0.0.1:8000'
const apiPaths = ['/transactions', '/allocations', '/categories', '/imports', '/rules',
  '/categorize', '/review-queue', '/health', '/openapi.json']

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    proxy: Object.fromEntries(apiPaths.map((p) => [p, { target: API, changeOrigin: true }])),
  },
})
