import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Cloud Run backend (dev). Override with VITE_BACKEND_URL env var if needed.
const BACKEND_URL = process.env.VITE_BACKEND_URL || 'https://aict-backend-dev-hqp7acew3q-uc.a.run.app'
const WS_BACKEND_URL = BACKEND_URL.replace('https://', 'wss://').replace('http://', 'ws://')

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
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
      '/ws': {
        target: WS_BACKEND_URL,
        ws: true,
        changeOrigin: true,
        secure: true,
      },
    },
  },
})
