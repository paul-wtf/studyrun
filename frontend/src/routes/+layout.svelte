<script lang="ts">
  import '../app.css';
  import { sessionExpired } from '#lib/session.ts';
  import SessionExpired from '#lib/components/SessionExpired.svelte';

  let { children } = $props();
</script>

<div class="shell">
  <header>
    <a class="brand" href="/">studyrun</a>
    <nav aria-label="Hauptnavigation">
      <a href="/">Start</a>
      <a href="/modules">Module</a>
      <a href="/flags">Gemeldet</a>
      <a href="/costs">Kosten</a>
    </nav>
  </header>
  <main>
    {#if $sessionExpired}
      <SessionExpired />
    {:else}
      {@render children?.()}
    {/if}
  </main>
</div>

<style>
  .shell {
    max-width: 640px;
    margin: 0 auto;
    padding: 0.75rem 1rem 2rem;
    min-height: 100dvh;
  }
  header { padding: 0.25rem 0 1rem; }
  .brand { color: var(--muted); text-decoration: none; font-weight: 600; letter-spacing: 0.02em; }
  nav { display: flex; flex-wrap: wrap; gap: 0.25rem 1rem; margin-top: 0.25rem; }
  nav a { color: var(--accent); text-decoration: none; padding: 0.6rem 0; min-height: 44px; display: inline-flex; align-items: center; }
</style>
