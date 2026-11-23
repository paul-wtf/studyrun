<script lang="ts">
  import { untrack } from 'svelte';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import type { ItemKind } from '#lib/api/types.ts';

  interface Flag {
    id: number;
    kind: ItemKind;
    payload: Record<string, unknown>;
    source_page: number;
  }

  type Field = { key: string; label: string; type: 'text' | 'area' | 'lines' | 'int' | 'bool' };

  const FIELDS: Record<ItemKind, Field[]> = {
    mc: [
      { key: 'prompt', label: 'Frage', type: 'area' },
      { key: 'options', label: 'Antwortoptionen (eine pro Zeile)', type: 'lines' },
      { key: 'answer_index', label: 'Nummer der richtigen Option (ab 0)', type: 'int' },
      { key: 'explanation', label: 'Erklärung', type: 'area' }
    ],
    true_false: [
      { key: 'statement', label: 'Aussage', type: 'area' },
      { key: 'correct', label: 'Richtige Antwort', type: 'bool' },
      { key: 'explanation', label: 'Erklärung', type: 'area' }
    ],
    cloze: [
      { key: 'text', label: 'Text mit Lücken', type: 'area' },
      { key: 'answers', label: 'Lösungen (eine pro Zeile)', type: 'lines' },
      { key: 'explanation', label: 'Erklärung', type: 'area' }
    ],
    free: [
      { key: 'prompt', label: 'Frage', type: 'area' },
      { key: 'model_answer', label: 'Musterantwort', type: 'area' },
      { key: 'rubric', label: 'Bewertungskriterien (eine pro Zeile)', type: 'lines' },
      { key: 'source_excerpt', label: 'Auszug aus dem Skript', type: 'area' }
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
        : String(start.payload[f.key] ?? '');

  let values = $state<Record<string, string>>(Object.fromEntries(fields.map((f) => [f.key, initial(f)])));
  let page = $state(String(start.source_page));
  let busy = $state(false);
  let error = $state('');

  function build(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const f of fields) {
      const v = values[f.key];
      out[f.key] =
        f.type === 'lines' ? v.split('\n').map((l) => l.trim()).filter(Boolean)
        : f.type === 'int' ? Number(v)
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
      {:else if f.type === 'int'}
        <input type="text" inputmode="numeric" bind:value={values[f.key]} />
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
    <button type="button" disabled={busy} onclick={remove}>Löschen</button>
  </div>
</form>

<style>
  label { display: block; }
  label :global(textarea), label :global(input), select { display: block; margin-top: 0.3rem; }
  select {
    font: inherit; width: 100%; padding: 0.75rem; border-radius: var(--radius);
    border: 1px solid var(--border); background: var(--surface); color: var(--text);
  }
  textarea { min-height: 5rem; }
  .row { display: flex; gap: 0.5rem; flex-wrap: wrap; }
</style>
