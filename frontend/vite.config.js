import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const frontendDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryDirectory = resolve(frontendDirectory, '..');
const bundleDirectory = resolve(repositoryDirectory, 'data/derived/demo');

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, frontendDirectory, 'VITE_');
  const staticMode = env.VITE_DATA_MODE === 'static';

  return {
    base: env.VITE_BASE_PATH || '/',
    plugins: [react()],
    publicDir: staticMode ? resolve(env.VITE_BUNDLE_DIR || process.env.VITE_BUNDLE_DIR || bundleDirectory) : false,
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      proxy: {
        '/v1': {
          target: env.VITE_API_ORIGIN || 'http://127.0.0.1:8000',
          changeOrigin: false,
        },
      },
      fs: { allow: [repositoryDirectory] },
    },
    build: { sourcemap: false },
  };
});
