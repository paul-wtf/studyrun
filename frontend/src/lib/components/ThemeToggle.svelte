<script lang="ts">
  import { theme, toggleTheme } from '#lib/stores/theme.ts';

  let label = $derived($theme === 'mocha' ? 'Helles Design' : 'Dunkles Design');
</script>

<button type="button" class="theme-toggle" onclick={toggleTheme} aria-label={label} title={label}>
  <span aria-hidden="true">{$theme === 'mocha' ? '☾' : '☀'}</span>
</button>

<style>
  .theme-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    min-height: 44px;
    height: 44px;
    padding: 0;
    background: var(--surface0);
    color: var(--text);
    border: 0;
    border-radius: var(--r-sm);
    font-size: 1rem;
    cursor: pointer;
    transition: background var(--dur-fast) var(--ease-out);
  }
  .theme-toggle:hover {
    background: var(--surface1);
  }
</style>
