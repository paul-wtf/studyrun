<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { api, ApiError, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import type { Run, RunSummaryData } from '#lib/api/models.ts';
  import { isCloze, isFree, isMc, isTrueFalse } from '#lib/api/entries.ts';
  import IntroCard from '#lib/components/IntroCard.svelte';
  import McQuestion from '#lib/components/McQuestion.svelte';
  import TrueFalseQuestion from '#lib/components/TrueFalseQuestion.svelte';
  import ClozeQuestion from '#lib/components/ClozeQuestion.svelte';
  import FreeQuestion from '#lib/components/FreeQuestion.svelte';
  import RunSummary from '#lib/components/RunSummary.svelte';

  const param = page.url.searchParams.get('subject');
  const subjectId = param && /^\d+$/.test(param) ? Number(param) : null;
  const start = () => api.post<Run>('/api/runs', subjectId === null ? undefined : { subject_id: subjectId });

  let run = $state<Run | null>(null);
  let subjectName = $state<string | null>(null);
  let summary = $state<RunSummaryData | null>(null);
  let empty = $state(false);
  let error = $state('');
  let note = $state('');

  const current = $derived(run?.entries.find((e) => !e.done));
  const doneCount = $derived(run?.entries.filter((e) => e.done).length ?? 0);

  async function finish() {
    if (!run) return;
    try {
      summary = await api.post<RunSummaryData>(`/api/runs/${run.id}/finish`);
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    }
  }

  function advance(n: number) {
    if (!run) return;
    const entry = run.entries.find((e) => e.n === n);
    if (entry) entry.done = true;
    if (!run.entries.some((e) => !e.done)) void finish();
  }

  async function reload(cause?: unknown) {
    try {
      const fresh = await start();
      if (fresh.entries.length === 0) {
        run = null;
        empty = true;
        return;
      }
      run = fresh;
      note =
        cause instanceof ApiError && cause.status === 409
          ? 'Diese Frage wurde schon auf einem anderen Gerät beantwortet.'
          : 'Der Durchlauf wurde neu geladen.';
      if (!current) await finish();
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    }
  }

  onMount(async () => {
    try {
      const fresh = await start();
      subjectName = fresh.subject_name;
      if (fresh.entries.length === 0) empty = true;
      else run = fresh;
      if (run && !current) await finish();
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    }
  });
</script>

{#if subjectName && !summary && !empty}
  <h1 class="title">Fach-Run: {subjectName}</h1>
{/if}
{#if summary}
  <RunSummary {summary} back={subjectId === null ? '/' : `/subjects/${subjectId}`} />
{:else if empty && subjectId !== null}
  <div class="card stack">
    <h1>Für {subjectName ?? 'dieses Fach'} gibt es gerade nichts</h1>
    <p>Es ist nichts fällig und kein neues Kapitel bereit. Prüf beim Fach, ob alle Module zugeordnet sind und Fragen haben.</p>
    <a class="btn primary block" href="/subjects/{subjectId}">Zum Fach</a>
  </div>
{:else if empty}
  <div class="card stack">
    <h1>Heute gibt es nichts zu lernen</h1>
    <p>Es ist nichts fällig und kein neues Kapitel bereit. Schau bei den Modulen nach.</p>
    <a class="btn primary block" href="/modules">Zu den Modulen</a>
  </div>
{:else if run && run.id !== null && current}
  <div class="top">
    <div
      class="bar"
      role="progressbar"
      aria-valuemin="0"
      aria-valuemax={run.entries.length}
      aria-valuenow={doneCount}
      aria-label="Fortschritt"
    >
      <div class="fill" style:width="{(doneCount / run.entries.length) * 100}%"></div>
    </div>
    <button class="quit" onclick={finish}>Beenden</button>
  </div>
  {#if note}<p class="muted note" role="status">{note}</p>{/if}
  {#key `${run.id}-${current.n}`}
    {#if current.type === 'intro'}
      <IntroCard runId={run.id} entry={current} onDone={() => advance(current.n)} onStale={reload} />
    {:else if isMc(current)}
      <McQuestion runId={run.id} entry={current} onDone={() => advance(current.n)} onStale={reload} />
    {:else if isTrueFalse(current)}
      <TrueFalseQuestion runId={run.id} entry={current} onDone={() => advance(current.n)} onStale={reload} />
    {:else if isCloze(current)}
      <ClozeQuestion runId={run.id} entry={current} onDone={() => advance(current.n)} onStale={reload} />
    {:else if isFree(current)}
      <FreeQuestion runId={run.id} entry={current} onDone={() => advance(current.n)} onStale={reload} />
    {/if}
  {/key}
{:else if !error}
  <p class="muted note">Lade …</p>
{/if}
{#if error}<p class="error">{error}</p>{/if}

<style>
  .top { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
  .bar { flex: 1; height: 8px; border-radius: 2px; background: var(--surface0); overflow: hidden; }
  .fill { height: 100%; background: var(--accent); transition: width var(--dur) var(--ease-out); }
  .quit { min-height: 44px; padding: 0.3rem 0.9rem; }
  .note { margin-bottom: 1rem; }
  .title { font-size: 1.1rem; margin-bottom: 0.75rem; overflow-wrap: anywhere; }
</style>
