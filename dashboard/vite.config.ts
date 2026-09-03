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
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.replace(/\\/g, '/');
          if (!normalizedId.includes('/node_modules/')) {
            return;
          }
          if (
            normalizedId.includes('/node_modules/react/') ||
            normalizedId.includes('/node_modules/react-dom/') ||
            normalizedId.includes('/node_modules/scheduler/')
          ) {
            return 'vendor-react';
          }
          if (
            normalizedId.includes('/node_modules/@tanstack/react-query') ||
            normalizedId.includes('/node_modules/@tanstack/query-core') ||
            normalizedId.includes('/node_modules/@tanstack/react-router') ||
            normalizedId.includes('/node_modules/@tanstack/router-core')
          ) {
            return 'vendor-tanstack';
          }
          if (
            normalizedId.includes('/node_modules/@radix-ui/') ||
            normalizedId.includes('/node_modules/radix-ui/') ||
            normalizedId.includes('/node_modules/lucide-react/') ||
            normalizedId.includes('/node_modules/class-variance-authority/') ||
            normalizedId.includes('/node_modules/tailwind-merge/') ||
            normalizedId.includes('/node_modules/clsx/')
          ) {
            return 'vendor-ui';
          }
          if (
            normalizedId.includes('/node_modules/recharts/') ||
            normalizedId.includes('/node_modules/@xyflow/')
          ) {
            return 'vendor-charts';
          }
        },
      },
    },
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

