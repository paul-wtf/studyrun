<script lang="ts">
  import { onMount } from 'svelte';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import { euro } from '#lib/format.ts';

  import type { Costs, Period } from '#lib/api/models.ts';

  const FEATURES: [string, string][] = [
    ['generate', 'Erzeugung'],
    ['verify', 'Prüfung'],
    ['grade', 'Bewertung'],
    ['tutor', 'Tutor']
  ];

  let costs = $state<Costs | null>(null);
  let error = $state('');

  onMount(async () => {
    try {
      costs = await api.get<Costs>('/api/costs');
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    }
  });

  const usd = (n: number) => `${euro(n)} $`;
</script>

<div class="stack">
  <h1>Kosten</h1>
  {#if error}<p class="error">{error}</p>{/if}
  {#if costs}
    {#each [['Heute', costs.today], ['Dieser Monat', costs.month]] as [title, period] (title)}
      <section class="card stack" aria-label={title as string}>
        <h2>{title}</h2>
        <p class="total">{usd((period as Period).total)}</p>
        <dl>
          {#each FEATURES as [key, label] (key)}
            <dt>{label}</dt>
            <dd>{usd((period as Period).by_feature[key] ?? 0)}</dd>
          {/each}
        </dl>
      </section>
    {/each}
    <section class="card stack" aria-label="Limits">
      <p><span>Tageslimit für Bewertung und Tutor: {usd(costs.cap_today)}</span><br /><span class="muted">Noch frei: {usd(costs.remaining_today)}</span></p>
      <p><span>Erzeugungsbudget heute: {usd(costs.generation_budget_today)}</span><br /><span class="muted">Noch frei: {usd(costs.generation_remaining_today)}</span></p>
    </section>
  {/if}
</div>

<style>
  h2 { font-size: 1rem; color: var(--text-muted); margin: 0; }
  .total { font-family: var(--font-display); font-size: 2rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; margin: 0.25rem 0 0; font-variant-numeric: tabular-nums; }
  dl { display: grid; grid-template-columns: 1fr auto; gap: 0.25rem 1rem; margin-bottom: 0; }
  dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
  dt { color: var(--text-muted); }
  p { margin-bottom: 0; }
</style>
