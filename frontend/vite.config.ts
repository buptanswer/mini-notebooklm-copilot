import path from "path"
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // Bind IPv4 loopback explicitly. Node >=17 resolves "localhost" to ::1
    // (IPv6) first, so Vite's default would only listen on [::1]:5173, and
    // http://localhost:5173 / http://127.0.0.1:5173 in the browser (IPv4) get
    // "connection refused" on Windows. Forcing 127.0.0.1 matches the proxy
    // target and the uvicorn --host convention.
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
})
