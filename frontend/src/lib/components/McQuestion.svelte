<script lang="ts">
  import { api, errorText, isStale } from '#lib/api/client.ts';
  import type { McEntry, ObjectiveResult } from '#lib/api/models.ts';
  import Feedback from './Feedback.svelte';

  let {
    runId,
    entry,
    onDone,
    onStale
  }: { runId: number; entry: McEntry; onDone: () => void; onStale?: (error: unknown) => void } = $props();
  let result = $state<ObjectiveResult | null>(null);
  let chosen = $state<number | null>(null);
  let busy = $state(false);
  let error = $state('');

  async function choose(i: number) {
    busy = true;
    error = '';
    chosen = i;
    try {
      result = await api.post<ObjectiveResult>(`/api/runs/${runId}/entries/${entry.n}/answer`, {
        answer: { choice: i }
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
  <h2>{entry.item.prompt}</h2>
  <div class="options">
    {#each entry.item.options ?? [] as option, i}
      <button class:picked={chosen === i} disabled={busy} onclick={() => choose(i)}>{option}</button>
    {/each}
  </div>
  {#if error}<p class="error">{error}</p>{/if}
  {#if result}
    <Feedback itemId={entry.item.id} source={entry.item.source} {result} onnext={onDone} />
  {/if}
</div>

<style>
  .options { display: grid; gap: 0.6rem; }
  .options button { justify-content: flex-start; text-align: left; }
  .picked { border-color: var(--accent); border-width: 2px; }
</style>
