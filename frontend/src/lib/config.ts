// Конфигурация клиента: база API и X-API-Key.
//
// База берётся из VITE_API_BASE (по умолчанию "/api/v1" - в dev обслуживается
// прокси Vite, в prod - nginx по подпути). X-API-Key в рантайме хранится в
// localStorage (вводится пользователем); для dev можно задать VITE_API_KEY.
// Доступ к localStorage обёрнут в try/catch (приватный режим, запрет куки).

const API_KEY_STORAGE = 'stories.apiKey';

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? '/api/v1';

export function getApiKey(): string {
  try {
    const stored = localStorage.getItem(API_KEY_STORAGE);
    if (stored) {
      return stored;
    }
  } catch {
    // localStorage недоступен - откатываемся на env.
  }
  return import.meta.env.VITE_API_KEY ?? '';
}

export function setApiKey(value: string): void {
  try {
    localStorage.setItem(API_KEY_STORAGE, value.trim());
  } catch {
    // Молча игнорируем: ключ будет жить только в памяти текущей сессии.
  }
}

export function hasApiKey(): boolean {
  return getApiKey().length > 0;
}
