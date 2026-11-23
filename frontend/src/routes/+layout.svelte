<script lang="ts">
  import '../app.css';
  import { sessionExpired } from '#lib/session.ts';
  import SessionExpired from '#lib/components/SessionExpired.svelte';

  let { children } = $props();
</script>

<div class="shell">
  <header><a href="/">studyrun</a></header>
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
  header a { color: var(--muted); text-decoration: none; font-weight: 600; letter-spacing: 0.02em; }
</style>
