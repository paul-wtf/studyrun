<script lang="ts">
  import type { Conflict } from '#lib/api/models.ts';

  let { conflicts }: { conflicts: Conflict[] } = $props();
</script>

{#if conflicts.length}
  <section class="card conflicts" aria-labelledby="conflicts-title">
    <h2 id="conflicts-title">Konflikte</h2>
    <ul>
      {#each conflicts as c, i (i)}
        <li>
          <a class="subject" href="/subjects/{c.subject_id}">{c.subject_name}</a>
          <span>{c.message}</span>
        </li>
      {/each}
    </ul>
  </section>
{/if}

<style>
  .conflicts { box-shadow: var(--glass-shadow), inset 4px 0 0 var(--error); }
  h2 { color: var(--error); font-size: 1rem; }
  ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 0.6rem; }
  li { display: grid; gap: 0.1rem; }
  .subject { font-weight: 600; color: var(--text); text-decoration: none; display: inline-flex; min-height: 44px; align-items: center; width: fit-content; }
  .subject:hover { color: var(--accent-text); }
</style>
