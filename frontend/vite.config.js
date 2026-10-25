import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'node:path'

// Two pages: the application (index.html) and the public site (site/index.html, rmsystem.co.ao - its own small
// bundle). In development the site is at http://localhost:5173/site/.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      input: {
        main: resolve(import.meta.dirname, 'index.html'),
        site: resolve(import.meta.dirname, 'site/index.html'),
      },
    },
  },
})
