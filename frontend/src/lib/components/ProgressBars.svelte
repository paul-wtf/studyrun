<script lang="ts">
  let { introduced, solid }: { introduced: number; solid: number } = $props();

  const bars = $derived([
    ['Eingeführt', Math.round(introduced * 100)],
    ['Gefestigt', Math.round(solid * 100)]
  ] as const);
</script>

<div class="bars">
  {#each bars as [label, pct] (label)}
    <div class="bar-row">
      <span class="label" aria-hidden="true">{label}</span>
      <div class="track">
        <div class="bar" role="progressbar" aria-label={label} aria-valuemin="0" aria-valuemax="100" aria-valuenow={pct}>
          <div class="fill" style:width="{pct}%"></div>
        </div>
        <span class="pct">{pct} %</span>
      </div>
    </div>
  {/each}
</div>

<style>
  .bars { display: grid; gap: 0.4rem; margin: 0; }
  .bar-row { display: grid; grid-template-columns: 6.5rem 1fr; align-items: center; gap: 0.75rem; }
  .label { color: var(--text-muted); font-size: 0.85rem; }
  .track { display: flex; align-items: center; gap: 0.6rem; margin: 0; }
  .bar { flex: 1; height: 8px; border-radius: 2px; background: var(--surface0); overflow: hidden; }
  .fill { height: 100%; background: var(--accent); }
  .pct { min-width: 3.2rem; text-align: right; font-size: 0.85rem; font-variant-numeric: tabular-nums; }
</style>
