import type { Attempt, Plan, PlanEntry, PlanState, Subject } from '#lib/api/models.ts';
import { addDays } from '#lib/dates.ts';

export const REGISTRATION_DAYS = 21;
export const DEADLINE_NOTICE_DAYS = 14;

export const STATE_LABEL: Record<PlanState, string> = {
  open: 'Vorschlag',
  planned: 'Geplant',
  registered: 'Angemeldet',
  passed: 'Bestanden',
  needs_result: 'Ergebnis fehlt',
  no_material: 'Stoff fehlt',
  not_plannable: 'Nicht planbar',
  sittings_pending: 'Termine folgen'
};

export function subjectFacts(subject: Subject): string {
  return [
    `${subject.duration_minutes} Minuten`,
    `ab Semester ${subject.earliest_semester}`,
    subject.recommended_semester === null ? null : `empfohlen im ${subject.recommended_semester}. Semester`
  ]
    .filter(Boolean)
    .join(' · ');
}

const COMING: PlanState[] = ['open', 'planned', 'registered'];
const UNREGISTERED: PlanState[] = ['open', 'planned'];

const bySitting = (a: PlanEntry, b: PlanEntry) => (a.sitting ?? '').localeCompare(b.sitting ?? '');

export function nextExam(entries: PlanEntry[], today: string): PlanEntry | undefined {
  return entries
    .filter((e) => COMING.includes(e.state) && e.sitting !== null && e.sitting >= today)
    .sort(bySitting)[0];
}

export function deadlinesSoon(entries: PlanEntry[], today: string, days = DEADLINE_NOTICE_DAYS): PlanEntry[] {
  const last = addDays(today, days);
  return entries
    .filter((e) => UNREGISTERED.includes(e.state) && e.register_by !== null && e.register_by >= today && e.register_by <= last)
    .sort((a, b) => (a.register_by ?? '').localeCompare(b.register_by ?? ''));
}

export function focusSubject(plan: Plan): PlanEntry | undefined {
  const ordered = plan.order
    .map((id) => plan.entries.find((e) => e.subject_id === id))
    .filter((e): e is PlanEntry => e !== undefined);
  return ordered.find((e) => e.study_from !== null && e.study_until !== null && e.study_until > e.study_from) ?? ordered[0];
}

export function attemptFor(subject: Subject, entry: PlanEntry): Attempt | undefined {
  const status = entry.state === 'needs_result' ? 'registered' : entry.state;
  return subject.attempts.find((a) => a.sitting === entry.sitting && a.status === status);
}

export interface SittingChoice {
  date: string;
  closed: boolean;
}

export function sittingChoices(subject: Subject, today: string): SittingChoice[] {
  const opensUntil = addDays(today, REGISTRATION_DAYS);
  return [...subject.sittings]
    .filter((d) => d >= today)
    .sort()
    .map((date) => ({ date, closed: date < opensUntil }));
}
