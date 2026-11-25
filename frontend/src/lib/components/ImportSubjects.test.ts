import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import ImportSubjects from './ImportSubjects.svelte';
import { mockApi } from '#lib/test/mockApi.ts';

const PLAN = {
  semesters: { '3a': '2026-04-01' },
  subjects: [{ name: 'Rechnungswesen', duration_minutes: 90, earliest_semester: '3a', recommended_semester: 4, sittings: ['2027-01-31'] }]
};

const file = (text: string) => new File([text], 'plan.json', { type: 'application/json' });

async function upload(text: string) {
  await userEvent.upload(screen.getByLabelText('JSON-Datei'), file(text));
  await userEvent.click(screen.getByRole('button', { name: 'Importieren' }));
}

describe('ImportSubjects', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('sends the content of the file and reports what changed', async () => {
    const onimported = vi.fn();
    const { calls } = mockApi({ 'POST /api/subjects/import': { created: 1, updated: 2, kept_sittings: 1 } });
    render(ImportSubjects, { onimported });
    await upload(JSON.stringify(PLAN));
    expect(await screen.findByText('1 Fach neu, 2 aktualisiert.')).toBeInTheDocument();
    expect(screen.getByText(/1 Termin mit Plan oder Anmeldung bleibt erhalten/)).toBeInTheDocument();
    expect(calls[0]).toMatchObject({ method: 'POST', path: '/api/subjects/import', body: PLAN });
    expect(onimported).toHaveBeenCalled();
  });

  it('refuses a file that is not JSON without calling the server', async () => {
    const { calls } = mockApi({});
    render(ImportSubjects, { onimported: vi.fn() });
    await upload('semesters: 3a');
    expect(await screen.findByText('Die Datei enthält kein gültiges JSON.')).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it('explains a rejected format', async () => {
    mockApi({
      'POST /api/subjects/import': new Response(JSON.stringify({ detail: [{ loc: ['body', 'subjects'], msg: 'Field required' }] }), {
        status: 422,
        headers: { 'content-type': 'application/json' }
      })
    });
    render(ImportSubjects, { onimported: vi.fn() });
    await upload('{}');
    expect(await screen.findByText(/passt nicht zum Format/)).toBeInTheDocument();
  });
});
