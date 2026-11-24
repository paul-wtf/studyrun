<script lang="ts">
  import { untrack } from 'svelte';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import type { Flag, ItemKind } from '#lib/api/models.ts';

  type Field = { key: string; label: string; type: 'text' | 'area' | 'lines' | 'choice' | 'bool' };

  const FIELDS: Record<ItemKind, Field[]> = {
    mc: [
      { key: 'prompt', label: 'Frage', type: 'area' },
      { key: 'options', label: 'Antwortoptionen (eine pro Zeile)', type: 'lines' },
      { key: 'answer_index', label: 'Richtige Option', type: 'choice' },
      { key: 'explanation', label: 'Erklärung', type: 'area' }
    ],
    true_false: [
      { key: 'statement', label: 'Aussage', type: 'area' },
      { key: 'correct', label: 'Richtige Antwort', type: 'bool' },
      { key: 'explanation', label: 'Erklärung', type: 'area' }
    ],
    cloze: [
      { key: 'text', label: 'Text mit Lücke (___ markiert die Lücke)', type: 'area' },
      { key: 'answers', label: 'Lösungen (eine pro Zeile)', type: 'lines' },
      { key: 'explanation', label: 'Erklärung', type: 'area' }
    ],
    free: [
      { key: 'prompt', label: 'Frage', type: 'area' },
      { key: 'model_answer', label: 'Musterantwort', type: 'area' },
      { key: 'rubric', label: 'Bewertungskriterien (eine pro Zeile)', type: 'lines' },
      { key: 'source_excerpt', label: 'Auszug aus dem Heft', type: 'area' }
    ]
  };

  let { item, onchanged }: { item: Flag; onchanged: () => void } = $props();

  const start = untrack(() => item);
  const fields = FIELDS[start.kind];
  const initial = (f: Field): string =>
    f.type === 'lines'
      ? ((start.payload[f.key] as string[] | undefined) ?? []).join('\n')
      : f.type === 'bool'
        ? String(start.payload[f.key] ?? true)
        : f.type === 'choice'
          ? String(Number(start.payload[f.key] ?? 0) + 1)
          : String(start.payload[f.key] ?? '');
  const lines = (v: string) => v.split('\n').map((l) => l.trim()).filter(Boolean);

  let values = $state<Record<string, string>>(Object.fromEntries(fields.map((f) => [f.key, initial(f)])));
  let page = $state(String(start.source_page));
  let busy = $state(false);
  let error = $state('');
  let confirming = $state(false);

  function build(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const f of fields) {
      const v = values[f.key];
      out[f.key] =
        f.type === 'lines' ? lines(v)
        : f.type === 'choice' ? Number(v) - 1
        : f.type === 'bool' ? v === 'true'
        : v;
    }
    return out;
  }

  async function run(action: () => Promise<unknown>) {
    busy = true;
    error = '';
    try {
      await action();
      onchanged();
    } catch (e) {
      if (e instanceof SessionExpiredError) throw e;
      error = errorText(e);
    } finally {
      busy = false;
    }
  }

  const save = () => run(() => api.put(`/api/items/${item.id}`, { payload: build(), source_page: Number(page) }));
  const remove = () => run(() => api.del(`/api/items/${item.id}`));
</script>

<form class="stack" onsubmit={(e) => { e.preventDefault(); void save(); }}>
  {#each fields as f (f.key)}
    <label>
      {f.label}
      {#if f.type === 'bool'}
        <select bind:value={values[f.key]}>
          <option value="true">Wahr</option>
          <option value="false">Falsch</option>
        </select>
      {:else if f.type === 'choice'}
        <select bind:value={values[f.key]}>
          {#each lines(values.options ?? '') as option, i (i)}
            <option value={String(i + 1)}>{i + 1}: {option}</option>
          {/each}
        </select>
      {:else}
        <textarea bind:value={values[f.key]}></textarea>
      {/if}
    </label>
  {/each}
  <label>
    Quellseite
    <input type="text" inputmode="numeric" bind:value={page} />
  </label>
  {#if error}<p class="error">{error}</p>{/if}
  <div class="row">
    <button type="submit" class="primary" disabled={busy}>Speichern</button>
    {#if !confirming}
      <button type="button" disabled={busy} onclick={() => (confirming = true)}>Löschen</button>
    {/if}
  </div>
  {#if confirming}
    <div class="stack" role="group" aria-label="Löschen bestätigen">
      <p>Wirklich löschen?</p>
      <div class="row">
        <button type="button" class="danger" disabled={busy} onclick={remove}>Löschen</button>
        <button type="button" disabled={busy} onclick={() => (confirming = false)}>Abbrechen</button>
      </div>
    </div>
  {/if}
</form>

<style>
  textarea { min-height: 5rem; }
  /* Error red carries base-coloured text at 4.80:1 (Latte) and 7.08:1 (Mocha). */
  .danger { background: var(--error); color: var(--base); }
  .danger:not(:disabled):hover { background: var(--error); filter: brightness(1.1); }
  .row { display: flex; gap: 0.5rem; flex-wrap: wrap; }
</style>
