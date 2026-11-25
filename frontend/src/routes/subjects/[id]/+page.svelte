<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import type { Attempt, AttemptStatus, CurrentRun, MockExam, MockSummary, Module, Plan, Progress, Subject } from '#lib/api/models.ts';
  import { deDate, deDateTime, today } from '#lib/dates.ts';
  import PlanEntryCard from '#lib/components/PlanEntryCard.svelte';
  import ProgressBars from '#lib/components/ProgressBars.svelte';
  import { attemptFor, subjectFacts } from '#lib/plan.ts';

  const ATTEMPT: Record<AttemptStatus, string> = {
    planned: 'Geplant',
    registered: 'Angemeldet',
    passed: 'Bestanden',
    failed: 'Nicht bestanden'
  };

  const id = Number(page.params.id);
  const day = today();

  let subject = $state<Subject | null>(null);
  let plan = $state<Plan | null>(null);
  let progress = $state<Progress | null>(null);
  let modules = $state<Module[]>([]);
  let runOpen = $state(false);
  let mocks = $state<MockSummary[]>([]);
  let openMock = $state<MockExam | null>(null);
  let error = $state('');
  let mockError = $state('');
  let busy = $state(false);

  const entry = $derived(plan?.entries.find((e) => e.subject_id === id));
  const mine = $derived(subject ? modules.filter((m) => subject?.module_ids.includes(m.id)) : []);
  const share = $derived(progress?.subjects.find((p) => p.subject_id === id));
  const attempts = $derived(subject ? [...subject.attempts].sort((a, b) => b.sitting.localeCompare(a.sitting)) : []);
  const onCard = $derived(subject && entry?.state === 'needs_result' ? attemptFor(subject, entry)?.id : undefined);
  const missingResult = (a: Attempt) => a.status === 'registered' && a.sitting < day;
  const pct = (n: number) => Math.round(n * 100);

  async function load() {
    try {
      const [s, p, pr, m, current, history] = await Promise.all([
        api.get<Subject>(`/api/subjects/${id}`),
        api.get<Plan>('/api/plan'),
        api.get<Progress>('/api/progress'),
        api.get<Module[]>('/api/modules'),
        api.get<CurrentRun>(`/api/runs/current?subject_id=${id}`),
        api.get<MockSummary[]>(`/api/subjects/${id}/mocks`)
      ]);
      const unfinished = history.find((h) => h.finished_at === null);
      openMock = unfinished ? await api.get<MockExam>(`/api/mock/${unfinished.id}`) : null;
      [subject, plan, progress, modules, mocks] = [s, p, pr, m, history];
      runOpen = current.run !== null && current.run.entries.length > 0;
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    }
  }

  async function mock() {
    busy = true;
    mockError = '';
    try {
      const exam = await api.post<MockExam>(`/api/subjects/${id}/mock`);
      await goto(`/mock/${exam.id}`);
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) mockError = errorText(e);
    } finally {
      busy = false;
    }
  }

  async function change(fn: () => Promise<unknown>) {
    busy = true;
    error = '';
    try {
      await fn();
      await load();
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    } finally {
      busy = false;
    }
  }

  const correct = (attemptId: number, status: AttemptStatus) => change(() => api.patch(`/api/attempts/${attemptId}`, { status }));
  const discard = (attemptId: number) => change(() => api.del(`/api/attempts/${attemptId}`));

  onMount(load);
</script>

<div class="stack">
  <p><a class="back" href="/subjects">Alle Fächer</a></p>
  {#if error}<p class="error">{error}</p>{/if}
  {#if subject}
    <h1>{subject.name}</h1>
    <p class="muted meta">
      {[subjectFacts(subject), subject.not_before ? `nicht vor dem ${deDate(subject.not_before)}` : null].filter(Boolean).join(' · ')}
    </p>

    <section class="card stack" aria-label="Lernen">
      <ProgressBars introduced={share?.introduced ?? subject.introduced_share} solid={share?.solid ?? 0} />
      <a class="btn primary block" href="/run?subject={id}">{runOpen ? 'Fach-Run fortsetzen' : 'Fach üben'}</a>
      {#if runOpen}
        <p class="muted">An dem Tag, an dem du ihn begonnen hast, hält der offene Fach-Run seine Fragen aus anderen Runs zurück.</p>
      {/if}
      {#if openMock}
        <a class="btn block" href="/mock/{openMock.id}">
          {openMock.finishing ? 'Auswertung abschließen' : openMock.expired ? 'Abgelaufen – Auswertung abschließen' : 'Bosskampf fortsetzen'}
        </a>
      {:else if subject.unlocked}
        <button type="button" class="block" disabled={busy} onclick={mock}>Bosskampf</button>
        <p class="muted">Probeprüfung über {subject.duration_minutes} Minuten, Auswertung erst am Ende, bestanden ab {subject.pass_mark} %.</p>
      {:else}
        <p class="muted">Der Bosskampf öffnet bei 80 % eingeführter Kapitel (jetzt {pct(subject.introduced_share)} %).</p>
      {/if}
      {#if mockError}<p class="error" role="alert">{mockError}</p>{/if}
    </section>

    {#if entry}
      <PlanEntryCard {entry} {subject} today={day} onchange={load} />
    {/if}

    <section class="card" aria-labelledby="modules-title">
      <h2 id="modules-title">Module</h2>
      {#if mine.length}
        <ul class="plain">
          {#each mine as m (m.id)}
            <li><a class="item" href="/modules/{m.id}">{m.name}</a></li>
          {/each}
        </ul>
      {:else}
        <p class="muted">Noch kein Modul zugeordnet. <a href="/modules">Zu den Modulen</a></p>
      {/if}
    </section>

    {#if attempts.length}
      <section class="card" aria-labelledby="attempts-title">
        <h2 id="attempts-title">Prüfungsversuche</h2>
        <ul class="plain rows">
          {#each attempts as a (a.id)}
            <li>
              <span class="date">{deDate(a.sitting)}</span>
              <span>{missingResult(a) ? 'Ergebnis fehlt' : ATTEMPT[a.status]}</span>
              {#if a.status === 'passed'}
                <button type="button" disabled={busy} onclick={() => correct(a.id, 'failed')}>Auf nicht bestanden ändern</button>
              {:else if a.status === 'failed'}
                <button type="button" disabled={busy} onclick={() => correct(a.id, 'passed')}>Auf bestanden ändern</button>
              {:else if missingResult(a) && a.id !== onCard}
                <span class="buttons">
                  <button type="button" disabled={busy} onclick={() => correct(a.id, 'passed')}>Bestanden</button>
                  <button type="button" disabled={busy} onclick={() => correct(a.id, 'failed')}>Nicht bestanden</button>
                </span>
              {:else if a.status === 'planned' && a.sitting < day}
                <button type="button" disabled={busy} onclick={() => discard(a.id)}>Verwerfen</button>
              {/if}
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if mocks.length}
      <section class="card" aria-labelledby="mocks-title">
        <h2 id="mocks-title">Bosskämpfe</h2>
        <ul class="plain rows">
          {#each mocks as m (m.id)}
            <li>
              <a class="item date" href="/mock/{m.id}">{deDateTime(m.started_at)}</a>
              {#if m.finished_at === null}
                <span class="muted">läuft</span>
              {:else}
                {#if m.score !== null}<span class="score">{m.score} %</span>{/if}
                {#if m.passed !== null}
                  <span class="chip" class:passed={m.passed} class:failed={!m.passed}>{m.passed ? 'Bestanden' : 'Nicht bestanden'}</span>
                {/if}
              {/if}
            </li>
          {/each}
        </ul>
      </section>
    {/if}
  {/if}
</div>

<style>
  .back { display: inline-flex; align-items: center; min-height: 44px; text-decoration: none; font-weight: 600; }
  h1 { overflow-wrap: anywhere; }
  .meta { margin-top: -0.25rem; }
  section p { margin: 0; }
  h2 { font-size: 1rem; color: var(--text-muted); margin: 0 0 0.5rem; }
  .plain { list-style: none; padding: 0; margin: 0; }
  .item { display: inline-flex; align-items: center; min-height: 44px; font-weight: 600; text-decoration: none; color: var(--text); }
  .item:hover { color: var(--accent-text); }
  .rows { display: grid; gap: 0.25rem; }
  .rows li { display: flex; flex-wrap: wrap; align-items: center; gap: 0 0.9rem; min-height: 44px; }
  .rows button { min-height: 44px; padding: 0.3rem 0.8rem; font-size: 0.85rem; margin-left: auto; }
  .buttons { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-left: auto; }
  .buttons button { margin-left: 0; }
  .date { font-variant-numeric: tabular-nums; }
  .score { font-weight: 700; font-variant-numeric: tabular-nums; }
  .passed { background: var(--success-soft); }
  .failed { background: var(--error-soft); }
</style>
