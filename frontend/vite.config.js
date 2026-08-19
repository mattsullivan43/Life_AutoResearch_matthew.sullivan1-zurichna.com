import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy /api to the FastAPI backend so the browser stays same-origin
// (this keeps Server-Sent Events working without CORS gymnastics).
export default defineConfig({
  plugins: [react()],
  // amazon-cognito-identity-js references Node's `global`, which doesn't exist
  // in the browser — without this shim the dev bundle dies at import time with
  // "Uncaught ReferenceError: global is not defined" and the page renders blank.
  define: { global: 'globalThis' },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
