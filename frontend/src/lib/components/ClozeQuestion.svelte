<script lang="ts">
  import { api, errorText } from '#lib/api/client.ts';
  import type { ItemEntry, ObjectiveResult } from '#lib/api/types.ts';
  import Feedback from './Feedback.svelte';

  let { runId, entry, onDone }: { runId: number; entry: ItemEntry; onDone: () => void } = $props();
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
      error = errorText(e);
      busy = false;
    }
  }
</script>

<div class="stack">
  <p class="muted">Lücke füllen</p>
  <h2>{entry.item.text}</h2>
  <form class="stack" onsubmit={submit}>
    <input
      type="text"
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
