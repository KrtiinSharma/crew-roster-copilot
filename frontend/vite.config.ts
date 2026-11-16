import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// VITE_BASE is "/<repo-name>/" when building for GitHub Pages.
// The backend routes have no /api prefix, so the dev proxy strips it.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})
