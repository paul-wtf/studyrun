<script lang="ts">
  import { api, errorText, isStale } from '#lib/api/client.ts';
  import type { FreeResult, GradingUnavailable, ItemEntry } from '#lib/api/types.ts';
  import Feedback from './Feedback.svelte';

  let {
    runId,
    entry,
    onDone,
    onStale
  }: { runId: number; entry: ItemEntry; onDone: () => void; onStale?: () => void } = $props();
  let text = $state('');
  let result = $state<FreeResult | null>(null);
  let unavailable = $state<GradingUnavailable | null>(null);
  let busy = $state(false);
  let error = $state('');

  async function submit() {
    if (busy || !text.trim()) return;
    busy = true;
    error = '';
    try {
      const res = await api.post<FreeResult | GradingUnavailable>(
        `/api/runs/${runId}/entries/${entry.n}/answer`,
        { answer: { text } }
      );
      if ('grading_unavailable' in res) unavailable = res;
      else result = res;
    } catch (e) {
      if (isStale(e) && onStale) return onStale();
      error = errorText(e);
      busy = false;
    }
  }

  async function selfRate(rating: 'again' | 'good') {
    error = '';
    try {
      await api.post(`/api/runs/${runId}/entries/${entry.n}/self-rate`, { rating });
      onDone();
    } catch (e) {
      if (isStale(e) && onStale) return onStale();
      error = errorText(e);
    }
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void submit();
    }
  }
</script>

<div class="stack">
  <h2>{entry.item.prompt}</h2>
  <textarea
    bind:value={text}
    disabled={busy}
    aria-label="Antwort"
    onkeydown={onKeydown}
    placeholder="In eigenen Worten …"
  ></textarea>
  {#if !result && !unavailable}
    <button class="primary block" disabled={busy} onclick={submit}>
      {busy ? 'Wird bewertet …' : 'Antworten'}
    </button>
  {/if}
  {#if error}<p class="error">{error}</p>{/if}
  {#if result}
    <Feedback itemId={entry.item.id} source={entry.item.source} {result} onnext={onDone} />
  {/if}
  {#if unavailable}
    <div class="card stack">
      <p class="muted">{unavailable.reason}</p>
      <h2>Musterantwort</h2>
      <p>{unavailable.model_answer}</p>
      <a href={entry.item.source} target="_blank" rel="noopener">Im Skript nachlesen</a>
      <div class="pair">
        <button onclick={() => selfRate('again')}>Wusste ich nicht</button>
        <button class="primary" onclick={() => selfRate('good')}>Wusste ich</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
</style>
