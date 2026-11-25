import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import Page from './+page.svelte';
import { mockApi } from '#lib/test/mockApi.ts';
import { planEntry, subject } from '#lib/test/planFixtures.ts';

const SUBJECTS = [subject(), subject({ id: 2, name: 'Statistik', earliest_semester: '5a', recommended_semester: null })];
const PLAN = {
  entries: [
    planEntry({ state: 'registered', sitting: '2027-01-31' }),
    planEntry({ subject_id: 2, subject_name: 'Statistik', state: 'not_plannable' })
  ],
  conflicts: [],
  order: [1],
  pace_per_day: 4
};
const SEMESTERS = [{ label: '3a', starts_on: '2026-04-01' }];

describe('subjects page', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('lists the subjects with their plan state and links to them', async () => {
    mockApi({ 'GET /api/subjects': SUBJECTS, 'GET /api/plan': PLAN, 'GET /api/semesters': SEMESTERS });
    render(Page);
    const card = (await screen.findByRole('link', { name: 'Rechnungswesen' })).closest('article')!;
    expect(screen.getByRole('link', { name: 'Rechnungswesen' })).toHaveAttribute('href', '/subjects/1');
    expect(within(card).getByText('Angemeldet')).toBeInTheDocument();
    expect(within(card).getByText(/31\.01\.2027/)).toBeInTheDocument();
    const other = screen.getByRole('link', { name: 'Statistik' }).closest('article')!;
    expect(within(other).getByText('Nicht planbar')).toBeInTheDocument();
    expect(screen.getByLabelText('Semester 5a')).toBeInTheDocument();
  });

  it('reloads after an import', async () => {
    let list: typeof SUBJECTS = [];
    const { calls } = mockApi({
      'GET /api/subjects': () => list,
      'GET /api/plan': () => ({ ...PLAN, entries: list.length ? PLAN.entries : [] }),
      'GET /api/semesters': SEMESTERS,
      'POST /api/subjects/import': () => {
        list = SUBJECTS;
        return { created: 2, updated: 0, kept_sittings: 0 };
      }
    });
    render(Page);
    expect(await screen.findByText(/Noch keine Fächer/)).toBeInTheDocument();
    await userEvent.upload(screen.getByLabelText('JSON-Datei'), new File(['{"semesters":{},"subjects":[]}'], 'p.json'));
    await userEvent.click(screen.getByRole('button', { name: 'Importieren' }));
    expect(await screen.findByRole('link', { name: 'Statistik' })).toBeInTheDocument();
    expect(calls.filter((c) => c.path === '/api/subjects')).toHaveLength(2);
  });
});
