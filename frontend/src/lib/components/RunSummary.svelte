<script lang="ts">
  import type { RunSummaryData } from '#lib/api/models.ts';

  let { summary }: { summary: RunSummaryData } = $props();
</script>

<div class="card stack">
  <h1>Geschafft</h1>
  <p><strong>{summary.correct} von {summary.answered} richtig</strong></p>
  {#if summary.chapters_introduced.length}
    <p class="muted">Neue Kapitel</p>
    <ul>
      {#each summary.chapters_introduced as title}
        <li>{title}</li>
      {/each}
    </ul>
  {/if}
  <p class="muted">
    Morgen {summary.due_tomorrow === 1 ? 'wartet 1 Wiederholung' : `warten ${summary.due_tomorrow} Wiederholungen`}.
  </p>
  <a class="btn primary block" href="/">Fertig</a>
</div>
