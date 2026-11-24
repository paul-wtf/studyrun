<script lang="ts">
  import '@fontsource-variable/jetbrains-mono';
  import '#lib/theme/tokens.css';
  import '../app.css';
  import { sessionExpired } from '#lib/session.ts';
  import SessionExpired from '#lib/components/SessionExpired.svelte';
  import Header from '#lib/components/Header.svelte';

  let { children } = $props();
</script>

<Header />
<main>
  {#if $sessionExpired}
    <SessionExpired />
  {:else}
    {@render children?.()}
  {/if}
</main>

<div class="zen-frame" aria-hidden="true"><i></i><i></i><i></i><i></i></div>

<style>
  main {
    max-width: 640px;
    margin: 0 auto;
    padding: calc(var(--viewport-r) + 16px) 1rem 2rem;
    min-height: calc(100dvh - var(--bar-h));
  }
  .zen-frame {
    position: fixed;
    inset: 0;
    border: solid var(--mantle);
    border-width: var(--viewport-top) var(--frame) var(--frame);
    pointer-events: none;
    z-index: 60;
  }
  .zen-frame i {
    position: absolute;
    width: var(--viewport-r);
    height: var(--viewport-r);
  }
  .zen-frame i:nth-child(1) {
    top: 0;
    left: 0;
    background: radial-gradient(circle at 100% 100%, transparent calc(var(--viewport-r) - 0.5px), var(--mantle) var(--viewport-r));
  }
  .zen-frame i:nth-child(2) {
    top: 0;
    right: 0;
    background: radial-gradient(circle at 0% 100%, transparent calc(var(--viewport-r) - 0.5px), var(--mantle) var(--viewport-r));
  }
  .zen-frame i:nth-child(3) {
    bottom: 0;
    left: 0;
    background: radial-gradient(circle at 100% 0%, transparent calc(var(--viewport-r) - 0.5px), var(--mantle) var(--viewport-r));
  }
  .zen-frame i:nth-child(4) {
    bottom: 0;
    right: 0;
    background: radial-gradient(circle at 0% 0%, transparent calc(var(--viewport-r) - 0.5px), var(--mantle) var(--viewport-r));
  }
</style>
