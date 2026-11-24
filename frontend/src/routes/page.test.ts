import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/svelte';
import Page from './+page.svelte';
import { mockApi } from '#lib/test/mockApi.ts';
import { planEntry } from '#lib/test/planFixtures.ts';

const COSTS = {
  today: { total: 0.12, by_feature: { generate: 0, verify: 0, grade: 0.1, tutor: 0.02 } },
  cap_today: 0.5
};
const MODULES = [{ id: 1, name: 'Bio', position: 0, booklets: [{ chapters: { ready: 3 } }] }];

const EMPTY_PLAN = { entries: [], conflicts: [], order: [], pace_per_day: 4 };
const week = (done: boolean[]) => ({
  days: done.map((d, i) => ({ date: `2026-11-${23 + i}`, done: d })),
  goal: 4,
  done_count: done.filter(Boolean).length
});
const PROGRESS = { week: week([true, true, false, false, false, false, false]), subjects: [] };

const BASE = {
  'GET /api/costs': COSTS,
  'GET /api/modules': MODULES,
  'GET /api/runs/current': { run: null },
  'GET /api/plan': EMPTY_PLAN,
  'GET /api/progress': PROGRESS
};

describe('home', () => {
  beforeEach(() => vi.useFakeTimers({ now: new Date('2026-11-24T10:00:00Z'), toFake: ['Date'] }));
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('offers to start a run and shows the spend', async () => {
    mockApi({ ...BASE });
    render(Page);
    expect(await screen.findByRole('link', { name: 'Run starten' })).toHaveAttribute('href', '/run');
    expect(screen.getByText(/0,12/)).toBeInTheDocument();
    expect(screen.getByText(/0,50/)).toBeInTheDocument();
  });

  it('keeps generation spend apart from the grading cap', async () => {
    mockApi({
      ...BASE,
      'GET /api/costs': {
        today: { total: 4.12, by_feature: { generate: 3, verify: 1, grade: 0.1, tutor: 0.02 } },
        cap_today: 0.5
      }
    });
    render(Page);
    expect(await screen.findByText('Bewertung heute: 0,12 von 0,50 $')).toBeInTheDocument();
    expect(screen.getByText('Erzeugung heute: 4,00 $')).toBeInTheDocument();
    expect(screen.queryByText(/4,12/)).not.toBeInTheDocument();
  });

  it('leaves out the generation line when nothing was generated', async () => {
    mockApi({ ...BASE });
    render(Page);
    expect(await screen.findByText('Bewertung heute: 0,12 von 0,50 $')).toBeInTheDocument();
    expect(screen.queryByText(/Erzeugung/)).not.toBeInTheDocument();
  });

  it('offers to resume a run started today', async () => {
    mockApi({ ...BASE, 'GET /api/runs/current': { run: { id: 4, entries: [{ n: 0 }] } } });
    render(Page);
    expect(await screen.findByRole('link', { name: 'Run fortsetzen' })).toBeInTheDocument();
  });

  it('links to the modules when nothing is ready to study', async () => {
    mockApi({ ...BASE, 'GET /api/modules': [] });
    render(Page);
    expect(await screen.findByRole('link', { name: /Module/ })).toHaveAttribute('href', '/modules');
    expect(screen.queryByRole('link', { name: 'Run starten' })).not.toBeInTheDocument();
  });

  it('shows the week as dots', async () => {
    mockApi({ ...BASE });
    render(Page);
    expect(await screen.findByRole('list', { name: 'Diese Woche' })).toBeInTheDocument();
    expect(screen.getByText('2 von 4 Tagen')).toBeInTheDocument();
  });

  it('warns about registration deadlines within 14 days', async () => {
    mockApi({
      ...BASE,
      'GET /api/plan': {
        ...EMPTY_PLAN,
        entries: [
          planEntry({ sitting: '2026-12-29', register_by: '2026-12-08' }),
          planEntry({ subject_id: 2, subject_name: 'Statistik', sitting: '2026-12-30', register_by: '2026-12-09' })
        ]
      }
    });
    render(Page);
    const banner = await screen.findByRole('region', { name: 'Anmeldefristen' });
    expect(within(banner).getByText(/Rechnungswesen/)).toBeInTheDocument();
    expect(within(banner).getByText(/bis 08\.12\.2026/)).toBeInTheDocument();
    expect(within(banner).queryByText(/Statistik/)).not.toBeInTheDocument();
    expect(within(banner).getByRole('link', { name: 'Zum Plan' })).toHaveAttribute('href', '/plan');
  });

  it('shows no deadline banner when no deadline is near', async () => {
    mockApi({ ...BASE, 'GET /api/plan': { ...EMPTY_PLAN, entries: [planEntry({ sitting: '2027-01-31', register_by: '2027-01-10' })] } });
    render(Page);
    expect(await screen.findByText('Nächste Prüfung')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Anmeldefristen' })).not.toBeInTheDocument();
  });

  it('counts down to the next exam', async () => {
    mockApi({ ...BASE, 'GET /api/plan': { ...EMPTY_PLAN, entries: [planEntry({ state: 'registered', sitting: '2026-12-06' })] } });
    render(Page);
    const next = (await screen.findByText('Nächste Prüfung')).closest('section')!;
    expect(within(next).getByText('Rechnungswesen')).toBeInTheDocument();
    expect(within(next).getByText(/06\.12\.2026/)).toBeInTheDocument();
    expect(within(next).getByText(/in 12 Tagen/)).toBeInTheDocument();
    expect(within(next).getByText('Angemeldet')).toBeInTheDocument();
  });

  it('asks for the result of a past exam', async () => {
    mockApi({ ...BASE, 'GET /api/plan': { ...EMPTY_PLAN, entries: [planEntry({ state: 'needs_result', sitting: '2026-11-08' })] } });
    render(Page);
    expect(await screen.findByText(/Ergebnis eintragen: Rechnungswesen/)).toBeInTheDocument();
  });

  it('offers a subject run for the subject in focus', async () => {
    const { calls } = mockApi({
      ...BASE,
      'GET /api/plan': {
        ...EMPTY_PLAN,
        entries: [planEntry({ sitting: '2027-01-31', study_from: '2026-11-24', study_until: '2027-01-02' })],
        order: [1]
      },
      'GET /api/runs/current?subject_id=1': { run: null }
    });
    render(Page);
    expect(await screen.findByRole('link', { name: 'Fach üben: Rechnungswesen' })).toHaveAttribute('href', '/run?subject=1');
    expect(calls.some((c) => c.path === '/api/runs/current?subject_id=1')).toBe(true);
  });

  it('offers to continue the open subject run of the subject in focus', async () => {
    mockApi({
      ...BASE,
      'GET /api/plan': { ...EMPTY_PLAN, entries: [planEntry({ study_from: '2026-11-24', study_until: '2027-01-02' })], order: [1] },
      'GET /api/runs/current?subject_id=1': { run: { id: 7, entries: [{ n: 0 }] } }
    });
    render(Page);
    expect(await screen.findByRole('link', { name: 'Fach-Run fortsetzen: Rechnungswesen' })).toHaveAttribute('href', '/run?subject=1');
  });
});
