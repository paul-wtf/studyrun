import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import Page from './+page.svelte';
import { mockApi } from '#lib/test/mockApi.ts';
import { CONFLICTS, planEntry, subject } from '#lib/test/planFixtures.ts';

const SUBJECTS = [
  subject({ sittings: ['2026-12-06', '2027-01-31', '2027-03-14'] }),
  subject({ id: 2, name: 'Statistik', sittings: ['2027-01-31', '2027-02-28'] })
];
const PLAN = {
  entries: [
    planEntry({ state: 'open', sitting: '2027-01-31', register_by: '2027-01-10', study_from: '2026-11-24', study_until: '2027-01-02' }),
    planEntry({ subject_id: 2, subject_name: 'Statistik', state: 'registered', sitting: '2027-02-28', study_from: '2027-01-02', study_until: '2027-02-20' })
  ],
  conflicts: CONFLICTS.slice(0, 2),
  order: [1, 2],
  pace_per_day: 3.5
};
const PROGRESS = { week: { days: [], goal: 4, done_count: 0 }, subjects: [{ subject_id: 1, introduced: 0.4, solid: 0.1 }, { subject_id: 2, introduced: 0, solid: 0 }] };

describe('plan page', () => {
  beforeEach(() => vi.useFakeTimers({ now: new Date('2026-11-24T10:00:00Z'), toFake: ['Date'] }));
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('puts the conflicts on top, then the timeline and a card per subject in study order', async () => {
    mockApi({ 'GET /api/plan': PLAN, 'GET /api/subjects': SUBJECTS, 'GET /api/progress': PROGRESS });
    render(Page);
    const conflicts = await screen.findByRole('region', { name: 'Konflikte' });
    const timeline = screen.getByRole('region', { name: 'Termine' });
    expect(conflicts.compareDocumentPosition(timeline) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByRole('article').map((a) => a.getAttribute('aria-label'))).toEqual(['Rechnungswesen', 'Statistik']);
    expect(screen.getByText(/3,5 neue Fragen pro Tag\./)).toBeInTheDocument();
  });

  it('shows the coming sittings by month with the subjects and which one is taken', async () => {
    mockApi({ 'GET /api/plan': PLAN, 'GET /api/subjects': SUBJECTS, 'GET /api/progress': PROGRESS });
    render(Page);
    const timeline = await screen.findByRole('region', { name: 'Termine' });
    const months = within(timeline).getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
    expect(months).toEqual(['Dezember 2026', 'Januar 2027', 'Februar 2027', 'März 2027']);
    const jan = within(timeline).getByRole('listitem', { name: '31.01.2027' });
    expect(within(jan).getByText('Rechnungswesen')).toBeInTheDocument();
    expect(within(jan).getByText('Statistik')).toBeInTheDocument();
    expect(within(jan).getByText('Vorschlag')).toBeInTheDocument();
    const feb = within(timeline).getByRole('listitem', { name: '28.02.2027' });
    expect(within(feb).getByText('Angemeldet')).toBeInTheDocument();
  });

  it('reloads the plan after a registration', async () => {
    const { calls } = mockApi({
      'GET /api/plan': PLAN,
      'GET /api/subjects': SUBJECTS,
      'GET /api/progress': PROGRESS,
      'POST /api/subjects/1/attempts': { id: 1, sitting: '2027-01-31', status: 'registered' }
    });
    render(Page);
    const card = await screen.findByRole('article', { name: 'Rechnungswesen' });
    await userEvent.click(within(card).getByRole('button', { name: 'Angemeldet' }));
    await vi.waitFor(() => expect(calls.filter((c) => c.path === '/api/plan')).toHaveLength(2));
  });

  it('invites an import when there are no subjects', async () => {
    mockApi({ 'GET /api/plan': { entries: [], conflicts: [], order: [], pace_per_day: 4 }, 'GET /api/subjects': [], 'GET /api/progress': PROGRESS });
    render(Page);
    expect(await screen.findByRole('link', { name: 'Prüfungsplan importieren' })).toHaveAttribute('href', '/subjects');
  });

  it('lists subjects outside the study order with open results first and passed ones last', async () => {
    const extra = [
      subject({ id: 3, name: 'Alt', sittings: [] }),
      subject({ id: 4, name: 'Offen', sittings: [] })
    ];
    mockApi({
      'GET /api/plan': {
        ...PLAN,
        conflicts: [],
        entries: [
          ...PLAN.entries,
          planEntry({ subject_id: 3, subject_name: 'Alt', state: 'passed', sitting: '2026-06-14' }),
          planEntry({ subject_id: 4, subject_name: 'Offen', state: 'needs_result', sitting: '2026-11-08' })
        ]
      },
      'GET /api/subjects': [...SUBJECTS, ...extra],
      'GET /api/progress': PROGRESS
    });
    render(Page);
    await screen.findByRole('region', { name: 'Termine' });
    expect(screen.getAllByRole('article').map((a) => a.getAttribute('aria-label'))).toEqual(['Rechnungswesen', 'Statistik', 'Offen', 'Alt']);
  });
});
