<script lang="ts">
  import { api, errorText } from '#lib/api/client.ts';
  import type { FreeResult, ObjectiveResult } from '#lib/api/models.ts';

  let {
    itemId,
    source,
    result,
    onnext
  }: { itemId: number; source: string; result: ObjectiveResult | FreeResult; onnext: () => void } = $props();

  const REASONS = [
    ['wrong', 'Inhaltlich falsch'],
    ['not_in_course', 'Nicht im Kurs'],
    ['unclear', 'Unklar']
  ] as const;

  let menuOpen = $state(false);
  let flagged = $state(false);
  let error = $state('');

  async function flag(reason: string) {
    try {
      await api.post(`/api/items/${itemId}/flag`, { reason });
      flagged = true;
      menuOpen = false;
    } catch (e) {
      error = errorText(e);
    }
  }
</script>

<div class="card stack" aria-live="polite">
  {#if 'correct' in result}
    <h2 class={result.correct ? 'good' : 'bad'}>{result.correct ? 'Richtig' : 'Falsch'}</h2>
    {#if !result.correct}<p>Richtige Antwort: <strong>{result.expected}</strong></p>{/if}
    {#if result.explanation}<p>{result.explanation}</p>{/if}
  {:else}
    <h2>{result.score} von 100</h2>
    <p>{result.feedback}</p>
    {#if result.missing.length}
      <p class="muted">Es fehlt noch:</p>
      <ul>
        {#each result.missing as point}
          <li>{point}</li>
        {/each}
      </ul>
    {/if}
    <details>
      <summary>Musterantwort</summary>
      <p>{result.model_answer}</p>
    </details>
  {/if}
  <a href={source} target="_blank" rel="noopener">Im Skript nachlesen</a>
  {#if error}<p class="error">{error}</p>{/if}
  <div class="actions">
    {#if flagged}
      <span class="muted">Gemeldet</span>
    {:else}
      <button onclick={() => (menuOpen = !menuOpen)} aria-expanded={menuOpen}>Melden</button>
    {/if}
    <button class="primary grow" onclick={onnext}>Weiter</button>
  </div>
  {#if menuOpen}
    <div class="menu">
      {#each REASONS as [reason, label]}
        <button onclick={() => flag(reason)}>{label}</button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .good { color: var(--good); }
  .bad { color: var(--bad); }
  .actions { display: flex; gap: 0.75rem; align-items: center; }
  .grow { flex: 1; }
  .menu { display: grid; gap: 0.5rem; }
</style>
