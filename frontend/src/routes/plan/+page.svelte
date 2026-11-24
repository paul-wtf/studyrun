<script lang="ts">
  import { onMount } from 'svelte';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import type { Plan, PlanEntry, Progress, Subject } from '#lib/api/models.ts';
  import { deDate, deShort, monthLabel, today } from '#lib/dates.ts';
  import { STATE_LABEL } from '#lib/plan.ts';
  import ConflictList from '#lib/components/ConflictList.svelte';
  import PlanEntryCard from '#lib/components/PlanEntryCard.svelte';
  import ProgressBars from '#lib/components/ProgressBars.svelte';

  let plan = $state<Plan | null>(null);
  let subjects = $state<Subject[]>([]);
  let progress = $state<Progress | null>(null);
  let error = $state('');

  const day = today();
  const TAKEN = ['open', 'planned', 'registered'];
  const LATER: PlanEntry['state'][] = ['needs_result', 'open', 'planned', 'registered', 'no_material', 'not_plannable', 'sittings_pending', 'passed'];

  const ordered = $derived.by(() => {
    if (!plan) return [];
    const rank = new Map(plan.order.map((id, i) => [id, i]));
    return [...plan.entries].sort(
      (a, b) =>
        (rank.get(a.subject_id) ?? Infinity) - (rank.get(b.subject_id) ?? Infinity) ||
        LATER.indexOf(a.state) - LATER.indexOf(b.state) ||
        (a.sitting ?? '9999').localeCompare(b.sitting ?? '9999') ||
        a.subject_name.localeCompare(b.subject_name)
    );
  });

  interface Slot {
    date: string;
    subjects: { id: number; name: string; taken: PlanEntry | undefined }[];
  }

  const months = $derived.by(() => {
    if (!plan) return [];
    const entries = new Map(plan.entries.map((e) => [e.subject_id, e]));
    const slots = new Map<string, Slot>();
    for (const s of subjects) {
      for (const date of s.sittings) {
        if (date < day) continue;
        const slot = slots.get(date) ?? { date, subjects: [] };
        const entry = entries.get(s.id);
        slot.subjects.push({ id: s.id, name: s.name, taken: entry?.sitting === date && TAKEN.includes(entry.state) ? entry : undefined });
        slots.set(date, slot);
      }
    }
    const groups = new Map<string, Slot[]>();
    for (const slot of [...slots.values()].sort((a, b) => a.date.localeCompare(b.date))) {
      slot.subjects.sort((a, b) => Number(!!b.taken) - Number(!!a.taken) || a.name.localeCompare(b.name));
      const key = slot.date.slice(0, 7);
      groups.set(key, [...(groups.get(key) ?? []), slot]);
    }
    return [...groups.values()];
  });

  const subjectOf = (id: number) => subjects.find((s) => s.id === id);
  const progressOf = (id: number) => progress?.subjects.find((p) => p.subject_id === id);
  const pace = (n: number) => n.toLocaleString('de-DE', { maximumFractionDigits: 1 });

  async function load() {
    try {
      [plan, subjects, progress] = await Promise.all([
        api.get<Plan>('/api/plan'),
        api.get<Subject[]>('/api/subjects'),
        api.get<Progress>('/api/progress')
      ]);
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    }
  }

  onMount(load);
</script>

<div class="stack">
  <h1>Prüfungsplan</h1>
  {#if error}<p class="error">{error}</p>{/if}
  {#if plan}
    <ConflictList conflicts={plan.conflicts} />
    {#if plan.entries.length === 0}
      <div class="card stack">
        <p>Noch keine Fächer im Plan.</p>
        <a class="btn primary block" href="/subjects">Prüfungsplan importieren</a>
      </div>
    {:else}
      <p class="note">Tempo: {pace(plan.pace_per_day)} neue Fragen pro Lerntag. Höchstens eine Prüfung pro Monat, Anmeldung bis 21 Tage vorher.</p>
      {#if months.length}
        <section class="card timeline" aria-labelledby="timeline-title">
          <h2 id="timeline-title">Termine</h2>
          {#each months as slots (slots[0].date.slice(0, 7))}
            <h3>{monthLabel(slots[0].date)}</h3>
            <ul>
              {#each slots as slot (slot.date)}
                <li aria-label={deDate(slot.date)}>
                  <span class="date">{deShort(slot.date)}</span>
                  <span class="names">
                    {#each slot.subjects as s (s.id)}
                      <span class="name" class:taken={s.taken}>
                        <span>{s.name}</span>
                        {#if s.taken}<span class="chip state-{s.taken.state}">{STATE_LABEL[s.taken.state]}</span>{/if}
                      </span>
                    {/each}
                  </span>
                </li>
              {/each}
            </ul>
          {/each}
        </section>
      {/if}
      {#each ordered as entry (entry.subject_id)}
        {@const subject = subjectOf(entry.subject_id)}
        {#if subject}
          <PlanEntryCard {entry} {subject} today={day} onchange={load} link>
            <ProgressBars introduced={progressOf(entry.subject_id)?.introduced ?? subject.introduced_share} solid={progressOf(entry.subject_id)?.solid ?? 0} />
          </PlanEntryCard>
        {/if}
      {/each}
    {/if}
  {/if}
</div>

<style>
  h2 { font-size: 1rem; color: var(--text-muted); margin: 0 0 0.25rem; }
  h3 { font-size: 0.85rem; font-weight: 600; color: var(--text-muted); margin: 0.9rem 0 0.35rem; text-transform: uppercase; letter-spacing: 0.04em; }
  .timeline ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 0.35rem; }
  .timeline li { display: grid; grid-template-columns: 3.5rem minmax(0, 1fr); gap: 0.75rem; align-items: baseline; }
  .date { font-variant-numeric: tabular-nums; font-weight: 600; }
  .names { display: flex; flex-wrap: wrap; gap: 0.25rem 0.9rem; }
  .name { color: var(--text-muted); display: inline-flex; flex-wrap: wrap; align-items: center; gap: 0.1rem 0.4rem; overflow-wrap: break-word; min-width: 0; }
  .name.taken { color: var(--text); font-weight: 600; }
  .state-registered { background: var(--success-soft); }
  .state-open { background: var(--accent-soft); }
</style>
