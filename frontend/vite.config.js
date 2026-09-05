import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * The dev server proxies /api to the Node backend.
 *
 * WHY A PROXY RATHER THAN A CORS ORIGIN. `ai-service` and `backend` both
 * default `CORS_ALLOW_ORIGINS` to empty -- no browser origin is allowed --
 * and that default is deliberate, because the backend is a server-side
 * consumer of the ai-service and nothing else should be talking to either.
 * Proxying keeps the browser same-origin in development, so no CORS
 * relaxation is needed to run this locally and none is tempting to add.
 *
 * The frontend NEVER talks to `ai-service` directly. Every call goes through
 * the backend, which is where authentication and owner scoping live.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.js'],
    include: ['tests/**/*.test.{js,jsx}'],
  },
});
