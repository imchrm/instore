<script lang="ts">
  import { onMount } from 'svelte';
  import JobForm from './components/JobForm.svelte';
  import JobProgress from './components/JobProgress.svelte';
  import ChunkList from './components/ChunkList.svelte';
  import { createJob, getJob, streamProgress } from './lib/api';
  import { hasApiKey, setApiKey } from './lib/config';
  import { initTelegram } from './lib/telegram';
  import type { JobCreateRequest, JobResponse, JobStatus } from './lib/types';

  let job = $state<JobResponse | null>(null);
  let status = $state<JobStatus | null>(null);
  let phaseProgress = $state(0);
  let message = $state<string | null>(null);
  let error = $state('');
  let processing = $state(false);

  let keyReady = $state(hasApiKey());
  let keyInput = $state('');

  const isReady = $derived(job !== null && job.status === 'ready' && job.chunks.length > 0);

  onMount(() => {
    initTelegram();
  });

  function saveKey(): void {
    if (keyInput.trim() === '') {
      return;
    }
    setApiKey(keyInput);
    keyReady = hasApiKey();
    keyInput = '';
  }

  async function handleSubmit(request: JobCreateRequest): Promise<void> {
    error = '';
    job = null;
    status = null;
    phaseProgress = 0;
    message = null;
    processing = true;
    try {
      const created = await createJob(request);
      job = created;
      status = created.status;
      await streamProgress(created.job_id, (event) => {
        status = event.status;
        phaseProgress = event.phase_progress;
        message = event.message;
      });
      // SSE-событие не несёт манифест - дочитываем полную задачу (куски/ошибку).
      const final = await getJob(created.job_id);
      job = final;
      status = final.status;
      if (final.status === 'ready') {
        phaseProgress = 1;
      }
      if (final.error) {
        error = `${final.error.code}: ${final.error.message}`;
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      processing = false;
    }
  }

  function reset(): void {
    job = null;
    status = null;
    phaseProgress = 0;
    message = null;
    error = '';
  }
</script>

<main>
  <header>
    <h1>Stories Backend</h1>
    <p class="tagline">Видео по URL → куски для Telegram Stories</p>
  </header>

  {#if !keyReady}
    <section class="card key">
      <p>Введите X-API-Key для доступа к API.</p>
      <div class="key-row">
        <input type="password" bind:value={keyInput} placeholder="X-API-Key" autocomplete="off" />
        <button onclick={saveKey}>Сохранить</button>
      </div>
    </section>
  {:else}
    <section class="card">
      <JobForm disabled={processing} onsubmit={handleSubmit} />
    </section>

    {#if job && job.source_title}
      <p class="source">{job.source_title}</p>
    {/if}

    {#if status}
      <section class="card">
        <JobProgress {status} progress={phaseProgress} {message} />
      </section>
    {/if}

    {#if error}
      <p class="error">{error}</p>
    {/if}

    {#if isReady && job}
      <section class="card">
        <ChunkList jobId={job.job_id} chunks={job.chunks} />
      </section>
    {/if}

    {#if job && !processing}
      <button class="reset" onclick={reset}>Новая задача</button>
    {/if}
  {/if}
</main>

<style>
  main {
    max-width: 520px;
    margin: 0 auto;
    padding: 1rem 1rem 2rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  header {
    text-align: center;
  }
  h1 {
    margin: 0;
    font-size: 1.4rem;
  }
  .tagline {
    margin: 0.25rem 0 0;
    font-size: 0.85rem;
    color: var(--muted);
  }
  .card {
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--card-bg);
  }
  .key-row {
    display: flex;
    gap: 0.5rem;
  }
  .key-row input {
    flex: 1;
    padding: 0.55rem 0.6rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--input-bg);
    color: var(--text);
    font: inherit;
  }
  .key-row button,
  .reset {
    padding: 0.55rem 0.9rem;
    border: none;
    border-radius: 8px;
    background: var(--accent);
    color: var(--accent-text);
    font: inherit;
    cursor: pointer;
  }
  .reset {
    align-self: center;
  }
  .source {
    margin: 0;
    text-align: center;
    font-size: 0.9rem;
    color: var(--muted);
  }
  .error {
    margin: 0;
    padding: 0.6rem 0.8rem;
    border-radius: 8px;
    background: color-mix(in srgb, var(--danger) 15%, transparent);
    color: var(--danger);
    font-size: 0.9rem;
  }
</style>
