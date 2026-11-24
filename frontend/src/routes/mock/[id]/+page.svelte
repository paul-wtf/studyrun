<script lang="ts">
  import { onDestroy, onMount, tick } from 'svelte';
  import { page } from '$app/state';
  import { api, ApiError, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import type { GivenAnswer, MockAnswer, MockExam, SelfRating } from '#lib/api/models.ts';
  import MockQuestion from '#lib/components/MockQuestion.svelte';
  import MockResult from '#lib/components/MockResult.svelte';
  import MockTimer from '#lib/components/MockTimer.svelte';

  const id = Number(page.params.id);
  const SAVE_DELAY = 500;
  const RETRY_DELAY = 3_000;
  const RETRIES = 3;

  let exam = $state<MockExam | null>(null);
  let answers = $state<(GivenAnswer | null)[]>([]);
  let phase = $state<'loading' | 'exam' | 'finishing' | 'stalled' | 'result'>('loading');
  let current = $state(0);
  let confirming = $state(false);
  let locked = $state(false);
  let timeUp = $state(false);
  let saving = $state(0);
  let error = $state('');
  let saveError = $state('');
  let rating = $state<number | null>(null);
  let rateError = $state('');
  let confirmBox = $state<HTMLElement | null>(null);
  let questionBox = $state<HTMLElement | null>(null);
  let where = $state<HTMLElement | null>(null);
  let offset = $state(0);

  const timers = new Map<number, ReturnType<typeof setTimeout>>();
  const dirty = new Set<number>();
  let queue: Promise<void> = Promise.resolve();
  let finishCalled = false;
  let retries = 0;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;

  const given = (a: GivenAnswer | null) => a != null && (a.choice != null || a.value != null || !!a.text?.trim());
  const total = $derived(exam?.entries.length ?? 0);
  const open = $derived(answers.filter((a) => !given(a)).length);
  const entry = $derived(exam?.entries[current]);

  $effect(() => {
    confirmBox?.focus();
  });

  function change(n: number, answer: GivenAnswer, typed: boolean) {
    answers[n] = answer;
    dirty.add(n);
    clearTimeout(timers.get(n));
    timers.delete(n);
    if (typed) timers.set(n, setTimeout(() => void save(n), SAVE_DELAY));
    else void save(n);
  }

  function save(n: number, keepalive = false): Promise<void> {
    clearTimeout(timers.get(n));
    timers.delete(n);
    saving++;
    queue = queue
      .then(async () => {
        if (!dirty.has(n)) return;
        dirty.delete(n);
        try {
          await api.post<MockAnswer>(`/api/mock/${id}/answers/${n}`, { answer: $state.snapshot(answers[n]) }, { keepalive });
          if (dirty.size === 0) saveError = '';
        } catch (e) {
          dirty.add(n);
          if (e instanceof SessionExpiredError) return;
          if (e instanceof ApiError && e.status === 409) {
            timeUp = true;
            void finish();
            return;
          }
          saveError = `Die Antwort auf Frage ${n + 1} ist nicht gespeichert: ${errorText(e)}`;
        }
      })
      .finally(() => saving--);
    return queue;
  }

  async function flush(keepalive = false) {
    for (const n of [...dirty]) void save(n, keepalive);
    await queue;
  }

  async function finish() {
    if (finishCalled || !exam) return;
    finishCalled = true;
    confirming = false;
    locked = true;
    await flush();
    if (dirty.size > 0 && Date.now() + offset < Date.parse(exam.deadline) && !timeUp) {
      finishCalled = false;
      locked = false;
      return;
    }
    await complete();
  }

  async function complete() {
    clearTimeout(retryTimer);
    phase = 'finishing';
    error = '';
    try {
      show(await api.post<MockExam>(`/api/mock/${id}/finish`));
    } catch (e) {
      if (e instanceof SessionExpiredError) return;
      try {
        const fresh = await api.get<MockExam>(`/api/mock/${id}`);
        if (fresh.finished) return show(fresh);
      } catch (again) {
        if (again instanceof SessionExpiredError) return;
        error = errorText(again);
      }
      phase = 'stalled';
      if (retries < RETRIES) retryTimer = setTimeout(() => void complete(), RETRY_DELAY * 2 ** retries++);
    }
  }

  function show(fresh: MockExam) {
    offset = Date.parse(fresh.now) - Date.now();
    exam = fresh;
    answers = fresh.entries.map((e) => e.answer);
    if (fresh.finished) phase = 'result';
  }

  async function jump(i: number) {
    current = i;
    await tick();
    questionBox?.scrollIntoView({ block: 'start' });
    where?.focus({ preventScroll: true });
  }

  function leave() {
    if (phase === 'exam') void flush(true);
  }

  function expire() {
    timeUp = true;
    void finish();
  }

  async function rate(n: number, value: SelfRating) {
    rating = n;
    rateError = '';
    try {
      exam = await api.post<MockExam>(`/api/mock/${id}/self-rate/${n}`, { rating: value });
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) rateError = errorText(e);
    } finally {
      rating = null;
    }
  }

  onMount(async () => {
    try {
      const fresh = await api.get<MockExam>(`/api/mock/${id}`);
      show(fresh);
      if (fresh.finished) return;
      if (fresh.finishing || fresh.expired) {
        finishCalled = true;
        locked = true;
        timeUp = fresh.expired;
        await complete();
      } else {
        phase = 'exam';
      }
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    }
  });

  onDestroy(() => {
    leave();
    clearTimeout(retryTimer);
    for (const t of timers.values()) clearTimeout(t);
  });
</script>

<svelte:window onpagehide={leave} />
<svelte:document onvisibilitychange={() => document.visibilityState === 'hidden' && leave()} />

<div class="stack">
  {#if exam}<p><a class="back" href="/subjects/{exam.subject_id}">Zum Fach</a></p>{/if}

  {#if phase === 'result' && exam}
    <MockResult {exam} {rating} error={rateError} onrate={rate} />
  {:else if (phase === 'finishing' || phase === 'stalled') && exam}
    <div class="card stack" aria-live="polite">
      {#if timeUp}<p class="muted">Die Zeit ist abgelaufen.</p>{/if}
      {#if phase === 'finishing'}
        <h1>Wird ausgewertet …</h1>
        <p class="muted">Freie Antworten werden einzeln bewertet. Das kann eine Minute dauern.</p>
      {:else}
        <h1>Die Auswertung ist noch nicht fertig</h1>
        <p class="muted">Sie macht dort weiter, wo sie stand.</p>
        <button class="primary block" onclick={complete}>Auswertung fortsetzen</button>
      {/if}
    </div>
  {:else if phase === 'exam' && exam && entry}
    <h1 class="title">Bosskampf: {exam.subject_name}</h1>
    <div class="top">
      <span class="where" tabindex="-1" bind:this={where}>Frage {current + 1} von {total}</span>
      <MockTimer deadline={exam.deadline} {offset} onexpire={expire} />
    </div>

    <div class="question" bind:this={questionBox}>
      {#key current}
        <MockQuestion item={entry.item} answer={answers[current]} disabled={locked} onanswer={(a, typed) => change(current, a, typed)} />
      {/key}
    </div>

    <div class="pair">
      <button disabled={current === 0} onclick={() => (current -= 1)}>Zurück</button>
      <button disabled={current === total - 1} onclick={() => (current += 1)}>Weiter</button>
    </div>

    {#if saveError}<p class="error" role="alert">{saveError}</p>{/if}

    <section class="card stack" aria-labelledby="overview-title">
      <div class="head">
        <h2 id="overview-title">Übersicht</h2>
        <span class="muted"><span role="status">{total - open} von {total} beantwortet</span>{#if saving > 0}<span aria-hidden="true"> · speichert …</span>{/if}</span>
      </div>
      <div class="grid">
        {#each exam.entries as e, i (e.n)}
          <button
            class="cell"
            class:done={given(answers[i])}
            aria-current={i === current ? 'step' : undefined}
            aria-label="Frage {i + 1}, {given(answers[i]) ? 'beantwortet' : 'offen'}"
            onclick={() => jump(i)}>{i + 1}</button
          >
        {/each}
      </div>
    </section>

    {#if confirming}
      <div class="card stack" role="group" aria-labelledby="confirm-title" tabindex="-1" bind:this={confirmBox}>
        <h2 id="confirm-title">Abgeben?</h2>
        <p>
          {open === 0
            ? 'Alle Fragen sind beantwortet.'
            : `${open} von ${total} ${total === 1 ? 'Frage ist' : 'Fragen sind'} noch unbeantwortet.`}
          Danach kannst du nichts mehr ändern.
        </p>
        <div class="pair">
          <button onclick={() => (confirming = false)}>Weiter bearbeiten</button>
          <button class="primary" disabled={locked} onclick={finish}>Jetzt abgeben</button>
        </div>
      </div>
    {:else}
      <button class="primary block" disabled={locked} onclick={() => (confirming = true)}>Abgeben</button>
    {/if}
  {:else if !error}
    <p class="muted note">Lade …</p>
  {/if}
  {#if error}<p class="error" role="alert">{error}</p>{/if}
</div>

<style>
  .back { display: inline-flex; align-items: center; min-height: 44px; text-decoration: none; font-weight: 600; }
  .title { font-size: 1.1rem; margin: 0; overflow-wrap: anywhere; }
  .top {
    position: sticky;
    top: var(--viewport-top);
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.35rem 0.5rem 0.35rem 1rem;
    border-radius: var(--r-lg);
    background: var(--base);
    box-shadow: var(--glass-shadow);
  }
  .where { font-weight: 600; font-variant-numeric: tabular-nums; }
  .where:focus { outline: none; }
  .question { scroll-margin-top: calc(var(--viewport-top) + 4rem); }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
  .head { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 0.25rem 0.75rem; }
  h2 { font-size: 1rem; color: var(--text-muted); margin: 0; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(44px, 1fr)); gap: 0.4rem; }
  .cell { min-height: 44px; padding: 0; font-variant-numeric: tabular-nums; }
  .cell.done { background: var(--accent-soft); }
  .cell[aria-current='step'] { box-shadow: inset 0 0 0 2px var(--accent-text); }
  [role='group']:focus { outline: none; }
</style>
