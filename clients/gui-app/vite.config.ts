import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    TanStackRouterVite({
      target: 'react',
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    sourcemap: 'hidden',
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/static': {
        target: process.env.VITE_API_BASE || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})

