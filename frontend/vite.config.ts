import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Load .env from repo root so one .env.development can serve both backend and frontend.
const rootDir = path.resolve(__dirname, '..')

// Cloud Run backend (dev). Override with VITE_BACKEND_URL env var if needed.
const BACKEND_URL = process.env.VITE_BACKEND_URL || 'https://aict-backend-dev-hqp7acew3q-uc.a.run.app'
const WS_BACKEND_URL = BACKEND_URL.replace('https://', 'wss://').replace('http://', 'ws://')

// https://vite.dev/config/
export default defineConfig({
  envDir: rootDir,
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
    // Pre-bundle noVNC (patch node_modules browser.js top-level await for esbuild)
    include: ['@novnc/novnc'],
  },
  server: {
    port: 3000,
    strictPort: true,
    proxy: {
      '/api': {
        target: BACKEND_URL,
        changeOrigin: true,
        secure: true,
      },
      '/internal': {
        target: BACKEND_URL,
        changeOrigin: true,
        secure: true,
      },
      '/testfads89213xlogin': {
        target: BACKEND_URL,
        changeOrigin: true,
        secure: true,
      },
      '/ws': {
        target: WS_BACKEND_URL,
        ws: true,
        changeOrigin: true,
        secure: true,
      },
    },
  },
})
