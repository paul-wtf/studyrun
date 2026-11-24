<script lang="ts">
  import { onMount } from 'svelte';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';

  import type { Module, Subject } from '#lib/api/models.ts';

  let modules = $state<Module[]>([]);
  let subjects = $state<Subject[]>([]);
  let name = $state('');
  let error = $state('');
  let busy = $state(false);

  async function load() {
    [modules, subjects] = await Promise.all([api.get<Module[]>('/api/modules'), api.get<Subject[]>('/api/subjects')]);
  }

  async function act(fn: () => Promise<unknown>) {
    busy = true;
    error = '';
    try {
      await fn();
      await load();
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    } finally {
      busy = false;
    }
  }

  const create = () =>
    act(async () => {
      await api.post('/api/modules', { name: name.trim() });
      name = '';
    });
  const move = (m: Module, to: number) => act(() => api.patch(`/api/modules/${m.id}`, { position: to }));
  const assign = (m: Module, value: string) =>
    act(() => api.patch(`/api/modules/${m.id}`, { subject_id: value === '' ? null : Number(value) }));

  onMount(() => act(async () => {}));
</script>

<div class="stack">
  <h1>Module</h1>
  {#if error}<p class="error">{error}</p>{/if}
  {#each modules as m, i (m.id)}
    <div class="card row">
      <a class="name" href="/modules/{m.id}">{m.name}</a>
      <span class="chip">{m.booklets.length} {m.booklets.length === 1 ? 'Heft' : 'Hefte'}</span>
      <button type="button" aria-label="{m.name} nach oben" disabled={busy || i === 0} onclick={() => move(m, i - 1)}>↑</button>
      <button type="button" aria-label="{m.name} nach unten" disabled={busy || i === modules.length - 1} onclick={() => move(m, i + 1)}>↓</button>
      {#if subjects.length}
        <select
          class="subject"
          aria-label="Fach für {m.name}"
          value={m.subject_id === null ? '' : String(m.subject_id)}
          disabled={busy}
          onchange={(e) => assign(m, e.currentTarget.value)}
        >
          <option value="">Kein Fach</option>
          {#each subjects as s (s.id)}
            <option value={String(s.id)}>{s.name}</option>
          {/each}
        </select>
      {/if}
    </div>
  {/each}
  <form class="card stack" onsubmit={(e) => { e.preventDefault(); void create(); }}>
    <label>
      Neues Modul
      <input type="text" bind:value={name} />
    </label>
    <button type="submit" class="primary" disabled={busy || !name.trim()}>Anlegen</button>
  </form>
</div>

<style>
  .row { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; padding: 0.6rem 0.6rem 0.6rem 1.1rem; }
  .name { flex: 1 1 12rem; display: flex; align-items: center; min-height: 44px; font-weight: 600; min-width: 0; overflow-wrap: break-word; color: var(--text); text-decoration: none; }
  .row .chip { margin-left: auto; }
  @media (max-width: 600px) {
    .name { flex-basis: 100%; }
    .row .chip { margin-left: 0; margin-right: auto; }
  }
  .name:hover { color: var(--accent-text); }
  .row button { min-width: 48px; min-height: 48px; padding: 0.4rem; }
  .subject { flex: 1 1 100%; }
</style>
