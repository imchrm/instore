import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig, loadEnv } from 'vite';

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // process.env имеет приоритет над .env-файлами: так сборка в Docker получает
  // значения из build-арг/ENV (loadEnv читает только .env-файлы).
  const proxyTarget = process.env.VITE_PROXY_TARGET ?? env.VITE_PROXY_TARGET ?? 'http://localhost:8000';
  // Базовый путь сборки (для раздачи под подпутём, напр. /instore/app/).
  const base = process.env.VITE_BASE ?? env.VITE_BASE ?? '/';

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
