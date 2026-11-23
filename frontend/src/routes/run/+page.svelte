<script lang="ts">
  import { onMount } from 'svelte';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import type { Run, RunSummaryData } from '#lib/api/types.ts';
  import { clearRunMarker, markRunStarted } from '#lib/run.ts';
  import IntroCard from '#lib/components/IntroCard.svelte';
  import McQuestion from '#lib/components/McQuestion.svelte';
  import TrueFalseQuestion from '#lib/components/TrueFalseQuestion.svelte';
  import ClozeQuestion from '#lib/components/ClozeQuestion.svelte';
  import FreeQuestion from '#lib/components/FreeQuestion.svelte';
  import RunSummary from '#lib/components/RunSummary.svelte';

  let run = $state<Run | null>(null);
  let summary = $state<RunSummaryData | null>(null);
  let empty = $state(false);
  let error = $state('');

  const current = $derived(run?.entries.find((e) => !e.done));
  const doneCount = $derived(run?.entries.filter((e) => e.done).length ?? 0);

  async function finish() {
    if (!run) return;
    try {
      summary = await api.post<RunSummaryData>(`/api/runs/${run.id}/finish`);
      clearRunMarker();
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

  onMount(async () => {
    try {
      run = await api.post<Run>('/api/runs');
      if (run.entries.length === 0) {
        empty = true;
        await api.post(`/api/runs/${run.id}/finish`);
      } else {
        markRunStarted(run.id);
        if (!current) await finish();
      }
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    }
  });
</script>

{#if summary}
  <RunSummary {summary} />
{:else if empty}
  <div class="card stack">
    <h1>Heute gibt es nichts zu lernen</h1>
    <p>Es ist nichts fällig und kein neues Kapitel bereit. Schau bei den Modulen nach.</p>
    <a class="btn primary block" href="/modules">Zu den Modulen</a>
  </div>
{:else if run && current}
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
  {#key current.n}
    {#if current.type === 'intro'}
      <IntroCard runId={run.id} entry={current} onDone={() => advance(current.n)} />
    {:else if current.item.kind === 'mc'}
      <McQuestion runId={run.id} entry={current} onDone={() => advance(current.n)} />
    {:else if current.item.kind === 'true_false'}
      <TrueFalseQuestion runId={run.id} entry={current} onDone={() => advance(current.n)} />
    {:else if current.item.kind === 'cloze'}
      <ClozeQuestion runId={run.id} entry={current} onDone={() => advance(current.n)} />
    {:else}
      <FreeQuestion runId={run.id} entry={current} onDone={() => advance(current.n)} />
    {/if}
  {/key}
{:else if !error}
  <p class="muted">Lade …</p>
{/if}
{#if error}<p class="error">{error}</p>{/if}

<style>
  .top { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; }
  .bar { flex: 1; height: 10px; border-radius: 5px; background: var(--border); overflow: hidden; }
  .fill { height: 100%; background: var(--accent); transition: width 0.2s; }
  .quit { min-height: 44px; padding: 0.3rem 0.9rem; }
</style>
