import type { Conflict, PlanEntry, Subject } from '#lib/api/models.ts';

export const TODAY = '2026-11-24';

export function planEntry(extra: Partial<PlanEntry> = {}): PlanEntry {
  return {
    subject_id: 1,
    subject_name: 'Rechnungswesen',
    state: 'open',
    sitting: null,
    register_by: null,
    feasible: true,
    study_from: null,
    study_until: null,
    ...extra
  };
}

export function subject(extra: Partial<Subject> = {}): Subject {
  return {
    id: 1,
    name: 'Rechnungswesen',
    duration_minutes: 90,
    earliest_semester: '3a',
    recommended_semester: 4,
    not_before: null,
    pass_mark: 50,
    sittings: ['2026-11-08', '2026-12-06', '2027-01-31', '2027-03-14'],
    module_ids: [],
    attempts: [],
    introduced_share: 0.5,
    unlocked: false,
    ...extra
  };
}

export const CONFLICTS: Conflict[] = [
  { subject_id: 1, subject_name: 'Rechnungswesen', kind: 'no_feasible_sitting', message: 'Beim aktuellen Tempo reicht die Zeit für keinen Termin.' },
  { subject_id: 2, subject_name: 'Statistik', kind: 'two_in_month', message: 'Im Januar 2027 ist schon Rechnungswesen angesetzt.' },
  { subject_id: 2, subject_name: 'Statistik', kind: 'before_not_before', message: 'Angemeldet für den 31.01.2027, möglich erst ab dem 01.03.2027.' },
  { subject_id: 3, subject_name: 'Recht', kind: 'no_material', message: 'Stoff fehlt: Für dieses Fach gibt es noch kein Heft.' },
  { subject_id: 4, subject_name: 'Marketing', kind: 'missing_semester', message: 'Für Semester 5a fehlt das Startdatum.' },
  { subject_id: 5, subject_name: 'Personal', kind: 'planned_not_allowed', message: 'Der gewählte Termin 06.12.2026 geht nicht mehr: Die Anmeldung war bis zum 15.11.2026.' },
  { subject_id: 6, subject_name: 'Logistik', kind: 'squeezes_other', message: 'Dein Termin für Logistik macht die Vorbereitung auf Statistik zu knapp.' }
];
