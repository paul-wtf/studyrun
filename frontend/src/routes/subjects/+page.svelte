<script lang="ts">
  import { onMount } from 'svelte';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import type { Plan, Semester, Subject } from '#lib/api/models.ts';
  import { deDate } from '#lib/dates.ts';
  import { STATE_LABEL, subjectFacts } from '#lib/plan.ts';
  import ImportSubjects from '#lib/components/ImportSubjects.svelte';
  import SemesterDates from '#lib/components/SemesterDates.svelte';
  import SubjectSettings from '#lib/components/SubjectSettings.svelte';

  let subjects = $state<Subject[]>([]);
  let semesters = $state<Semester[]>([]);
  let plan = $state<Plan | null>(null);
  let loaded = $state(false);
  let error = $state('');

  const entryOf = (id: number) => plan?.entries.find((e) => e.subject_id === id);

  async function load() {
    try {
      [subjects, semesters, plan] = await Promise.all([
        api.get<Subject[]>('/api/subjects'),
        api.get<Semester[]>('/api/semesters'),
        api.get<Plan>('/api/plan')
      ]);
      loaded = true;
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    }
  }

  onMount(load);
</script>

<div class="stack">
  <h1>Fächer</h1>
  {#if error}<p class="error">{error}</p>{/if}
  {#if loaded && subjects.length === 0}
    <p class="note">Noch keine Fächer. Importiere den Prüfungsplan, dann erscheinen sie hier.</p>
  {/if}
  {#each subjects as s (s.id)}
    {@const entry = entryOf(s.id)}
    <article class="card subject" aria-label={s.name}>
      <div class="head">
        <h2><a href="/subjects/{s.id}">{s.name}</a></h2>
        {#if entry}<span class="chip">{STATE_LABEL[entry.state]}</span>{/if}
      </div>
      <p class="muted">{[subjectFacts(s), entry?.sitting ? `Prüfung am ${deDate(entry.sitting)}` : null].filter(Boolean).join(' · ')}</p>
      <details>
        <summary>Einstellungen</summary>
        <SubjectSettings subject={s} onchange={load} />
      </details>
    </article>
  {/each}
  {#if loaded}
    <SemesterDates {semesters} {subjects} onchange={load} />
  {/if}
  <ImportSubjects onimported={load} />
</div>

<style>
  .subject p { margin: 0; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap; }
  h2 { margin: 0; font-size: 1.1rem; min-width: 0; overflow-wrap: anywhere; }
  h2 a { color: var(--text); text-decoration: none; display: inline-flex; align-items: center; min-height: 44px; }
  h2 a:hover { color: var(--accent-text); }
  details { margin-top: 0.25rem; }
  summary { min-height: 44px; display: flex; align-items: center; }
</style>
