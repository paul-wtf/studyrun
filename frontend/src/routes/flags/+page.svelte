<script lang="ts">
  import { onMount } from 'svelte';
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import FlagEditor from '#lib/components/FlagEditor.svelte';
  import type { Flag, FlagReason } from '#lib/api/models.ts';

  const REASON: Record<FlagReason, string> = { wrong: 'Falsch', not_in_course: 'Nicht im Kurs', unclear: 'Unklar' };

  let flags = $state<Flag[] | null>(null);
  let error = $state('');

  async function load() {
    try {
      flags = await api.get<Flag[]>('/api/flags');
      error = '';
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    }
  }

  onMount(load);
</script>

<div class="stack">
  <h1>Gemeldet</h1>
  {#if error}<p class="error">{error}</p>{/if}
  {#if flags && flags.length === 0}<p class="muted note">Keine gemeldeten Fragen.</p>{/if}
  {#each flags ?? [] as f (f.id)}
    <div class="card stack">
      <p class="muted">
        <strong class="chip">{f.reason ? REASON[f.reason] : 'Gemeldet'}</strong> · {f.chapter_title} · Seite {f.source_page}
        · <a href={f.source} target="_blank" rel="noopener">Im Heft nachlesen</a>
      </p>
      <FlagEditor item={f} onchanged={load} />
    </div>
  {/each}
</div>
