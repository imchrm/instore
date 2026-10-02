# frontend - клиент stories-backend

Telegram Mini App на Svelte + Vite + TypeScript. Назначение и решения - в
[`../docs/adr/0001-frontend-architecture.md`](../docs/adr/0001-frontend-architecture.md).

Сценарий: ввод URL видео → создание задачи → прогресс (SSE) → список готовых
кусков (скачивание; публикация в Telegram Stories через `shareToStory` - после
backend-шага с публичными подписанными URL, Фаза 8).

## Стек

- Svelte 5 + Vite + TypeScript (SPA, статическая сборка).
- Telegram WebApp SDK (`telegram-web-app.js`) - тема и `shareToStory`.
- Клиент API (`src/lib/api.ts`) ходит в бэкенд с заголовком `X-API-Key`;
  прогресс читается из SSE через `fetch` (EventSource не умеет заголовки).

## Разработка

```bash
cd frontend
npm install
npm run dev        # дев-сервер; /api проксируется на VITE_PROXY_TARGET
```

Переменные - в `.env.example` (скопировать в `.env.local`). X-API-Key вводится
в интерфейсе и хранится в `localStorage`; для dev можно задать `VITE_API_KEY`.

Вне Telegram приложение тоже работает (тема - системная, кнопка «В Stories»
скрыта); внутри Telegram подхватываются тема и `shareToStory`.

## Проверки и сборка

```bash
npm run check      # svelte-check (strict) + tsc по конфигу node
npm run build      # прод-сборка в dist/
npm run preview    # предпросмотр собранного
```

## Деплой

`npm run build` даёт статику в `dist/`, которая раздаётся nginx. Для подпути
задать `VITE_BASE` (например `/instore/app/`) и описать соответствующую
`location` в nginx. Подробности появятся вместе с backend-шагом Фазы 8.

## Структура

```
src/
  lib/
    types.ts       # типы DTO (зеркало schemas.py; позже - генерация из OpenAPI)
    config.ts      # база API и X-API-Key
    api.ts         # REST + SSE клиент
    telegram.ts    # обёртка Telegram WebApp SDK
  components/
    JobForm.svelte     # форма создания задачи
    JobProgress.svelte # индикатор статуса/прогресса
    ChunkList.svelte   # список кусков (скачать / в Stories)
  App.svelte       # оркестрация сценария
  main.ts          # точка входа
```
