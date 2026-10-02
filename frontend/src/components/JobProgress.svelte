<script lang="ts">
  import type { JobStatus } from '../lib/types';

  interface Props {
    status: JobStatus;
    /** Доля выполнения текущей фазы, 0..1. */
    progress: number;
    message?: string | null;
  }

  const { status, progress, message }: Props = $props();

  const labels: Record<JobStatus, string> = {
    queued: 'В очереди',
    downloading: 'Скачивание',
    transcoding: 'Перекодирование',
    segmenting: 'Нарезка',
    probing: 'Проверка кусков',
    ready: 'Готово',
    failed: 'Ошибка',
    expired: 'Истекло',
  };

  const percent = $derived(Math.round(Math.max(0, Math.min(progress, 1)) * 100));
</script>

<div class="progress" class:failed={status === 'failed'}>
  <div class="head">
    <span class="label">{labels[status]}</span>
    <span class="pct">{percent}%</span>
  </div>
  <div class="bar" role="progressbar" aria-valuenow={percent} aria-valuemin="0" aria-valuemax="100">
    <div class="fill" style:width="{percent}%"></div>
  </div>
  {#if message}
    <p class="message">{message}</p>
  {/if}
</div>

<style>
  .progress {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .head {
    display: flex;
    justify-content: space-between;
    font-size: 0.9rem;
  }
  .bar {
    height: 8px;
    border-radius: 999px;
    background: var(--border);
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: var(--accent);
    transition: width 0.3s ease;
  }
  .failed .fill {
    background: var(--danger);
  }
  .message {
    margin: 0;
    font-size: 0.8rem;
    color: var(--muted);
  }
</style>
