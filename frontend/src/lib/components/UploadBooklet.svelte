<script lang="ts">
  import { api, ApiError, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import { euro } from '#lib/format.ts';

  let { moduleId, onuploaded }: { moduleId: number; onuploaded: () => void } = $props();

  let file = $state<File | null>(null);
  let busy = $state(false);
  let error = $state('');
  let estimate = $state<number | null>(null);

  async function send(confirm: boolean) {
    if (!file) return;
    busy = true;
    error = '';
    const form = new FormData();
    form.append('file', file);
    form.append('confirm', String(confirm));
    try {
      await api.post(`/api/modules/${moduleId}/booklets`, form);
      estimate = null;
      file = null;
      onuploaded();
    } catch (e) {
      if (e instanceof SessionExpiredError) throw e;
      const body = e instanceof ApiError ? (e.body as { needs_confirmation?: boolean; estimate_usd?: number } | null) : null;
      if (e instanceof ApiError && e.status === 409 && body?.needs_confirmation) {
        estimate = body.estimate_usd ?? 0;
      } else {
        error = errorText(e);
      }
    } finally {
      busy = false;
    }
  }
</script>

<form class="card stack" onsubmit={(e) => { e.preventDefault(); void send(false); }}>
  <h2>Skript hochladen</h2>
  <label>
    PDF-Datei
    <input
      type="file"
      accept="application/pdf"
      disabled={busy}
      onchange={(e) => { file = e.currentTarget.files?.[0] ?? null; estimate = null; error = ''; }}
    />
  </label>
  {#if estimate !== null}
    <p>Die Erzeugung kostet etwa {euro(estimate)} $. Fortfahren?</p>
    <div class="row">
      <button type="button" class="primary" disabled={busy} onclick={() => send(true)}>Fortfahren</button>
      <button type="button" disabled={busy} onclick={() => (estimate = null)}>Abbrechen</button>
    </div>
  {:else}
    <button type="submit" class="primary" disabled={busy || !file}>Hochladen</button>
  {/if}
  {#if error}<p class="error">{error}</p>{/if}
</form>

<style>
  label { display: block; }
  input[type='file'] { display: block; margin-top: 0.4rem; max-width: 100%; }
  .row { display: flex; gap: 0.5rem; flex-wrap: wrap; }
</style>
