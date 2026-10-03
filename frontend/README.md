# frontend - клиент stories-backend

Telegram Mini App на Svelte + Vite + TypeScript. Назначение и решения - в
[`../docs/adr/0001-frontend-architecture.md`](../docs/adr/0001-frontend-architecture.md).

Сценарий: ввод URL видео → создание задачи → прогресс (SSE) → список готовых
кусков: скачивание и публикация в Telegram Stories. Для публикации клиент
запрашивает у бэкенда подписанный публичный URL куска
(`GET /jobs/{id}/chunks/{index}/share-url`) и передаёт его в `shareToStory` -
Telegram тянет файл сам и открывает родной редактор историй. Куски крупнее 30 МБ
Telegram не принимает (кнопка выключена).

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
`location` в nginx, отдающую `index.html`.

На бэкенде для публикации в Stories должны быть заданы `SIGNING_SECRET` и
`PUBLIC_BASE_URL` (например `https://360tur.uz/instore`) - см. `../docs/DEPLOY.md`,
раздел «Публичные подписанные URL кусков».

## Настройка Telegram (бот и Mini App)

`shareToStory` работает только когда страница открыта как **Mini App внутри
Telegram** (есть `window.Telegram.WebApp`). В обычном браузере приложение тоже
работает, но кнопка «В Stories» скрыта. Чтобы открыть его в Telegram, нужен бот и
зарегистрированный Mini App:

1. **Создать бота:** в [@BotFather](https://t.me/BotFather) - `/newbot`, получить
   токен. (Токен нужен только для настройки; клиент его не использует.)
2. **Зарегистрировать Mini App:** `/newapp` у BotFather → выбрать бота → задать имя,
   короткое имя (`short_name`), иконку и **URL** собранного клиента (HTTPS,
   например `https://360tur.uz/instore/app/`). Получите прямую ссылку вида
   `https://t.me/<bot>/<short_name>`.
3. **(Необязательно) кнопка меню:** `/mybots` → бот → *Bot Settings* → *Menu Button*
   → задать тот же URL, чтобы открывать Mini App кнопкой в чате с ботом.
4. **Открыть** Mini App по ссылке `t.me/<bot>/<short_name>` (или кнопкой меню) -
   внутри Telegram появится `window.Telegram.WebApp` и кнопка «В Stories».

Домен Mini App должен совпадать с тем, где раздаётся клиент, и быть доступен по
HTTPS. Отдельный сервер боту не нужен: бот здесь - только «обёртка» для запуска
Mini App; вся логика в статическом клиенте и уже существующем API. Токен бота на
клиенте и сервере не требуется (мы не используем Bot API и серверную проверку
`initData`). Если позже понадобится усилить доступ - можно добавить валидацию
`initData` на бэкенде; сейчас доступ к API - по `X-API-Key`.

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
