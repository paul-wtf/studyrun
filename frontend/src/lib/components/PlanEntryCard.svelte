<script lang="ts">
  import type { Snippet } from 'svelte';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import type { AttemptStatus, PlanEntry, Subject } from '#lib/api/models.ts';
  import { countdown, deDate } from '#lib/dates.ts';
  import { attemptFor, sittingChoices, STATE_LABEL } from '#lib/plan.ts';

  let {
    entry,
    subject,
    today,
    onchange,
    link = false,
    children
  }: { entry: PlanEntry; subject: Subject; today: string; onchange: () => void; link?: boolean; children?: Snippet } = $props();

  let busy = $state(false);
  let error = $state('');
  let choosing = $state(false);
  let asking = $state(false);
  let choice = $state('');

  const coming = $derived(['open', 'planned', 'registered'].includes(entry.state));
  const examDay = $derived(entry.state === 'registered' && entry.sitting !== null && entry.sitting <= today);
  const choices = $derived(sittingChoices(subject, today));
  const picked = $derived(choices.find((c) => c.date === choice));
  const attempt = $derived(attemptFor(subject, entry));
  const studying = $derived(
    coming && entry.study_from !== null && entry.study_until !== null && entry.study_until > entry.study_from
  );

  async function act(fn: () => Promise<unknown>) {
    busy = true;
    error = '';
    try {
      await fn();
      choosing = false;
      asking = false;
      onchange();
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    } finally {
      busy = false;
    }
  }

  const book = (sitting: string, status: 'planned' | 'registered') =>
    act(() => api.post(`/api/subjects/${subject.id}/attempts`, { sitting, status }));
  const result = (status: AttemptStatus) => act(() => api.patch(`/api/attempts/${attempt?.id}`, { status }));
  const drop = () => act(() => api.del(`/api/attempts/${attempt?.id}`));

  function choose() {
    choice = choices.find((c) => !c.closed && c.date !== entry.sitting)?.date ?? choices[0]?.date ?? '';
    choosing = true;
  }
</script>

<article class="card stack entry" aria-label={entry.subject_name}>
  <div class="head">
    {#if link}
      <h2><a href="/subjects/{entry.subject_id}">{entry.subject_name}</a></h2>
    {:else}
      <h2>Prüfungstermin</h2>
    {/if}
    <span class="chip state-{entry.state}">{STATE_LABEL[entry.state]}</span>
  </div>

  {#if entry.sitting}
    <p class="when">
      {entry.state === 'passed' ? 'Bestanden am' : 'Prüfung am'}
      <strong>{deDate(entry.sitting)}</strong>
      {#if coming && entry.sitting >= today}<span class="muted">· {countdown(today, entry.sitting)}</span>{/if}
    </p>
  {:else if entry.state === 'open'}
    <p class="muted">Kein Termin vorgeschlagen.</p>
  {/if}
  {#if entry.register_by && entry.register_by >= today}
    <p class="deadline">Anmelden bis {deDate(entry.register_by)}</p>
  {/if}
  {#if coming && entry.sitting && !entry.feasible}
    <p class="warn">Beim aktuellen Tempo wird es knapp.</p>
  {/if}
  {#if studying && entry.study_from && entry.study_until}
    <p class="muted">Lernzeit {deDate(entry.study_from)} bis {deDate(entry.study_until)}</p>
  {/if}

  {@render children?.()}

  {#if entry.state === 'no_material'}
    <p><a class="fix" href="/modules">Module zuordnen</a></p>
  {:else if entry.state === 'not_plannable'}
    <p><a class="fix" href="/subjects#semester">Semesterstart eintragen</a></p>
  {:else if entry.state === 'sittings_pending'}
    <p class="muted">Sobald neue Termine importiert sind, wird das Fach eingeplant.</p>
  {/if}

  {#if examDay || asking}
    <div class="actions">
      <button type="button" class="primary" disabled={busy || !attempt} onclick={() => result('passed')}>Bestanden</button>
      <button type="button" disabled={busy || !attempt} onclick={() => result('failed')}>Nicht bestanden</button>
    </div>
  {:else if entry.state === 'needs_result'}
    <div class="actions">
      <button type="button" class="primary" onclick={() => (asking = true)}>Ergebnis eintragen</button>
    </div>
  {:else if coming && !choosing}
    <div class="actions">
      {#if entry.state !== 'registered' && entry.sitting}
        <button type="button" class="primary" disabled={busy} onclick={() => entry.sitting && book(entry.sitting, 'registered')}>Angemeldet</button>
      {/if}
      {#if choices.length}
        <button type="button" disabled={busy} onclick={choose}>Anderen Termin wählen</button>
      {/if}
      {#if entry.state === 'planned' && attempt}
        <button type="button" disabled={busy} onclick={drop}>Eigenen Termin verwerfen</button>
      {/if}
    </div>
  {/if}

  {#if choosing}
    <div class="choose stack">
      <label>
        Termin
        <select bind:value={choice}>
          {#each choices as c (c.date)}
            <option value={c.date}>{deDate(c.date)}{c.closed ? ' (Anmeldung vorbei)' : ''}</option>
          {/each}
        </select>
      </label>
      <div class="actions">
        <button type="button" class="primary" disabled={busy || !picked || picked.closed} onclick={() => book(choice, 'planned')}>Termin übernehmen</button>
        <button type="button" disabled={busy || !picked} onclick={() => book(choice, 'registered')}>Dort angemeldet</button>
        <button type="button" disabled={busy} onclick={() => (choosing = false)}>Abbrechen</button>
      </div>
    </div>
  {/if}
  {#if error}<p class="error" role="alert">{error}</p>{/if}
</article>

<style>
  .entry p { margin: 0; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap; }
  h2 { margin: 0; font-size: 1.1rem; min-width: 0; overflow-wrap: anywhere; }
  h2 a { color: var(--text); text-decoration: none; display: inline-flex; align-items: center; min-height: 44px; }
  h2 a:hover { color: var(--accent-text); }
  .state-registered, .state-passed { background: var(--success-soft); }
  .state-needs_result, .state-no_material, .state-not_plannable { background: var(--error-soft); }
  .state-open { background: var(--accent-soft); }
  .deadline { font-weight: 600; color: var(--accent-text); }
  .warn { color: var(--error); }
  .fix { display: inline-flex; align-items: center; min-height: 44px; font-weight: 600; }
  .actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .actions button { min-height: 44px; }
  @media (max-width: 600px) {
    .actions button { flex: 1 1 100%; }
  }
</style>
