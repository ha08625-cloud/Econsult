import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  root: '.',
  build: {
    rollupOptions: {
      input: {
        main: 'index.html',
        admin: 'admin-ui/index.html',
      }
    }
  },
  server: {
    proxy: {
      '/conditions': 'http://localhost:8000',
      '/form': 'http://localhost:8000',
      '/safety-warning': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
    }
  }
})
