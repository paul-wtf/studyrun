<script lang="ts">
  import { onMount } from 'svelte';
  import { api, SessionExpiredError } from '#lib/api/client.ts';
  import { euro } from '#lib/format.ts';

  import type { Costs, Module } from '#lib/api/models.ts';

  let costs = $state<Costs | null>(null);
  let ready = $state<boolean | null>(null);
  let resume = $state(false);
  let error = $state('');

  const spent = (features: string[]) =>
    features.reduce((sum, f) => sum + (costs?.today.by_feature[f] ?? 0), 0);
  const grading = $derived(spent(['grade', 'tutor']));
  const generation = $derived(spent(['generate', 'verify']));

  onMount(async () => {
    try {
      const [c, modules, current] = await Promise.all([
        api.get<Costs>('/api/costs'),
        api.get<Module[]>('/api/modules'),
        api.get<{ run: { entries: unknown[] } | null }>('/api/runs/current')
      ]);
      costs = c;
      resume = current.run !== null && current.run.entries.length > 0;
      ready = modules.some((m) => m.booklets.some((b) => b.chapters.ready > 0));
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = 'Daten konnten nicht geladen werden.';
    }
  });
</script>

<div class="stack">
  {#if ready === false && !resume}
    <div class="card stack">
      <h1>Noch nichts zu lernen</h1>
      <p>Lade ein Heft hoch und lass Fragen erzeugen, dann kann es losgehen.</p>
      <a class="btn primary block" href="/modules">Zu den Modulen</a>
    </div>
  {:else if ready !== null || resume || error}
    <a class="btn primary block start" href="/run">{resume ? 'Run fortsetzen' : 'Run starten'}</a>
  {/if}
  {#if error}<p class="error">{error}</p>{/if}
  {#if costs}
    <p class="muted">Bewertung heute: {euro(grading)} von {euro(costs.cap_today)} $</p>
    {#if generation > 0}<p class="muted">Erzeugung heute: {euro(generation)} $</p>{/if}
  {/if}
</div>

<style>
  .start { min-height: 96px; font-size: 1.4rem; }
</style>
