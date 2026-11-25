import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import SemesterDates from './SemesterDates.svelte';
import { mockApi } from '#lib/test/mockApi.ts';
import { subject } from '#lib/test/planFixtures.ts';

describe('SemesterDates', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('lists known semesters and the ones subjects need but lack, in semester order', () => {
    render(SemesterDates, {
      semesters: [{ label: '10a', starts_on: '2029-04-01' }, { label: '3a', starts_on: '2026-04-01' }],
      subjects: [subject({ earliest_semester: '5b', recommended_semester: 4 })],
      onchange: vi.fn()
    });
    expect(screen.getAllByLabelText(/^Semester /).map((el) => el.getAttribute('aria-label'))).toEqual([
      'Semester 3a', 'Semester 4a', 'Semester 5b', 'Semester 10a'
    ]);
    expect(screen.getByLabelText('Semester 3a')).toHaveValue('2026-04-01');
    expect(screen.getAllByText('fehlt')).toHaveLength(2);
  });

  it('saves a start date', async () => {
    const onchange = vi.fn();
    const { calls } = mockApi({ 'PUT /api/semesters/5b': { label: '5b', starts_on: '2027-10-01' } });
    render(SemesterDates, { semesters: [], subjects: [subject({ earliest_semester: '5b', recommended_semester: null })], onchange });
    await fireEvent.input(screen.getByLabelText('Semester 5b'), { target: { value: '2027-10-01' } });
    await userEvent.click(screen.getByRole('button', { name: '5b speichern' }));
    await vi.waitFor(() => expect(onchange).toHaveBeenCalled());
    expect(calls[0]).toMatchObject({ method: 'PUT', path: '/api/semesters/5b', body: { starts_on: '2027-10-01' } });
  });
});
