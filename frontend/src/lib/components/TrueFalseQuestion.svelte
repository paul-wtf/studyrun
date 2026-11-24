<script lang="ts">
  import { api, errorText, isStale } from '#lib/api/client.ts';
  import type { TrueFalseEntry, ObjectiveResult } from '#lib/api/models.ts';
  import Feedback from './Feedback.svelte';

  let {
    runId,
    entry,
    onDone,
    onStale
  }: { runId: number; entry: TrueFalseEntry; onDone: () => void; onStale?: (error: unknown) => void } = $props();
  let result = $state<ObjectiveResult | null>(null);
  let chosen = $state<boolean | null>(null);
  let busy = $state(false);
  let error = $state('');

  async function answer(value: boolean) {
    busy = true;
    error = '';
    chosen = value;
    try {
      result = await api.post<ObjectiveResult>(`/api/runs/${runId}/entries/${entry.n}/answer`, {
        answer: { value }
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
  <div class="card stack">
    <p class="muted">Wahr oder falsch?</p>
    <h2>{entry.item.statement}</h2>
    <div class="pair">
      {#each [[true, 'Wahr'], [false, 'Falsch']] as const as [value, label] (label)}
        <button
          class="option"
          class:picked={chosen === value && !result}
          class:correct={result !== null && label === result.expected}
          class:wrong={result !== null && chosen === value && !result.correct}
          disabled={busy}
          onclick={() => answer(value)}>{label}</button
        >
      {/each}
    </div>
  </div>
  {#if error}<p class="error">{error}</p>{/if}
  {#if result}
    <Feedback itemId={entry.item.id} source={entry.item.source} {result} onnext={onDone} />
  {/if}
</div>

<style>
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
</style>
