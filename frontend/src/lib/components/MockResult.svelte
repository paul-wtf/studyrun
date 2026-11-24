<script lang="ts">
  import type { MockEntry, MockExam, SelfRating } from '#lib/api/models.ts';
  import { answerText, questionText } from '#lib/mock.ts';

  let {
    exam,
    rating = null,
    error = '',
    onrate
  }: { exam: MockExam; rating?: number | null; error?: string; onrate: (n: number, rating: SelfRating) => void } = $props();

  const result = $derived(exam.result);
  const chapters = $derived(result ? [...result.chapters].sort((a, b) => a.score - b.score) : []);
  const correct = $derived(exam.entries.filter((e) => e.review?.correct).length);

  const pending = (e: MockEntry) => e.review?.grading_unavailable === true && e.review.score === null;

  function status(e: MockEntry): [string, 'good' | 'bad' | null] {
    const r = e.review;
    if (!r) return ['', null];
    if (!e.answered) return ['Ohne Antwort', 'bad'];
    if (pending(e)) return ['Selbst bewerten', null];
    if (e.item.kind === 'free' && r.grading_unavailable) return [r.correct ? 'Gewusst' : 'Nicht gewusst', r.correct ? 'good' : 'bad'];
    if (e.item.kind === 'free') return [`${r.score} von 100`, r.correct ? 'good' : 'bad'];
    return r.correct ? ['Richtig', 'good'] : ['Falsch', 'bad'];
  }
</script>

<div class="stack">
  {#if result}
    <section class="card stack" aria-label="Ergebnis">
      <p class="muted">Bosskampf · {exam.subject_name}</p>
      <div class="total">
        <span class="pct">{result.score} %</span>
        <span class="chip" class:good={result.passed} class:bad={!result.passed}>{result.passed ? 'Bestanden' : 'Nicht bestanden'}</span>
      </div>
      <p class="muted">bestanden ab {result.pass_mark} % · {correct} von {exam.entries.length} Fragen richtig</p>
      {#if result.pending_self_rating}
        <p class="muted">
          {result.pending_self_rating === 1
            ? '1 freie Antwort wartet auf deine Selbstbewertung und zählt bis dahin mit 0 Punkten.'
            : `${result.pending_self_rating} freie Antworten warten auf deine Selbstbewertung und zählen bis dahin mit 0 Punkten.`}
        </p>
      {/if}
      <a class="btn block" href="/subjects/{exam.subject_id}">Zum Fach</a>
    </section>

    <section class="card">
      <h2 id="chapters-title">Kapitel</h2>
      <ul class="plain chapters" aria-labelledby="chapters-title">
        {#each chapters as c (c.chapter_id)}
          <li>
            <span class="name">{c.title} <span class="muted count">· {c.items === 1 ? '1 Frage' : `${c.items} Fragen`}</span></span>
            <span class="score">{c.score} %</span>
            <span class="bar" aria-hidden="true"><span class="fill" style:width="{c.score}%"></span></span>
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  {#if error}<p class="error" role="alert">{error}</p>{/if}

  {#each exam.entries as e (e.n)}
    {@const [label, tone] = status(e)}
    {@const given = answerText(e.item, e.answer)}
    <article class="card stack" aria-labelledby="entry-{e.n}">
      <div class="head">
        <h3 id="entry-{e.n}">Frage {e.n + 1}</h3>
        {#if label}<span class="chip" class:good={tone === 'good'} class:bad={tone === 'bad'}>{label}</span>{/if}
      </div>
      <p class="question">{questionText(e.item)}</p>
      <dl>
        <dt>Deine Antwort</dt>
        <dd class:missing={given === null}>{given ?? 'Nicht beantwortet'}</dd>
        {#if e.review?.expected && !e.review.correct}
          <dt>Richtige Antwort</dt>
          <dd><strong>{e.review.expected}</strong></dd>
        {/if}
      </dl>
      {#if e.review?.explanation}<p>{e.review.explanation}</p>{/if}
      {#if e.review?.feedback}<p>{e.review.feedback}</p>{/if}
      {#if e.review?.missing.length}
        <p class="muted">Es fehlt noch:</p>
        <ul>
          {#each e.review.missing as point}<li>{point}</li>{/each}
        </ul>
      {/if}
      {#if pending(e)}
        <p class="muted">Die automatische Bewertung war nicht möglich. Vergleiche deine Antwort mit der Musterantwort und bewerte selbst.</p>
        <p class="label">Musterantwort</p>
        <p>{e.review?.model_answer}</p>
        <div class="pair">
          <button disabled={rating !== null} onclick={() => onrate(e.n, 'again')}>Wusste ich nicht</button>
          <button class="primary" disabled={rating !== null} onclick={() => onrate(e.n, 'good')}>Wusste ich</button>
        </div>
      {:else if e.review?.model_answer}
        <details>
          <summary>Musterantwort</summary>
          <p>{e.review.model_answer}</p>
        </details>
      {/if}
      {#if e.source}<a href={e.source} target="_blank" rel="noopener">Im Heft nachlesen</a>{/if}
    </article>
  {/each}
</div>

<style>
  .total { display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem 0.9rem; }
  .pct { font-family: var(--font-display); font-size: 2.4rem; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; }
  .chip.good { background: var(--success-soft); }
  .chip.bad { background: var(--error-soft); }
  section p { margin: 0; }
  h2 { font-size: 1rem; color: var(--text-muted); margin: 0 0 0.5rem; }
  .plain { list-style: none; padding: 0; margin: 0; }
  .chapters { display: grid; gap: 0.6rem; }
  .chapters li { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: baseline; gap: 0.15rem 0.75rem; }
  .name { font-weight: 600; overflow-wrap: break-word; }
  .count { font-weight: 400; white-space: nowrap; }
  .score { font-weight: 700; font-variant-numeric: tabular-nums; min-width: 3.2rem; text-align: right; }
  .bar { grid-column: 1 / -1; height: 6px; border-radius: 2px; background: var(--surface0); overflow: hidden; }
  .fill { display: block; height: 100%; background: var(--accent); }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
  h3 { font-size: 0.95rem; color: var(--text-muted); margin: 0; }
  .question { font-weight: 600; font-size: 1.05rem; overflow-wrap: anywhere; }
  dl { margin: 0 0 0.75rem; }
  dt { color: var(--text-muted); font-size: 0.85rem; }
  dd { margin: 0 0 0.5rem; overflow-wrap: break-word; }
  dd:last-child { margin-bottom: 0; }
  dd.missing { color: var(--text-muted); font-style: italic; }
  .label { color: var(--text-muted); font-size: 0.9rem; margin-bottom: 0.25rem; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
</style>
