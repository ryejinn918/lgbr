import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxy = {
  '/api': {
    target: 'http://127.0.0.1:8787',
    changeOrigin: true,
  },
} as const

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 8788,
    strictPort: true,
    allowedHosts: ['lgbrwsl.tail700203.ts.net'],
    proxy: apiProxy,
  },
  preview: {
    host: '0.0.0.0',
    port: 8788,
    strictPort: true,
    allowedHosts: ['lgbrwsl.tail700203.ts.net'],
    proxy: apiProxy,
  },
})
