// Типы транспорта API. Зеркалят DTO бэкенда (interface/api/schemas.py).
// При вводе генерации клиента из OpenAPI (Фаза 8) эти определения заменит
// сгенерированный модуль.

export type JobStatus =
  | 'queued'
  | 'downloading'
  | 'transcoding'
  | 'segmenting'
  | 'probing'
  | 'ready'
  | 'failed'
  | 'expired';

export type StoriesFit = 'none' | 'cover' | 'pad';

export const TERMINAL_STATUSES: ReadonlySet<JobStatus> = new Set<JobStatus>([
  'ready',
  'failed',
  'expired',
]);

export interface ChunkInfo {
  index: number;
  filename: string;
  url: string;
  duration_sec: number;
  size_bytes: number;
  sha256: string;
  over_limit: boolean;
}

export interface ErrorInfo {
  code: string;
  message: string;
}

export interface JobResponse {
  job_id: string;
  status: JobStatus;
  source_title: string | null;
  source_duration_sec: number | null;
  progress: number;
  chunks: ChunkInfo[];
  error: ErrorInfo | null;
  created_at: number;
  updated_at: number;
}

export interface JobCreateRequest {
  url: string;
  segment_time: number;
  max_height: number;
  stories_fit: StoriesFit;
  use_cookies: boolean;
}

export interface ProgressEvent {
  job_id: string;
  status: JobStatus;
  phase_progress: number;
  message: string | null;
}
