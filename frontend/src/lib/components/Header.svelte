<script lang="ts">
  import ThemeToggle from './ThemeToggle.svelte';
</script>

<header class="zen-bar">
  <a class="brand" href="/">
    <span class="mark" aria-hidden="true"></span>
    studyrun
  </a>
  <nav aria-label="Hauptnavigation">
    <a href="/">Start</a>
    <a href="/modules">Module</a>
    <a href="/flags">Gemeldet</a>
    <a href="/costs">Kosten</a>
  </nav>
  <div class="actions"><ThemeToggle /></div>
</header>

<style>
  /* This bar is the top edge of the zen frame: --viewport-top must equal its
     rendered height, or the frame's corners drift off the bar. Bound to the
     bar being in the DOM, not to this stylesheet being loaded. */
  :global(:root:has(.zen-bar)) {
    --viewport-top: var(--bar-h);
  }

  header {
    position: sticky;
    top: 0;
    z-index: 70;
    height: var(--bar-h);
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 0 1.25rem;
    padding: 0 clamp(1rem, 4vw, 2rem);
    background: var(--mantle);
    overflow: hidden;
  }
  .brand {
    display: inline-flex;
    align-items: center;
    gap: 0.55rem;
    min-height: 44px;
    font-family: var(--font-display);
    font-weight: 700;
    font-size: 1.35rem;
    line-height: 1;
    color: var(--text);
    text-decoration: none;
    letter-spacing: -0.02em;
  }
  .mark {
    width: 0.7rem;
    height: 0.7rem;
    border-radius: 2px;
    background: var(--accent);
  }
  nav {
    display: flex;
    gap: 0 1.25rem;
    overflow-x: auto;
    scrollbar-width: none;
  }
  nav::-webkit-scrollbar {
    display: none;
  }
  nav a {
    display: inline-flex;
    align-items: center;
    flex-shrink: 0;
    min-height: 44px;
    color: var(--text-muted);
    text-decoration: none;
    font-size: 0.95rem;
    transition: color var(--dur-fast) var(--ease-out);
  }
  nav a:hover {
    color: var(--accent-text);
  }

  /* Two fixed rows below 1000px (brand and toggle, then the links); --bar-h
     in tokens.css carries the matching height. */
  @media (max-width: 999px) {
    header {
      grid-template-columns: minmax(0, 1fr) auto;
      grid-template-rows: 1fr 1fr;
      gap: 0 0.75rem;
      padding: 0.25rem clamp(1rem, 4vw, 1.5rem);
    }
    nav {
      grid-column: 1 / -1;
      grid-row: 2;
    }
    .actions {
      grid-column: 2;
      grid-row: 1;
    }
  }
</style>
