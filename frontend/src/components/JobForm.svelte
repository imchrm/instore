<script lang="ts">
  import type { JobCreateRequest, StoriesFit } from '../lib/types';

  interface Props {
    disabled: boolean;
    onsubmit: (request: JobCreateRequest) => void;
  }

  const { disabled, onsubmit }: Props = $props();

  let url = $state('');
  let segmentTime = $state(45);
  let maxHeight = $state(480);
  let storiesFit = $state<StoriesFit>('cover');
  let useCookies = $state(false);

  const fitOptions: ReadonlyArray<{ value: StoriesFit; label: string }> = [
    { value: 'cover', label: 'cover (обрезать под 1080x1920)' },
    { value: 'pad', label: 'pad (вписать с подложкой)' },
    { value: 'none', label: 'none (не менять кадр)' },
  ];

  function submit(event: SubmitEvent): void {
    event.preventDefault();
    if (disabled || url.trim() === '') {
      return;
    }
    onsubmit({
      url: url.trim(),
      segment_time: segmentTime,
      max_height: maxHeight,
      stories_fit: storiesFit,
      use_cookies: useCookies,
    });
  }
</script>

<form onsubmit={submit}>
  <label class="field">
    <span>URL видео (YouTube / Instagram)</span>
    <input
      type="url"
      bind:value={url}
      placeholder="https://..."
      required
      {disabled}
      autocomplete="off"
    />
  </label>

  <div class="row">
    <label class="field">
      <span>Длина куска, c</span>
      <input type="number" bind:value={segmentTime} min="5" max="60" {disabled} />
    </label>
    <label class="field">
      <span>Макс. высота, px</span>
      <input type="number" bind:value={maxHeight} min="240" max="2160" step="120" {disabled} />
    </label>
  </div>

  <label class="field">
    <span>Кадрирование под Stories</span>
    <select bind:value={storiesFit} {disabled}>
      {#each fitOptions as option (option.value)}
        <option value={option.value}>{option.label}</option>
      {/each}
    </select>
  </label>

  <label class="checkbox">
    <input type="checkbox" bind:checked={useCookies} {disabled} />
    <span>Использовать cookies (приватные Instagram reels)</span>
  </label>

  <button type="submit" {disabled}>Создать задачу</button>
</form>

<style>
  form {
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    font-size: 0.9rem;
  }
  .row {
    display: flex;
    gap: 0.75rem;
  }
  .row .field {
    flex: 1;
  }
  input,
  select {
    padding: 0.55rem 0.6rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--input-bg);
    color: var(--text);
    font: inherit;
  }
  .checkbox {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
  }
  .checkbox input {
    width: auto;
  }
  button {
    margin-top: 0.25rem;
    padding: 0.7rem 1rem;
    border: none;
    border-radius: 8px;
    background: var(--accent);
    color: var(--accent-text);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.6;
    cursor: default;
  }
</style>
