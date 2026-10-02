/// <reference types="svelte" />
/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** База API, например "/api/v1" (dev через прокси) или полный URL. */
  readonly VITE_API_BASE?: string;
  /** X-API-Key для dev; в рантайме приоритетно значение из localStorage. */
  readonly VITE_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
