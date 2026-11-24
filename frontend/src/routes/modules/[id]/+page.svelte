<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import ChapterList from '#lib/components/ChapterList.svelte';
  import UploadBooklet from '#lib/components/UploadBooklet.svelte';

  import type { BookletStatus, Module } from '#lib/api/models.ts';

  const STATUS: Record<BookletStatus, string> = { processing: 'In Arbeit', ready: 'Fertig', failed: 'Fehlgeschlagen' };

  const id = Number(page.params.id);
  let module = $state<Module | null>(null);
  let error = $state('');
  let generation = $state(0);

  async function load() {
    try {
      const all = await api.get<Module[]>('/api/modules');
      module = all.find((m) => m.id === id) ?? null;
      if (!module) error = 'Modul nicht gefunden';
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    }
  }

  function uploaded() {
    generation += 1;
    void load();
  }

  onMount(load);
</script>

<div class="stack">
  <p><a class="back" href="/modules">Alle Module</a></p>
  {#if error}<p class="error">{error}</p>{/if}
  {#if module}
    <h1>{module.name}</h1>
    {#each module.booklets as b (b.id)}
      <div class="card booklet">
        <strong>{b.filename}</strong>
        <p class="muted">{b.page_count} Seiten · {STATUS[b.status]}</p>
      </div>
    {/each}
    <UploadBooklet moduleId={id} onuploaded={uploaded} />
    {#key generation}
      <ChapterList moduleId={id} onchange={load} />
    {/key}
  {/if}
</div>

<style>
  .card p { margin: 0; }
  .back { display: inline-flex; align-items: center; min-height: 44px; text-decoration: none; font-weight: 600; }
  .booklet { overflow-wrap: anywhere; }
</style>
