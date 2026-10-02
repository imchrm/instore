import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig, loadEnv } from 'vite';

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // Куда проксировать /api в dev (локальный или удалённый бэкенд).
  const proxyTarget = env.VITE_PROXY_TARGET ?? 'http://localhost:8000';
  // Базовый путь сборки (для раздачи под подпутём за nginx, напр. /instore/app/).
  const base = env.VITE_BASE ?? '/';

  return {
    base,
    plugins: [svelte()],
    server: {
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
