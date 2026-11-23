<script lang="ts">
  import { onMount } from 'svelte';
  import { api, SessionExpiredError } from '#lib/api/client.ts';
  import { euro, hasRunToday } from '#lib/run.ts';

  interface Costs { today: { total: number }; cap_today: number }
  interface Module { booklets: { chapters: { ready: number } }[] }

  let costs = $state<Costs | null>(null);
  let ready = $state<boolean | null>(null);
  let resume = $state(false);
  let error = $state('');

  onMount(async () => {
    resume = hasRunToday();
    try {
      const [c, modules] = await Promise.all([
        api.get<Costs>('/api/costs'),
        api.get<Module[]>('/api/modules')
      ]);
      costs = c;
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
      <p>Lade ein Skript hoch und lass Aufgaben erzeugen, dann kann es losgehen.</p>
      <a class="btn primary block" href="/modules">Zu den Modulen</a>
    </div>
  {:else if ready !== null || resume || error}
    <a class="btn primary block start" href="/run">{resume ? 'Run fortsetzen' : 'Run starten'}</a>
  {/if}
  {#if error}<p class="error">{error}</p>{/if}
  {#if costs}
    <p class="muted">Heute {euro(costs.today.total)} von {euro(costs.cap_today)} $ ausgegeben</p>
  {/if}
</div>

<style>
  .start { min-height: 96px; font-size: 1.4rem; }
</style>
