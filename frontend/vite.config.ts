import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the API is the Docker Compose stack behind its gateway.
const backend = 'http://localhost'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': backend,
      '/media': backend,
    },
  },
})
