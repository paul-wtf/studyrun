<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import ChapterList from '#lib/components/ChapterList.svelte';
  import UploadBooklet from '#lib/components/UploadBooklet.svelte';

  interface Booklet { id: number; filename: string; page_count: number; status: 'processing' | 'ready' | 'failed' }
  interface Module { id: number; name: string; booklets: Booklet[] }

  const STATUS = { processing: 'In Arbeit', ready: 'Fertig', failed: 'Fehlgeschlagen' };

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
  <p><a href="/modules">Alle Module</a></p>
  {#if error}<p class="error">{error}</p>{/if}
  {#if module}
    <h1>{module.name}</h1>
    {#each module.booklets as b (b.id)}
      <div class="card">
        <strong>{b.filename}</strong>
        <p class="muted">{b.page_count} Seiten · {STATUS[b.status]}</p>
      </div>
    {/each}
    <UploadBooklet moduleId={id} onuploaded={uploaded} />
    {#key generation}
      <ChapterList moduleId={id} />
    {/key}
  {/if}
</div>

<style>
  .card p { margin: 0; }
</style>
