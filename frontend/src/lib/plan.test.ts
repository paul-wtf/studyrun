import { describe, expect, it } from 'vitest';
import type { Plan, PlanEntry, Subject } from '#lib/api/models.ts';
import { deadlinesSoon, focusSubject, nextExam, attemptFor, sittingChoices, subjectFacts } from './plan.ts';

const entry = (subject_id: number, extra: Partial<PlanEntry> = {}): PlanEntry => ({
  subject_id,
  subject_name: `Fach ${subject_id}`,
  state: 'open',
  sitting: null,
  register_by: null,
  feasible: true,
  study_from: null,
  study_until: null,
  ...extra
});

const subject = (extra: Partial<Subject> = {}): Subject => ({
  id: 1,
  name: 'Fach 1',
  duration_minutes: 90,
  earliest_semester: '3a',
  recommended_semester: null,
  not_before: null,
  pass_mark: 50,
  sittings: [],
  module_ids: [],
  attempts: [],
  introduced_share: 0,
  unlocked: false,
  ...extra
});

const TODAY = '2026-11-24';

describe('deadlinesSoon', () => {
  it('lists registration deadlines from today to 14 days ahead', () => {
    const entries = [
      entry(1, { sitting: '2026-12-29', register_by: '2026-12-08' }),
      entry(2, { sitting: '2026-12-30', register_by: '2026-12-09', state: 'planned' }),
      entry(3, { sitting: '2026-12-15', register_by: TODAY }),
      entry(4, { sitting: '2026-12-14', register_by: '2026-11-23' }),
      entry(5, { sitting: '2026-12-29', register_by: '2026-12-08', state: 'registered' })
    ];
    expect(deadlinesSoon(entries, TODAY).map((e) => e.subject_id)).toEqual([3, 1]);
  });
});

describe('nextExam', () => {
  it('takes the nearest coming sitting that is proposed, planned or registered', () => {
    const entries = [
      entry(1, { sitting: '2027-01-31' }),
      entry(2, { sitting: '2026-11-08', state: 'needs_result' }),
      entry(3, { sitting: '2026-12-13', state: 'registered' }),
      entry(4, { sitting: TODAY, state: 'passed' })
    ];
    expect(nextExam(entries, TODAY)?.subject_id).toBe(3);
  });

  it('counts an exam today as next', () => {
    expect(nextExam([entry(1, { sitting: TODAY, state: 'registered' })], TODAY)?.subject_id).toBe(1);
  });

  it('is undefined without coming sittings', () => {
    expect(nextExam([entry(1, { state: 'no_material' })], TODAY)).toBeUndefined();
  });
});

describe('focusSubject', () => {
  const plan = (entries: PlanEntry[], order: number[]): Plan => ({ entries, order, conflicts: [], pace_per_day: 4 });

  it('is the first subject in study order with material left to learn', () => {
    const p = plan(
      [
        entry(1, { study_from: TODAY, study_until: TODAY }),
        entry(2, { study_from: TODAY, study_until: '2026-12-10' }),
        entry(3, { study_from: '2026-12-10', study_until: '2027-01-02' })
      ],
      [1, 2, 3]
    );
    expect(focusSubject(p)?.subject_id).toBe(2);
  });

  it('falls back to the first subject in order when everything is learned', () => {
    const p = plan([entry(1, { study_from: TODAY, study_until: TODAY }), entry(2)], [1]);
    expect(focusSubject(p)?.subject_id).toBe(1);
  });

  it('is undefined without a study order', () => {
    expect(focusSubject(plan([entry(1)], []))).toBeUndefined();
  });
});

describe('attemptFor', () => {
  it('finds the open attempt behind a plan entry', () => {
    const s = subject({
      attempts: [
        { id: 7, sitting: '2026-06-01', status: 'failed' },
        { id: 8, sitting: '2026-12-13', status: 'registered' }
      ]
    });
    expect(attemptFor(s, entry(1, { state: 'registered', sitting: '2026-12-13' }))?.id).toBe(8);
    expect(attemptFor(s, entry(1, { state: 'open', sitting: '2026-12-13' }))).toBeUndefined();
  });
});

describe('sittingChoices', () => {
  it('offers coming sittings and marks those whose registration closed', () => {
    const s = subject({ sittings: ['2026-11-08', TODAY, '2026-12-15', '2026-12-16', '2027-01-31'] });
    expect(sittingChoices(s, TODAY)).toEqual([
      { date: TODAY, closed: true },
      { date: '2026-12-15', closed: false },
      { date: '2026-12-16', closed: false },
      { date: '2027-01-31', closed: false }
    ]);
  });
});

describe('subjectFacts', () => {
  it('joins duration and semesters with separators', () => {
    expect(subjectFacts(subject({ recommended_semester: 4 }))).toBe('90 Minuten · ab Semester 3a · empfohlen im 4. Semester');
    expect(subjectFacts(subject())).toBe('90 Minuten · ab Semester 3a');
  });
});
