<script lang="ts">
  import type { ChunkInfo } from '../lib/types';
  import { downloadChunk, fetchShareUrl } from '../lib/api';
  import { shareToStory, supportsShareToStory } from '../lib/telegram';

  interface Props {
    jobId: string;
    chunks: ChunkInfo[];
  }

  const { jobId, chunks }: Props = $props();

  const canShare = supportsShareToStory();

  let busy = $state<number | null>(null);
  let error = $state('');

  function mib(bytes: number): string {
    return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
  }

  async function onDownload(chunk: ChunkInfo): Promise<void> {
    error = '';
    busy = chunk.index;
    try {
      await downloadChunk(jobId, chunk.index, chunk.filename);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = null;
    }
  }

  async function onShare(chunk: ChunkInfo): Promise<void> {
    // Берём у бэкенда подписанный публичный URL (Telegram тянет его сам, без
    // X-API-Key) и открываем родной редактор историй.
    error = '';
    busy = chunk.index;
    try {
      const share = await fetchShareUrl(jobId, chunk.index);
      shareToStory(share.url);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = null;
    }
  }
</script>

<section class="chunks">
  <h2>Куски ({chunks.length})</h2>
  <ul>
    {#each chunks as chunk (chunk.index)}
      <li>
        <div class="meta">
          <span class="name">#{chunk.index} · {chunk.filename}</span>
          <span class="sub">
            {chunk.duration_sec.toFixed(1)} c · {mib(chunk.size_bytes)}
            {#if chunk.over_limit}<span class="badge warn">over_limit</span>{/if}
            {#if chunk.over_story_limit}<span class="badge warn">&gt;30 МБ</span>{/if}
          </span>
        </div>
        <div class="actions">
          <button onclick={() => onDownload(chunk)} disabled={busy === chunk.index}>
            {busy === chunk.index ? '...' : 'Скачать'}
          </button>
          {#if canShare}
            <button
              class="ghost"
              onclick={() => onShare(chunk)}
              disabled={busy === chunk.index || chunk.over_story_limit}
              title={chunk.over_story_limit ? 'Кусок больше 30 МБ - Telegram не примет' : ''}
            >
              В Stories
            </button>
          {/if}
        </div>
      </li>
    {/each}
  </ul>
  {#if error}<p class="error">{error}</p>{/if}
  {#if canShare}
    <p class="note">
      «В Stories» открывает родной редактор историй Telegram с этим куском. Куски
      крупнее 30 МБ Telegram не принимает (кнопка выключена) - уменьшите высоту при
      создании задачи.
    </p>
  {:else}
    <p class="note">
      Публикация в Stories доступна только внутри Telegram (Mini App). В обычном
      браузере - «Скачать» и публикация вручную.
    </p>
  {/if}
</section>

<style>
  .chunks {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  h2 {
    margin: 0;
    font-size: 1rem;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.6rem 0.7rem;
    border: 1px solid var(--border);
    border-radius: 8px;
  }
  .meta {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    min-width: 0;
  }
  .name {
    font-size: 0.9rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sub {
    font-size: 0.78rem;
    color: var(--muted);
    display: flex;
    gap: 0.4rem;
    align-items: center;
  }
  .badge {
    padding: 0.05rem 0.35rem;
    border-radius: 999px;
    font-size: 0.7rem;
  }
  .badge.warn {
    background: var(--danger);
    color: var(--accent-text);
  }
  .actions {
    display: flex;
    gap: 0.4rem;
    flex-shrink: 0;
  }
  button {
    padding: 0.45rem 0.7rem;
    border: none;
    border-radius: 7px;
    background: var(--accent);
    color: var(--accent-text);
    font: inherit;
    font-size: 0.85rem;
    cursor: pointer;
  }
  button.ghost {
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
  }
  button:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .error {
    margin: 0;
    color: var(--danger);
    font-size: 0.85rem;
  }
  .note {
    margin: 0;
    font-size: 0.78rem;
    color: var(--muted);
  }
</style>
