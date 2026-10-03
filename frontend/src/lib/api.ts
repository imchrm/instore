// Типизированный клиент API бэкенда (REST + SSE).
//
// Все запросы идут с заголовком X-API-Key. SSE-поток прогресса читается через
// fetch + ReadableStream (а не EventSource), потому что EventSource не умеет
// задавать заголовки, а эндпоинт событий требует X-API-Key.

import { API_BASE, getApiKey } from './config';
import type { JobCreateRequest, JobResponse, ProgressEvent, ShareUrl } from './types';
import { TERMINAL_STATUSES } from './types';

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function authHeaders(extra?: Record<string, string>): Headers {
  const headers = new Headers(extra);
  headers.set('X-API-Key', getApiKey());
  return headers;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json();
    if (data && typeof data === 'object' && 'detail' in data) {
      return String((data as { detail: unknown }).detail);
    }
  } catch {
    // Тело не JSON - вернём статус-текст ниже.
  }
  return response.statusText || `HTTP ${response.status}`;
}

export async function createJob(request: JobCreateRequest): Promise<JobResponse> {
  const response = await fetch(`${API_BASE}/jobs`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return (await response.json()) as JobResponse;
}

export async function getJob(jobId: string): Promise<JobResponse> {
  const response = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return (await response.json()) as JobResponse;
}

/**
 * Подписаться на поток прогресса задачи (SSE). Вызывает onEvent для каждого
 * события; завершается, когда бэкенд закрывает поток (терминальный статус) или
 * срабатывает signal. Бросает ApiError при не-2xx ответе.
 */
export async function streamProgress(
  jobId: string,
  onEvent: (event: ProgressEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}/events`, {
    headers: authHeaders({ Accept: 'text/event-stream' }),
    signal,
  });
  if (!response.ok || response.body === null) {
    throw new ApiError(response.status, await errorMessage(response));
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += value;
      // События SSE разделены пустой строкой.
      let separator = buffer.indexOf('\n\n');
      while (separator !== -1) {
        const raw = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        const event = parseSseData(raw);
        if (event) {
          onEvent(event);
          if (TERMINAL_STATUSES.has(event.status)) {
            return;
          }
        }
        separator = buffer.indexOf('\n\n');
      }
    }
  } finally {
    reader.cancel().catch(() => undefined);
  }
}

function parseSseData(block: string): ProgressEvent | null {
  const dataLine = block
    .split('\n')
    .map((line) => line.trimEnd())
    .find((line) => line.startsWith('data:'));
  if (!dataLine) {
    return null;
  }
  try {
    return JSON.parse(dataLine.slice('data:'.length).trim()) as ProgressEvent;
  } catch {
    return null;
  }
}

/**
 * Запросить подписанную публичную ссылку на кусок (для Telegram shareToStory).
 * Требует X-API-Key (владение задачей). 503 - функция на сервере выключена.
 */
export async function fetchShareUrl(jobId: string, index: number): Promise<ShareUrl> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/chunks/${index}/share-url`,
    { headers: authHeaders() },
  );
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return (await response.json()) as ShareUrl;
}

/** Скачать кусок (с X-API-Key) и сохранить файлом на устройство. */
export async function downloadChunk(jobId: string, index: number, filename: string): Promise<void> {
  const response = await fetch(
    `${API_BASE}/jobs/${encodeURIComponent(jobId)}/chunks/${index}`,
    { headers: authHeaders() },
  );
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.click();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
