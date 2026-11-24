<script lang="ts">
  import type { Week } from '#lib/api/models.ts';
  import { weekdayShort } from '#lib/dates.ts';

  let { week }: { week: Week } = $props();
</script>

<div class="week">
  <ol aria-label="Diese Woche">
    {#each week.days as day (day.date)}
      <li aria-label="{weekdayShort(day.date)}: {day.done ? 'gelernt' : 'offen'}">
        <span class="dot" class:done={day.done}></span>
        <span class="day" aria-hidden="true">{weekdayShort(day.date)}</span>
      </li>
    {/each}
  </ol>
  <p class="count">
    {#if week.done_count >= week.goal}Wochenziel erreicht{:else}{week.done_count} von {week.goal} Tagen{/if}
  </p>
</div>

<style>
  .week { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 1rem; }
  ol { display: flex; gap: 0.4rem; list-style: none; margin: 0; padding: 0; }
  li { display: flex; flex-direction: column; align-items: center; gap: 0.25rem; min-width: 2rem; }
  .dot { width: 0.85rem; height: 0.85rem; border-radius: 50%; background: var(--surface0); }
  .dot.done { background: var(--accent-text); }
  .day { font-size: 0.75rem; color: var(--text-muted); }
  .count { margin: 0; font-weight: 600; }
</style>
