// Тонкая типизированная обёртка над Telegram WebApp SDK.
//
// SDK подключается скриптом telegram-web-app.js в index.html и выставляет
// window.Telegram.WebApp. Вне Telegram (обычный браузер) объекта нет - все
// функции деградируют мягко, приложение остаётся работоспособным.

interface TelegramWebApp {
  ready(): void;
  expand(): void;
  version: string;
  colorScheme: 'light' | 'dark';
  isVersionAtLeast(version: string): boolean;
  shareToStory(mediaUrl: string, params?: { text?: string }): void;
}

interface TelegramNamespace {
  WebApp?: TelegramWebApp;
}

declare global {
  interface Window {
    Telegram?: TelegramNamespace;
  }
}

function webApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function isTelegram(): boolean {
  return webApp() !== null;
}

/** Инициализация Mini App: сообщить готовность и развернуть на весь экран. */
export function initTelegram(): void {
  const app = webApp();
  if (!app) {
    return;
  }
  // Маркер для CSS: внутри Telegram темой управляют переменные --tg-theme-*,
  // поэтому браузерный тёмный фолбэк (prefers-color-scheme) не применяется.
  document.documentElement.dataset.tg = app.colorScheme;
  app.ready();
  app.expand();
}

/** Поддерживается ли shareToStory (добавлен в Bot API 7.8). */
export function supportsShareToStory(): boolean {
  const app = webApp();
  return app !== null && app.isVersionAtLeast('7.8');
}

/**
 * Открыть родной редактор историй Telegram с указанным медиа. media_url должен
 * быть публично доступен по HTTPS (Telegram тянет его сам, без X-API-Key) -
 * публичная подписанная отдача кусков появится в backend-шаге Фазы 8.
 */
export function shareToStory(mediaUrl: string, text?: string): void {
  const app = webApp();
  if (!app) {
    return;
  }
  app.shareToStory(mediaUrl, text ? { text } : undefined);
}
