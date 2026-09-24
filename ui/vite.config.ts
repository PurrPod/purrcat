import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiEnvironment = (globalThis as {
  process?: { env?: Record<string, string | undefined> }
}).process?.env
const configuredApiPort = Number.parseInt(apiEnvironment?.PURRCAT_API_PORT ?? '', 10)
const apiPort = Number.isInteger(configuredApiPort) && configuredApiPort > 0
  ? configuredApiPort
  : 8000

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
