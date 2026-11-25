<script lang="ts">
  import { onMount } from 'svelte';
  import { api, SessionExpiredError } from '#lib/api/client.ts';
  import { euro } from '#lib/format.ts';
  import { countdown, deDate, today } from '#lib/dates.ts';
  import { deadlinesSoon, focusSubject, nextExam, STATE_LABEL } from '#lib/plan.ts';
  import WeekDots from '#lib/components/WeekDots.svelte';

  import type { Costs, CurrentRun, Module, OpenRun, Plan, Progress } from '#lib/api/models.ts';

  let costs = $state<Costs | null>(null);
  let ready = $state<boolean | null>(null);
  let resume = $state(false);
  let error = $state('');
  let plan = $state<Plan | null>(null);
  let progress = $state<Progress | null>(null);
  let openRuns = $state<OpenRun[]>([]);

  const day = today();
  const spent = (features: string[]) =>
    features.reduce((sum, f) => sum + (costs?.today.by_feature[f] ?? 0), 0);
  const grading = $derived(spent(['grade', 'tutor']));
  const generation = $derived(spent(['generate', 'verify']));
  const next = $derived(plan ? nextExam(plan.entries, day) : undefined);
  const deadlines = $derived(plan ? deadlinesSoon(plan.entries, day) : []);
  const results = $derived(plan?.entries.filter((e) => e.state === 'needs_result') ?? []);
  const missing = $derived(plan?.conflicts.filter((c) => c.kind === 'needs_result') ?? []);
  const focusEntry = $derived(plan ? focusSubject(plan) : undefined);
  const focus = $derived(openRuns.some((r) => r.subject_id === focusEntry?.subject_id) ? undefined : focusEntry);
  const questions = (n: number) => (n === 1 ? '1 Frage offen' : `${n} Fragen offen`);

  const hasEntries = (run: CurrentRun['run']) => run !== null && run.entries.length > 0;

  async function loadDaily() {
    try {
      const [c, modules, current] = await Promise.all([
        api.get<Costs>('/api/costs'),
        api.get<Module[]>('/api/modules'),
        api.get<CurrentRun>('/api/runs/current')
      ]);
      costs = c;
      resume = hasEntries(current.run);
      ready = modules.some((m) => m.booklets.some((b) => b.chapters.ready > 0));
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = 'Daten konnten nicht geladen werden.';
    }
  }

  async function loadPlan() {
    try {
      const [p, pr, runs] = await Promise.all([
        api.get<Plan>('/api/plan'),
        api.get<Progress>('/api/progress'),
        api.get<OpenRun[]>('/api/runs/open')
      ]);
      [plan, progress, openRuns] = [p, pr, runs];
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = 'Daten konnten nicht geladen werden.';
    }
  }

  onMount(() => {
    void loadDaily();
    void loadPlan();
  });
</script>

<div class="stack">
  {#if deadlines.length}
    <section class="card banner" aria-labelledby="deadlines-title">
      <h2 id="deadlines-title">Anmeldefristen</h2>
      <ul>
        {#each deadlines as d (d.subject_id)}
          <li>
            <strong>{d.subject_name}</strong>: anmelden bis {deDate(d.register_by ?? '')}
            <span class="muted">({countdown(day, d.register_by ?? day)}, Prüfung am {deDate(d.sitting ?? '')})</span>
          </li>
        {/each}
      </ul>
      <a class="go" href="/plan">Zum Plan</a>
    </section>
  {/if}
  {#each results as r (r.subject_id)}
    <p class="note">Ergebnis eintragen: {r.subject_name} (Prüfung am {deDate(r.sitting ?? '')}). <a href="/plan">Zum Plan</a></p>
  {/each}
  {#each missing as m, i (i)}
    <p class="note">Ergebnis eintragen: {m.subject_name}. {m.message} <a href="/subjects/{m.subject_id}">Zum Fach</a></p>
  {/each}

  {#if ready === false && !resume}
    <div class="card stack">
      <h1>Noch nichts zu lernen</h1>
      <p>Lade ein Heft hoch und lass Fragen erzeugen, dann kann es losgehen.</p>
      <a class="btn primary block" href="/modules">Zu den Modulen</a>
    </div>
  {:else if ready !== null || resume || error}
    <a class="btn primary block start" href="/run">{resume ? 'Run fortsetzen' : 'Run starten'}</a>
  {/if}
  {#if openRuns.length}
    <section class="card stack open-runs" aria-labelledby="open-runs-title">
      <h2 id="open-runs-title">Offene Fach-Runs</h2>
      <ul>
        {#each openRuns as r (r.id)}
          <li>
            <a class="btn block" href="/run?subject={r.subject_id}">Fach-Run fortsetzen: {r.subject_name}</a>
            <span class="muted">{questions(r.open_items)}, begonnen am {deDate(today(new Date(r.created_at)))}</span>
          </li>
        {/each}
      </ul>
      <p class="muted">Brauchst du einen nicht mehr, schließ ihn im Run mit „Beenden“ ab.</p>
    </section>
  {/if}
  {#if focus}
    <a class="btn block" href="/run?subject={focus.subject_id}">Fach üben: {focus.subject_name}</a>
  {/if}
  {#if error}<p class="error">{error}</p>{/if}

  {#if next}
    <section class="card next" aria-labelledby="next-title">
      <div class="head">
        <h2 id="next-title">Nächste Prüfung</h2>
        <span class="chip">{STATE_LABEL[next.state]}</span>
      </div>
      <p class="subject"><a href="/subjects/{next.subject_id}">{next.subject_name}</a></p>
      <p>Am <strong>{deDate(next.sitting ?? '')}</strong> <span class="muted">· {countdown(day, next.sitting ?? day)}</span></p>
    </section>
  {/if}
  {#if progress}
    <section class="card" aria-labelledby="week-title">
      <h2 id="week-title">Wochenziel</h2>
      <WeekDots week={progress.week} />
    </section>
  {/if}
  {#if costs}
    <div class="card spend">
      <p class="muted">Bewertung heute: {euro(grading)} von {euro(costs.cap_today)} $</p>
      {#if generation > 0}<p class="muted">Erzeugung heute: {euro(generation)} $</p>{/if}
    </div>
  {/if}
</div>

<style>
  .start { min-height: 96px; font-size: 1.4rem; border-radius: var(--r-lg); box-shadow: var(--glass-shadow); }
  .spend { padding: 0.9rem 1.25rem; }
  .spend p { margin: 0; }
  h2 { font-size: 1rem; color: var(--text-muted); margin: 0 0 0.5rem; }
  .banner { box-shadow: var(--glass-shadow), inset 4px 0 0 var(--accent-text); }
  .banner h2 { color: var(--accent-text); }
  .banner ul { list-style: none; padding: 0; margin: 0 0 0.25rem; display: grid; gap: 0.35rem; }
  .open-runs ul { list-style: none; padding: 0; display: grid; gap: 0.75rem; }
  .open-runs li { display: grid; gap: 0.25rem; }
  .go { display: inline-flex; align-items: center; min-height: 44px; font-weight: 600; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
  .head h2 { margin: 0; }
  .next p { margin: 0; }
  .subject { font-size: 1.2rem; font-weight: 700; overflow-wrap: anywhere; }
  .subject a { color: var(--text); text-decoration: none; display: inline-flex; min-height: 44px; align-items: center; }
  .subject a:hover { color: var(--accent-text); }
</style>
