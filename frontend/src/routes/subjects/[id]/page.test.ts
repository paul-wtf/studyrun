import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { mockApi } from '#lib/test/mockApi.ts';
import { planEntry, subject } from '#lib/test/planFixtures.ts';

const nav = vi.hoisted(() => ({ goto: vi.fn() }));
vi.mock('$app/state', () => ({ page: { params: { id: '1' } } }));
vi.mock('$app/navigation', () => nav);

import Page from './+page.svelte';

const MODULES = [
  { id: 4, name: 'Buchführung', position: 0, subject_id: 1, booklets: [] },
  { id: 5, name: 'Bilanzen', position: 1, subject_id: 1, booklets: [] },
  { id: 6, name: 'Anderes', position: 2, subject_id: null, booklets: [] }
];
const PLAN = { entries: [planEntry({ sitting: '2027-01-31', register_by: '2027-01-10' })], conflicts: [], order: [1], pace_per_day: 4 };
const PROGRESS = { week: { days: [], goal: 4, done_count: 0 }, subjects: [{ subject_id: 1, introduced: 0.8, solid: 0.35 }] };
const MOCK = { id: 12, subject_id: 1, subject_name: 'Rechnungswesen', finishing: false, finished: false, expired: false };

function routes(extra: Record<string, unknown> = {}, s = subject({ module_ids: [4, 5], unlocked: true, introduced_share: 0.8 })) {
  return {
    'GET /api/subjects/1': s,
    'GET /api/plan': PLAN,
    'GET /api/progress': PROGRESS,
    'GET /api/modules': MODULES,
    'GET /api/runs/current?subject_id=1': { run: null },
    'GET /api/subjects/1/mocks': [],
    ...extra
  };
}

describe('subject page', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    nav.goto.mockReset();
  });

  it('shows progress, modules and the plan entry of the subject', async () => {
    mockApi(routes());
    render(Page);
    expect(await screen.findByRole('heading', { name: 'Rechnungswesen', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Eingeführt' })).toHaveAttribute('aria-valuenow', '80');
    expect(screen.getByRole('progressbar', { name: 'Gefestigt' })).toHaveAttribute('aria-valuenow', '35');
    const modules = screen.getByRole('region', { name: 'Module' });
    expect(within(modules).getAllByRole('link').map((a) => a.textContent)).toEqual(['Buchführung', 'Bilanzen']);
    expect(screen.getByText('Anmelden bis 10.01.2027')).toBeInTheDocument();
  });

  it('starts a subject run', async () => {
    mockApi(routes());
    render(Page);
    expect(await screen.findByRole('link', { name: 'Fach üben' })).toHaveAttribute('href', '/run?subject=1');
  });

  it('continues an open subject run and says it holds back its items', async () => {
    mockApi(routes({ 'GET /api/runs/current?subject_id=1': { run: { id: 3, subject_id: 1, subject_name: 'Rechnungswesen', entries: [{ n: 0 }] } } }));
    render(Page);
    expect(await screen.findByRole('link', { name: 'Fach-Run fortsetzen' })).toHaveAttribute('href', '/run?subject=1');
    expect(screen.queryByRole('link', { name: 'Fach üben' })).not.toBeInTheDocument();
    expect(screen.getByText(/bis du ihn beendest/)).toBeInTheDocument();
  });

  it('starts a mock exam once unlocked and opens it', async () => {
    const { calls } = mockApi(routes({ 'POST /api/subjects/1/mock': MOCK }));
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Bosskampf' }));
    await vi.waitFor(() => expect(nav.goto).toHaveBeenCalledWith('/mock/12'));
    expect(calls.at(-1)).toMatchObject({ method: 'POST', path: '/api/subjects/1/mock' });
  });

  it('keeps the mock exam locked below the threshold', async () => {
    mockApi(routes({}, subject({ unlocked: false, introduced_share: 0.5 })));
    render(Page);
    expect(await screen.findByText(/Der Bosskampf öffnet bei 80 % eingeführter Kapitel \(jetzt 50 %\)/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Bosskampf/ })).not.toBeInTheDocument();
  });

  const OPEN = { id: 12, started_at: '2026-11-24T19:00:00Z', deadline: '2026-11-24T20:30:00Z', finished_at: null, score: null, passed: null };

  it('links straight to an open mock exam', async () => {
    const { calls } = mockApi(routes({ 'GET /api/subjects/1/mocks': [OPEN], 'GET /api/mock/12': MOCK }));
    render(Page);
    expect(await screen.findByRole('link', { name: 'Bosskampf fortsetzen' })).toHaveAttribute('href', '/mock/12');
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('completes the grading of a submitted mock exam', async () => {
    mockApi(
      routes({ 'GET /api/subjects/1/mocks': [OPEN], 'GET /api/mock/12': { ...MOCK, finishing: true } }, subject({ unlocked: false, introduced_share: 0.5 }))
    );
    render(Page);
    expect(await screen.findByRole('link', { name: 'Auswertung abschließen' })).toHaveAttribute('href', '/mock/12');
  });

  it('calls an open mock exam past its deadline expired', async () => {
    mockApi(routes({ 'GET /api/subjects/1/mocks': [OPEN], 'GET /api/mock/12': { ...MOCK, expired: true } }));
    render(Page);
    expect(await screen.findByRole('link', { name: 'Abgelaufen – Auswertung abschließen' })).toHaveAttribute('href', '/mock/12');
    expect(screen.queryByText('Bosskampf fortsetzen')).not.toBeInTheDocument();
  });

  it('shows the server reason when a mock exam cannot start', async () => {
    mockApi(
      routes({
        'POST /api/subjects/1/mock': new Response(JSON.stringify({ detail: 'Für dieses Fach gibt es noch keine Fragen.' }), {
          status: 409,
          headers: { 'content-type': 'application/json' }
        })
      })
    );
    render(Page);
    await userEvent.click(await screen.findByRole('button', { name: 'Bosskampf' }));
    expect(await screen.findByText('Für dieses Fach gibt es noch keine Fragen.')).toBeInTheDocument();
    expect(nav.goto).not.toHaveBeenCalled();
  });

  it('lists past mock exams with their score', async () => {
    const past = [
      { id: 9, started_at: '2026-11-20T17:00:00Z', deadline: '2026-11-20T18:30:00Z', finished_at: '2026-11-20T18:10:00Z', score: 64, passed: true },
      { id: 8, started_at: '2026-11-10T17:00:00Z', deadline: '2026-11-10T18:30:00Z', finished_at: '2026-11-10T18:20:00Z', score: 41, passed: false }
    ];
    mockApi(routes({ 'GET /api/subjects/1/mocks': past }));
    render(Page);
    const history = await screen.findByRole('region', { name: 'Bosskämpfe' });
    const rows = within(history).getAllByRole('listitem');
    expect(within(rows[0]).getByRole('link')).toHaveAttribute('href', '/mock/9');
    expect(within(rows[0]).getByText('64 %')).toBeInTheDocument();
    expect(within(rows[0]).getByText('Bestanden')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Nicht bestanden')).toBeInTheDocument();
  });

  it('corrects a recorded result', async () => {
    const s = subject({ attempts: [{ id: 3, sitting: '2026-06-14', status: 'failed' }] });
    const { calls } = mockApi(routes({ 'PATCH /api/attempts/3': { id: 3, sitting: '2026-06-14', status: 'passed' } }, s));
    render(Page);
    const attempts = await screen.findByRole('region', { name: 'Prüfungsversuche' });
    expect(within(attempts).getByText('Nicht bestanden')).toBeInTheDocument();
    await userEvent.click(within(attempts).getByRole('button', { name: 'Auf bestanden ändern' }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')).toMatchObject({ path: '/api/attempts/3', body: { status: 'passed' } });
  });
});
