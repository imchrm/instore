<script lang="ts">
  import type { ChunkInfo } from '../lib/types';
  import { chunkAbsoluteUrl, downloadChunk } from '../lib/api';
  import { shareToStory, supportsShareToStory } from '../lib/telegram';

  interface Props {
    jobId: string;
    chunks: ChunkInfo[];
  }

  const { jobId, chunks }: Props = $props();

  // Лимит истории Telegram - 30 МБ (см. ADR 0001).
  const STORY_MAX_BYTES = 30 * 1024 * 1024;
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

  function onShare(chunk: ChunkInfo): void {
    // ВНИМАНИЕ: пока отдача кусков закрыта X-API-Key, Telegram не сможет забрать
    // этот URL. Публичная подписанная отдача (HMAC+TTL) - следующий backend-шаг
    // Фазы 8; до него кнопка носит демонстрационный характер.
    shareToStory(chunkAbsoluteUrl(chunk.url));
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
            {#if chunk.size_bytes > STORY_MAX_BYTES}<span class="badge warn">&gt;30 МБ</span>{/if}
          </span>
        </div>
        <div class="actions">
          <button onclick={() => onDownload(chunk)} disabled={busy === chunk.index}>
            {busy === chunk.index ? '...' : 'Скачать'}
          </button>
          {#if canShare}
            <button class="ghost" onclick={() => onShare(chunk)}>В Stories</button>
          {/if}
        </div>
      </li>
    {/each}
  </ul>
  {#if error}<p class="error">{error}</p>{/if}
  {#if canShare}
    <p class="note">
      «В Stories» открывает редактор историй Telegram. Публикация заработает после
      backend-шага: публичный подписанный URL кусков (Фаза 8).
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
