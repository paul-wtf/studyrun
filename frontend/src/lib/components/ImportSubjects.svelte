<script lang="ts">
  import { api, ApiError, errorText, SessionExpiredError } from '#lib/api/client.ts';
  import type { ImportResult } from '#lib/api/models.ts';

  let { onimported }: { onimported: () => void } = $props();

  let file = $state<File | null>(null);
  let busy = $state(false);
  let error = $state('');
  let done = $state<ImportResult | null>(null);

  function readText(f: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsText(f);
    });
  }

  type Problem = { loc?: (string | number)[]; msg?: string };

  function formatProblem(e: unknown): string | null {
    if (!(e instanceof ApiError) || e.status !== 422) return null;
    const detail = (e.body as { detail?: unknown } | null)?.detail;
    if (!Array.isArray(detail)) return null;
    const first = detail[0] as Problem | undefined;
    const where = first?.loc?.filter((part) => part !== 'body').join('.');
    const what = [where, first?.msg].filter(Boolean).join(': ');
    return `Die Datei passt nicht zum Format des Prüfungsplans${what ? ` (${what})` : ''}.`;
  }

  async function send() {
    if (!file) return;
    error = '';
    done = null;
    let text: string;
    try {
      text = await readText(file);
    } catch {
      error = 'Die Datei ließ sich nicht lesen.';
      return;
    }
    let body: unknown;
    try {
      body = JSON.parse(text);
    } catch {
      error = 'Die Datei enthält kein gültiges JSON.';
      return;
    }
    busy = true;
    try {
      done = await api.post<ImportResult>('/api/subjects/import', body);
      onimported();
    } catch (e) {
      if (e instanceof SessionExpiredError) return;
      error = formatProblem(e) ?? errorText(e);
    } finally {
      busy = false;
    }
  }
</script>

<form class="card stack" onsubmit={(e) => { e.preventDefault(); void send(); }}>
  <h2>Prüfungsplan importieren</h2>
  <p class="muted">Fächer, Semesterstarts und Prüfungstermine als JSON. Ein erneuter Import aktualisiert die Fächer und lässt Anmeldungen und Ergebnisse stehen.</p>
  <label>
    JSON-Datei
    <input
      type="file"
      accept="application/json,.json"
      disabled={busy}
      onchange={(e) => { file = e.currentTarget.files?.[0] ?? null; error = ''; done = null; }}
    />
  </label>
  <button type="submit" class="primary" disabled={busy || !file}>Importieren</button>
  {#if done}
    <p role="status">
      <span>{done.created} {done.created === 1 ? 'Fach' : 'Fächer'} neu, {done.updated} aktualisiert.</span>
      {#if done.kept_sittings}
        <span class="muted">
          {done.kept_sittings === 1
            ? '1 Termin mit Plan oder Anmeldung bleibt erhalten, obwohl er im Import fehlt.'
            : `${done.kept_sittings} Termine mit Plan oder Anmeldung bleiben erhalten, obwohl sie im Import fehlen.`}
        </span>
      {/if}
    </p>
  {/if}
  {#if error}<p class="error" role="alert">{error}</p>{/if}
</form>

<style>
  input[type='file'] { display: block; margin-top: 0.5rem; }
</style>
