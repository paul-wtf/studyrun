<script lang="ts">
  import { onMount } from 'svelte';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';

  import type { Chapter } from '#lib/api/models.ts';

  const POLL_MS = 30_000;
  const LABEL = {
    pending: 'Wartet',
    generating: 'Wird erzeugt',
    verifying: 'Wird geprüft',
    ready: 'Fertig',
    failed: 'Fehlgeschlagen',
    skipped: 'Übersprungen'
  };

  let { moduleId, onchange }: { moduleId: number; onchange?: () => void } = $props();

  let chapters = $state<Chapter[]>([]);
  let loaded = $state(false);
  let error = $state('');
  let timer: ReturnType<typeof setTimeout> | undefined;
  let alive = true;

  const working = $derived(chapters.some((c) => ['pending', 'generating', 'verifying'].includes(c.status)));

  const signature = (list: Chapter[]) => list.map((c) => `${c.id}:${c.status}`).join(',');

  async function load() {
    clearTimeout(timer);
    try {
      const next = await api.get<Chapter[]>(`/api/modules/${moduleId}/chapters`);
      const changed = loaded && signature(next) !== signature(chapters);
      chapters = next;
      if (changed) onchange?.();
      error = '';
    } catch (e) {
      if (e instanceof SessionExpiredError) return;
      error = errorText(e);
    }
    loaded = true;
    if (alive && working) timer = setTimeout(load, POLL_MS);
  }

  async function act(id: number, action: 'retry' | 'skip') {
    try {
      await api.post(`/api/chapters/${id}/${action}`);
    } catch (e) {
      if (e instanceof SessionExpiredError) return;
      error = errorText(e);
      return;
    }
    await load();
  }

  onMount(() => {
    void load();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  });
</script>

<div class="stack">
  <h2>Kapitel</h2>
  {#if working}
    <p class="muted">Ein Heft braucht in der Regel bis zu einer Stunde. Die Liste aktualisiert sich selbst.</p>
  {/if}
  {#if error}<p class="error">{error}</p>{/if}
  {#if loaded && chapters.length === 0}<p class="muted">Noch keine Kapitel.</p>{/if}
  {#each chapters as c (c.id)}
    <div class="card stack">
      <div class="head">
        <strong>{c.title}</strong>
        <span class="status {c.status}">{LABEL[c.status]}</span>
      </div>
      <p class="muted">Seiten {c.first_page}–{c.last_page}{c.status === 'ready' ? `, ${c.active_items} Aufgaben` : ''}</p>
      {#if c.waiting_reason}<p class="muted">{c.waiting_reason}</p>{/if}
      {#if c.status === 'failed' && c.error}<p class="error">{c.error}</p>{/if}
      {#if c.status === 'failed' || c.status === 'pending'}
        <div class="actions">
          {#if c.status === 'failed'}
            <button type="button" onclick={() => act(c.id, 'retry')}>Neu versuchen</button>
          {/if}
          <button type="button" onclick={() => act(c.id, 'skip')}>Kapitel überspringen</button>
        </div>
      {/if}
    </div>
  {/each}
</div>

<style>
  .head { display: flex; justify-content: space-between; gap: 0.5rem; align-items: baseline; }
  .status { font-size: 0.9rem; color: var(--muted); white-space: nowrap; }
  .status.ready { color: var(--good); }
  .status.failed { color: var(--bad); }
  .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .card :global(p) { margin-bottom: 0; }
</style>
