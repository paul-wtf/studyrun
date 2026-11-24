import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { mockApi } from '#lib/test/mockApi.ts';

const here = vi.hoisted(() => ({ url: new URL('http://localhost/run') }));
vi.mock('$app/state', () => ({ page: here }));

import Page from './+page.svelte';

const RUN = {
  id: 1,
  entries: [
    {
      n: 0,
      type: 'intro',
      done: false,
      grading_unavailable: false,
      chapter: { id: 5, title: 'Die Zelle', summary: 'Bausteine.', concepts: [{ term: 'Kern', explanation: 'Steuert die Zelle.' }], source: '/p#page=1' }
    },
    {
      n: 1,
      type: 'item',
      done: false,
      grading_unavailable: false,
      item: { id: 9, kind: 'true_false', statement: 'Wasser ist nass.', source: '/p#page=2' }
    }
  ]
};
const SUMMARY = { answered: 1, correct: 1, chapters_introduced: ['Die Zelle'], due_tomorrow: 2 };

describe('run page', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    here.url = new URL('http://localhost/run');
  });

  it('moves to the next entry and shows the summary after finish', async () => {
    const { calls } = mockApi({
      'POST /api/runs': RUN,
      'POST /api/runs/1/entries/0/ack': { done: true },
      'POST /api/runs/1/entries/1/answer': { correct: true, expected: 'Wahr', explanation: 'Ja.' },
      'POST /api/runs/1/finish': SUMMARY
    });
    render(Page);
    expect(await screen.findByText('Die Zelle')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }));
    expect(await screen.findByText('Wasser ist nass.')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1');
    await userEvent.click(screen.getByRole('button', { name: 'Wahr' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Weiter' }));
    expect(await screen.findByText('1 von 1 richtig')).toBeInTheDocument();
    expect(calls.at(-1)?.path).toBe('/api/runs/1/finish');
  });

  it('finishes early with Beenden', async () => {
    const { calls } = mockApi({ 'POST /api/runs': RUN, 'POST /api/runs/1/finish': SUMMARY });
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Beenden' }));
    expect(await screen.findByText('1 von 1 richtig')).toBeInTheDocument();
    expect(calls.map((c) => c.path)).toEqual(['/api/runs', '/api/runs/1/finish']);
  });

  it('shows an empty state when the server has no run to give', async () => {
    const { calls } = mockApi({ 'POST /api/runs': { id: null, entries: [] } });
    render(Page);
    expect(await screen.findByText(/nichts zu lernen/i)).toBeInTheDocument();
    expect(calls.map((c) => c.path)).toEqual(['/api/runs']);
  });

  it('reloads the run when another device answered the entry', async () => {
    const { fetchMock } = mockApi({
      'POST /api/runs': { ...RUN, entries: [{ ...RUN.entries[0], done: true }, RUN.entries[1]] }
    });
    fetchMock.mockImplementationOnce(async () => new Response(JSON.stringify(RUN), { status: 200, headers: { 'content-type': 'application/json' } }));
    fetchMock.mockImplementationOnce(async () =>
      new Response(JSON.stringify({ detail: 'Dieser Eintrag ist schon beantwortet.' }), {
        status: 409,
        headers: { 'content-type': 'application/json' }
      })
    );
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Weiter' }));
    expect(await screen.findByText('Wasser ist nass.')).toBeInTheDocument();
    expect(screen.getByText(/auf einem anderen Gerät beantwortet/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([
      '/api/runs',
      '/api/runs/1/entries/0/ack',
      '/api/runs'
    ]);
  });

  it('reloads with a neutral note when the entry is gone', async () => {
    const { fetchMock } = mockApi({
      'POST /api/runs': { ...RUN, entries: [{ ...RUN.entries[0], done: true }, RUN.entries[1]] }
    });
    fetchMock.mockImplementationOnce(async () => new Response(JSON.stringify(RUN), { status: 200, headers: { 'content-type': 'application/json' } }));
    fetchMock.mockImplementationOnce(async () =>
      new Response(JSON.stringify({ detail: 'Durchlauf nicht gefunden' }), {
        status: 404,
        headers: { 'content-type': 'application/json' }
      })
    );
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Weiter' }));
    expect(await screen.findByText('Der Durchlauf wurde neu geladen.')).toBeInTheDocument();
    expect(screen.queryByText(/anderen Gerät/)).not.toBeInTheDocument();
  });

  it('is interactive again when the reloaded run starts at the same entry number', async () => {
    const other = {
      id: 2,
      entries: [
        { ...RUN.entries[1], n: 0 },
        { ...RUN.entries[1], n: 1 }
      ]
    };
    const { fetchMock } = mockApi({
      'POST /api/runs': other,
      'POST /api/runs/2/entries/0/answer': { correct: true, expected: 'Wahr', explanation: 'Ja.' }
    });
    const json = (body: unknown, status: number) =>
      new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
    fetchMock.mockImplementationOnce(async () => json({ id: 1, entries: [{ ...RUN.entries[1], n: 0 }] }, 200));
    fetchMock.mockImplementationOnce(async () => json({ detail: 'schon beantwortet' }, 409));
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Wahr' }));
    await screen.findByText(/auf einem anderen Gerät beantwortet/);
    const wahr = screen.getByRole('button', { name: 'Wahr' });
    expect(wahr).toBeEnabled();
    await userEvent.click(wahr);
    expect(await screen.findByText('Richtig')).toBeInTheDocument();
    expect(fetchMock.mock.calls.map((c) => c[0]).at(-1)).toBe('/api/runs/2/entries/0/answer');
  });

  it('starts the daily run without a subject', async () => {
    const { calls } = mockApi({ 'POST /api/runs': RUN });
    render(Page);
    await screen.findByText('Die Zelle');
    expect(calls[0].body).toBeUndefined();
    expect(screen.queryByRole('heading', { name: /Fach-Run/ })).not.toBeInTheDocument();
  });

  it('starts a subject run and names the subject', async () => {
    here.url = new URL('http://localhost/run?subject=3');
    const { calls } = mockApi({ 'POST /api/runs': { ...RUN, subject_id: 3, subject_name: 'Rechnungswesen' }, 'POST /api/runs/1/finish': SUMMARY });
    render(Page);
    expect(await screen.findByRole('heading', { name: 'Fach-Run: Rechnungswesen' })).toBeInTheDocument();
    expect(calls[0].body).toEqual({ subject_id: 3 });
    await userEvent.click(screen.getByRole('button', { name: 'Beenden' }));
    expect(await screen.findByRole('link', { name: 'Fertig' })).toHaveAttribute('href', '/subjects/3');
  });

  it('keeps the subject when the run is reloaded', async () => {
    here.url = new URL('http://localhost/run?subject=3');
    const subjectRun = { ...RUN, subject_id: 3, subject_name: 'Rechnungswesen' };
    const { calls, fetchMock } = mockApi({ 'POST /api/runs': subjectRun });
    fetchMock.mockImplementationOnce(async () => new Response(JSON.stringify(subjectRun), { status: 200, headers: { 'content-type': 'application/json' } }));
    fetchMock.mockImplementationOnce(async () =>
      new Response(JSON.stringify({ detail: 'schon beantwortet' }), { status: 409, headers: { 'content-type': 'application/json' } })
    );
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Weiter' }));
    await screen.findByText(/auf einem anderen Gerät beantwortet/);
    expect(fetchMock.mock.calls.at(-1)?.[1]?.body).toBe(JSON.stringify({ subject_id: 3 }));
    expect(calls).toHaveLength(1);
  });

  it('points an empty subject run back to its subject', async () => {
    here.url = new URL('http://localhost/run?subject=3');
    mockApi({ 'POST /api/runs': { id: null, subject_id: 3, subject_name: 'Rechnungswesen', entries: [] } });
    render(Page);
    expect(await screen.findByText(/Für Rechnungswesen gibt es gerade nichts/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Zum Fach' })).toHaveAttribute('href', '/subjects/3');
  });
});
