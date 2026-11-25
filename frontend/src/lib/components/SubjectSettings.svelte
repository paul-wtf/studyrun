<script lang="ts">
  import { api, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import type { Subject } from '#lib/api/models.ts';

  let { subject, onchange }: { subject: Subject; onchange: () => void } = $props();

  // svelte-ignore state_referenced_locally
  let notBefore = $state(subject.not_before ?? '');
  // svelte-ignore state_referenced_locally
  let passMark = $state<number | null>(subject.pass_mark);
  let busy = $state(false);
  let error = $state('');
  let saved = $state(false);

  const valid = $derived(passMark !== null && Number.isInteger(passMark) && passMark >= 1 && passMark <= 100);

  async function save() {
    busy = true;
    error = '';
    saved = false;
    try {
      await api.patch(`/api/subjects/${subject.id}`, { not_before: notBefore || null, pass_mark: passMark });
      saved = true;
      onchange();
    } catch (e) {
      if (!(e instanceof SessionExpiredError)) error = errorText(e);
    } finally {
      busy = false;
    }
  }
</script>

<form class="settings stack" onsubmit={(e) => { e.preventDefault(); void save(); }}>
  <div class="fields">
    <label>
      Nicht vor
      <input type="date" bind:value={notBefore} oninput={() => (saved = false)} />
    </label>
    <label>
      Bestehensgrenze Bosskampf (%)
      <input type="number" min="1" max="100" step="1" bind:value={passMark} oninput={() => (saved = false)} />
    </label>
  </div>
  <div class="row">
    <button type="submit" disabled={busy || !valid}>Speichern</button>
    {#if saved}<span class="muted" role="status">Gespeichert</span>{/if}
  </div>
  {#if error}<p class="error" role="alert">{error}</p>{/if}
</form>

<style>
  .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: 0.75rem; }
  .row { display: flex; align-items: center; gap: 0.75rem; }
  .row button { min-height: 48px; }
</style>
