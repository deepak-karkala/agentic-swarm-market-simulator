import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/simulate": "http://localhost:8000",
      "/simulations": "http://localhost:8000",
      "/report": "http://localhost:8000",
    },
  },
})
