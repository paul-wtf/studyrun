<script lang="ts">
  import { api, errorText, isStale } from '#lib/api/client.ts';
  import type { IntroEntry } from '#lib/api/models.ts';

  let {
    runId,
    entry,
    onDone,
    onStale
  }: { runId: number; entry: IntroEntry; onDone: () => void; onStale?: () => void } = $props();
  let busy = $state(false);
  let error = $state('');

  async function ack() {
    busy = true;
    error = '';
    try {
      await api.post(`/api/runs/${runId}/entries/${entry.n}/ack`);
      onDone();
    } catch (e) {
      if (isStale(e) && onStale) {
        busy = false;
        return onStale();
      }
      error = errorText(e);
      busy = false;
    }
  }
</script>

<div class="card stack">
  <p class="muted">Neues Kapitel</p>
  <h2>{entry.chapter.title}</h2>
  <p>{entry.chapter.summary}</p>
  {#if entry.chapter.concepts.length}
    <ul>
      {#each entry.chapter.concepts as concept}
        <li><strong>{concept.term}</strong>: {concept.explanation}</li>
      {/each}
    </ul>
  {/if}
  <a href={entry.chapter.source} target="_blank" rel="noopener">Im Skript nachlesen</a>
  {#if error}<p class="error">{error}</p>{/if}
  <button class="primary block" disabled={busy} onclick={ack}>Weiter</button>
</div>
