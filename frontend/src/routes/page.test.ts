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
  'GET /api/runs/open': [],
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

  it('asks for a missing result the plan reports next to a later registration', async () => {
    mockApi({
      ...BASE,
      'GET /api/plan': {
        ...EMPTY_PLAN,
        entries: [planEntry({ state: 'registered', sitting: '2027-01-31' })],
        conflicts: [
          { subject_id: 1, subject_name: 'Rechnungswesen', kind: 'needs_result', message: 'Für die Prüfung am 08.11.2026 fehlt das Ergebnis.' },
          { subject_id: 2, subject_name: 'Statistik', kind: 'two_in_month', message: 'Im Januar 2027 ist schon Rechnungswesen angesetzt.' }
        ]
      }
    });
    render(Page);
    const note = (await screen.findByText(/Für die Prüfung am 08\.11\.2026 fehlt das Ergebnis/)).closest('p')!;
    expect(note).toHaveTextContent('Ergebnis eintragen: Rechnungswesen.');
    expect(within(note).getByRole('link', { name: 'Zum Fach' })).toHaveAttribute('href', '/subjects/1');
    expect(screen.queryByText(/Im Januar 2027/)).not.toBeInTheDocument();
  });

  it('offers a subject run for the subject in focus', async () => {
    mockApi({
      ...BASE,
      'GET /api/plan': {
        ...EMPTY_PLAN,
        entries: [planEntry({ sitting: '2027-01-31', study_from: '2026-11-24', study_until: '2027-01-02' })],
        order: [1]
      }
    });
    render(Page);
    expect(await screen.findByRole('link', { name: 'Fach üben: Rechnungswesen' })).toHaveAttribute('href', '/run?subject=1');
  });

  it('lists every open subject run, the one in focus included', async () => {
    mockApi({
      ...BASE,
      'GET /api/plan': { ...EMPTY_PLAN, entries: [planEntry({ study_from: '2026-11-24', study_until: '2027-01-02' })], order: [1] },
      'GET /api/runs/open': [
        { id: 7, subject_id: 1, subject_name: 'Rechnungswesen', created_at: '2026-11-24T08:00:00Z', open_items: 3 },
        { id: 5, subject_id: 2, subject_name: 'Statistik', created_at: '2026-11-20T21:30:00Z', open_items: 1 }
      ]
    });
    render(Page);
    const runs = await screen.findByRole('region', { name: 'Offene Fach-Runs' });
    expect(within(runs).getByRole('link', { name: 'Fach-Run fortsetzen: Rechnungswesen' })).toHaveAttribute('href', '/run?subject=1');
    expect(within(runs).getByRole('link', { name: 'Fach-Run fortsetzen: Statistik' })).toHaveAttribute('href', '/run?subject=2');
    expect(within(runs).getByText('3 Fragen offen, begonnen am 24.11.2026')).toBeInTheDocument();
    expect(within(runs).getByText('1 Frage offen, begonnen am 20.11.2026')).toBeInTheDocument();
    expect(within(runs).getByText(/Beenden/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Fach üben: Rechnungswesen' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /Rechnungswesen/ })).toHaveLength(1);
  });

  it('shows no open subject runs section without one', async () => {
    mockApi({ ...BASE });
    render(Page);
    expect(await screen.findByRole('link', { name: 'Run starten' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Offene Fach-Runs' })).not.toBeInTheDocument();
  });
});
