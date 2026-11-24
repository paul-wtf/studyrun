<script lang="ts">
  import { api, errorText, isStale } from '#lib/api/client.ts';
  import type { ClozeEntry, ObjectiveResult } from '#lib/api/models.ts';
  import Feedback from './Feedback.svelte';

  let {
    runId,
    entry,
    onDone,
    onStale
  }: { runId: number; entry: ClozeEntry; onDone: () => void; onStale?: (error: unknown) => void } = $props();
  let text = $state('');
  let result = $state<ObjectiveResult | null>(null);
  let busy = $state(false);
  let error = $state('');

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (busy || !text.trim()) return;
    busy = true;
    error = '';
    try {
      result = await api.post<ObjectiveResult>(`/api/runs/${runId}/entries/${entry.n}/answer`, {
        answer: { text }
      });
    } catch (e) {
      if (isStale(e) && onStale) {
        busy = false;
        return onStale(e);
      }
      error = errorText(e);
      busy = false;
    }
  }
</script>

<div class="stack">
  <form class="card stack" onsubmit={submit}>
    <p class="muted">Lücke füllen</p>
    <h2>{entry.item.text}</h2>
    <input
      type="text"
      class:correct={result?.correct === true}
      class:wrong={result?.correct === false}
      bind:value={text}
      disabled={busy}
      aria-label="Antwort"
      autocomplete="off"
      autocapitalize="off"
      autocorrect="off"
      spellcheck="false"
    />
    {#if !result}
      <button class="primary block" type="submit" disabled={busy}>Prüfen</button>
    {/if}
  </form>
  {#if error}<p class="error">{error}</p>{/if}
  {#if result}
    <Feedback itemId={entry.item.id} source={entry.item.source} {result} onnext={onDone} />
  {/if}
</div>
