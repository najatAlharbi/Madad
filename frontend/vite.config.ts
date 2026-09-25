import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The /api proxy means the browser only ever talks to localhost:5173, so the
// backend's HttpOnly SameSite=Lax session cookie is same-origin and needs no
// CORS exemption in development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
