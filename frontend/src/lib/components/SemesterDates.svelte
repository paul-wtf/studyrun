<script lang="ts">
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import type { Semester, Subject } from '#lib/api/models.ts';

  let { semesters, subjects, onchange }: { semesters: Semester[]; subjects: Subject[]; onchange: () => void } = $props();

  let drafts = $state<Record<string, string>>({});
  let busy = $state(false);
  let error = $state('');

  const order = (label: string): [number, string] => {
    const m = /^(\d+)(.*)$/.exec(label);
    return m ? [Number(m[1]), m[2]] : [Number.MAX_SAFE_INTEGER, label];
  };
  const bySemester = (a: string, b: string) => {
    const [na, ra] = order(a);
    const [nb, rb] = order(b);
    return na - nb || ra.localeCompare(rb);
  };

  const known = $derived(Object.fromEntries(semesters.map((s) => [s.label, s.starts_on])));
  const labels = $derived(
    [
      ...new Set([
        ...semesters.map((s) => s.label),
        ...subjects.map((s) => s.earliest_semester),
        ...subjects.flatMap((s) => (s.recommended_semester === null ? [] : [`${s.recommended_semester}a`]))
      ])
    ].sort(bySemester)
  );

  const value = (label: string) => drafts[label] ?? known[label] ?? '';

  async function save(label: string) {
    const starts_on = value(label);
    if (!starts_on) return;
    busy = true;
    error = '';
    try {
      await api.put(`/api/semesters/${encodeURIComponent(label)}`, { starts_on });
      delete drafts[label];
      onchange();
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    } finally {
      busy = false;
    }
  }
</script>

<section class="card stack" id="semester" aria-labelledby="semester-title">
  <h2 id="semester-title">Semesterstarts</h2>
  <p class="muted">Ab dem Start des frühesten Semesters ist ein Fach zugelassen; das empfohlene Semester gibt die Zielrichtung vor.</p>
  {#if labels.length === 0}
    <p class="muted">Noch keine Semester. Sie kommen mit dem Import.</p>
  {/if}
  <ul>
    {#each labels as label (label)}
      <li>
        <span class="label">{label}</span>
        <input
          type="date"
          aria-label="Semester {label}"
          value={value(label)}
          oninput={(e) => (drafts[label] = e.currentTarget.value)}
        />
        {#if !known[label]}<span class="chip missing">fehlt</span>{/if}
        {#if value(label) && value(label) !== known[label]}
          <button type="button" aria-label="{label} speichern" disabled={busy} onclick={() => save(label)}>Speichern</button>
        {/if}
      </li>
    {/each}
  </ul>
  {#if error}<p class="error" role="alert">{error}</p>{/if}
</section>

<style>
  ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 0.5rem; }
  li { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }
  .label { flex: 0 0 2.5rem; font-weight: 600; }
  input { flex: 1 1 10rem; width: auto; min-width: 0; }
  .missing { background: var(--error-soft); }
  li button { min-height: 48px; margin-left: auto; }
</style>
