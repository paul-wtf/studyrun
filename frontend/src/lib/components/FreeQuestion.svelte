<script lang="ts">
  import { untrack } from 'svelte';
  import { api, errorText, isStale } from '#lib/api/client.ts';
  import type { FreeResult, GradingUnavailable, FreeEntry } from '#lib/api/models.ts';
  import Feedback from './Feedback.svelte';

  let {
    runId,
    entry,
    onDone,
    onStale
  }: { runId: number; entry: FreeEntry; onDone: () => void; onStale?: (error: unknown) => void } =
    $props();
  const start = untrack(() => entry);
  let text = $state('');
  let result = $state<FreeResult | null>(null);
  let unavailable = $state<GradingUnavailable | null>(
    start.grading_unavailable
      ? {
          grading_unavailable: true,
          reason: 'Die Bewertung war nicht möglich. Bewerte deine Antwort selbst.',
          model_answer: start.model_answer ?? ''
        }
      : null
  );
  let busy = $state(false);
  let error = $state('');
  const answered = $derived(result !== null || unavailable !== null);

  async function submit() {
    if (busy || answered || !text.trim()) return;
    busy = true;
    error = '';
    try {
      const res = await api.post<FreeResult | GradingUnavailable>(
        `/api/runs/${runId}/entries/${entry.n}/answer`,
        { answer: { text } }
      );
      if ('grading_unavailable' in res) unavailable = res;
      else result = res;
      busy = false;
    } catch (e) {
      if (isStale(e) && onStale) {
        busy = false;
        return onStale(e);
      }
      error = errorText(e);
      busy = false;
    }
  }

  async function selfRate(rating: 'again' | 'good') {
    if (busy) return;
    busy = true;
    error = '';
    try {
      await api.post(`/api/runs/${runId}/entries/${entry.n}/self-rate`, { rating });
      onDone();
    } catch (e) {
      busy = false;
      if (isStale(e) && onStale) return onStale(e);
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
    disabled={busy || answered}
    aria-label="Antwort"
    onkeydown={onKeydown}
    placeholder="In eigenen Worten …"
  ></textarea>
  {#if !answered}
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
        <button disabled={busy} onclick={() => selfRate('again')}>Wusste ich nicht</button>
        <button class="primary" disabled={busy} onclick={() => selfRate('good')}>Wusste ich</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
</style>
