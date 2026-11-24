# studyrun: subjects, exam plan and exam preparation

Date: 2026-11-24
Status: draft, awaiting Paul's approval

## Why

Paul wants studyrun to prepare him for his exams on its own: he groups his
modules into the subjects the DAA examines, the app plans which exam sitting
to aim for, and the daily run learns towards the next exam. Before an exam he
also wants to practise one subject on purpose and see how ready he is.

This is stage 3 of the original design
(`2026-11-23-studyrun-design.md`, sections "Exam plan" and "Motivation"),
widened by subjects and a subject run, and adjusted to how the DAA actually
examines.

## How the DAA examines (from Paul's exam plan, L21, as of 10.07.2026)

- Every exam belongs to one **subject** ("Fach"): for example Mathematik I,
  Deutsch/Kommunikation, Politik, or "Führungsaufgaben und
  Personalverantwortung übernehmen (Modul 6)". The DAA's modules 1 to 8 are
  subjects in this sense.
- A subject has a duration (90 or 180 minutes), an earliest semester from
  which it may be taken (3a, 4a, 4b, 5a, 5b, 6a, 7a) and six fixed sittings
  between October 2026 and March 2028, roughly every three months.
- Several subjects share sitting dates, for example two exams on 08.11.2026.
- The DAA's course outline ("schematischer Lehrgangsablauf") names the
  semester in which each exam is recommended. Mathematik has two exams
  (Mathematik I in the 4th semester, Mathematik II in the 6th). The final
  project in the 7th semester is not an exam in this sense and stays out.
- A semester lasts six months; "a" is its first half and "b" its second
  (Paul confirmed 24.11.2026). A label like 4b therefore becomes eligible
  three months after 4a.
- Paul registers for a sitting himself, at the latest three weeks before it.
- As of 24.11.2026 Paul has passed no exam and is registered for none. He is
  in the 4th semester (as of October 2026).

## Goals

- Subjects. A subject is the exam unit. Paul's studyrun modules (his groups
  of booklets) are each assigned to at most one subject.
- The exam data per subject: name, duration, earliest semester and the list
  of sittings, plus Paul's state for it: open, planned for a sitting,
  registered for a sitting, passed, or failed (with the sitting).
- Import of the exam plan from a JSON file, so Paul's real data gets in
  without typing and without the DAA document going into the public repo.
- A planner that proposes a sitting for every open subject and keeps the plan
  up to date.
- The daily run follows the plan.
- A subject run on demand.
- A mock exam ("Bosskampf") per subject.
- A weekly goal and progress per subject.

## Non-goals

- Parsing the DAA PDF inside the app. The JSON for Paul's plan is produced
  once outside the repo.
- Notifications, email or calendar sync. Deadlines show up in the app.
- Grades. The app tracks passed or failed, nothing more.
- Exam locations.

## Anti-goals

- A plan that silently changes a sitting Paul has registered for.
- A run that becomes a cram session of 60 items. Runs stay at 10 to 15
  minutes. The subject run and the mock exam are the deliberate exceptions,
  and Paul starts them himself.
- A missed registration deadline because the app didn't make it visible.

## Constraints

- Rules from the original design: at most one exam per calendar month. M6
  only after its advanced seminar (date still open, so a "not before" date
  per subject, empty until known).
- A subject can't be planned for a sitting before it becomes eligible. The
  eligible date of a semester comes from Paul's semester calendar (a start
  date per semester label, entered in the app).
- Registration closes 21 days before a sitting.
- Study time 5 to 10 hours a week; the planner works from Paul's measured
  pace, not from that range.
- Single user, German UI, Berlin days, the existing daily cap for grading,
  the Zen look.

## Approaches

1. **Rule-based planner with proposals (chosen).** Estimate the remaining
   effort per subject from its material and Paul's pace, assign each open
   subject the earliest feasible sitting under the rules, show it on a
   timeline, and let Paul move or confirm sittings. Registered sittings are
   fixed; everything else is redistributed.
2. **Manual only.** Paul picks every sitting himself, and the app only learns
   towards them. It is simpler, but it leaves the feasibility judgment to
   him, which is what he wants to get rid of.
3. **Claude as planner.** Rejected: it has a running cost, and its proposals
   would be harder to follow than rules.

Paul chose 1 on 24.11.2026.

## Design

### Subjects and modules

- New entity `Subject`: name, duration in minutes, earliest semester label,
  recommended semester (from the course outline, optional), "not before"
  date (optional), sittings (dates), pass mark for the mock exam.
- New entity `ExamAttempt`: subject, sitting date, status (planned,
  registered, passed, failed). A subject is open when it has no attempt that
  is planned, registered or passed. Failed attempts stay as history and the
  subject is open again. A registered attempt whose date has passed without
  a result shows "Ergebnis eintragen" and still occupies its month. Only
  planned and registered attempts in the future, and passed ones, count for
  the one-exam-per-month rule. (My call.)
- `Module.subject_id` is optional. Modules without a subject keep working as
  today: they get no exam focus, but their reviews still come due.
- A subject's material is the material of its modules.

### Course settings

Semester calendar: a start date per half-semester label (3a, 3b, 4a, …), weekly study days for the goal
(default 4 of 7), the "not before" date per subject, and the cap of one exam
per month (always on).

### Import

`POST /api/subjects/import` takes JSON:

```json
{
  "semesters": {"3a": "2026-04-01", "4a": "2026-10-01"},
  "subjects": [
    {"name": "Mathematik I", "duration_minutes": 90, "earliest_semester": "3a",
     "recommended_semester": 4,
     "sittings": ["2026-11-08", "2027-01-31", "2027-05-09"]}
  ]
}
```

The import is idempotent by subject name: a re-import updates durations,
semesters and sittings and never touches Paul's state, registrations or
module assignments. The JSON for Paul's real plan is generated once from his
PDF and handed to him; it doesn't go into git.

### Planner

- **Effort per subject:** the number of active items not yet learned (unseen,
  or still in learning), including those of chapters not yet introduced.
  Chapters that have no items yet (pending, generating, verifying, failed)
  count with an estimate of two items per page, the generation target.
  Skipped chapters don't count. A subject without any module or
  booklet is "Stoff fehlt": the planner shows its sittings but proposes none
  and lists it as a conflict until material is uploaded. (My call.) Effort is
  converted to days using Paul's measured pace (items learned per study day over the last 28
  days; until there is enough history, the default from the run sizes, four
  new items per run).
- **Order of study:** one subject at a time. The planner lays the subjects
  out in the order of their sittings, and each subject's learning starts when the previous one's
  material is learned, not when its exam is over. Reviews of earlier
  subjects keep running. (My call: it uses the time before a late sitting
  instead of leaving it idle.)
- **Eligibility:** a sitting is eligible when its date is on or after the
  start date of the subject's earliest semester. A semester label without a
  start date makes the subject "nicht planbar" with a hint to enter the
  date; the import accepts it.
- **"Today"** for the 21-day rule and all date logic is the Berlin date.
- **Target:** the recommended semester is a preference. The planner takes
  the earliest good sitting from the start of the recommended semester on;
  if there is none, it takes the latest good sitting before that start. It
  never goes before the eligible date or the "not before" date. A subject
  without a recommended semester, or whose recommended semester has no
  start date, takes the earliest good sitting. Paul can still pick another
  eligible sitting by hand.
- **No sitting yet:** a subject with no possible sitting at all (eligible,
  after its "not before" date, at least 21 days away) is shown as "Termine
  folgen"; a later import adds them.
- **Assignment:** registered, passed and past registered sittings are fixed
  first and block their month; a sitting Paul planned by hand is kept next
  if it is still possible. Open subjects are then processed by recommended
  semester (subjects without one last), then earliest eligible sitting,
  then name. A sitting is good for a subject when it is possible, lies in
  a month without another planned, registered or passed exam, leaves enough
  days for the subject's effort, and leaves every subject that was feasible
  before still feasible. When no sitting is good, the planner takes the
  latest free sitting that harms no other subject and marks it not
  feasible; when every free sitting would harm another subject, the subject
  gets no sitting. A sitting Paul planned by hand stays even when it harms
  another subject, with a conflict that names it.
- **Output:** the plan per subject (sitting, registration deadline, whether
  it is feasible at the current pace, its study window) and conflicts (no
  feasible sitting left, naming the subject it would squeeze where that is
  the reason; two registered exams in one month; registered before the "not
  before" date; a hand-planned sitting that is no longer possible or that
  squeezes another subject; no material; a missing semester start).
- The plan is recomputed when it is shown, not stored. Only Paul's choices
  are stored: a moved sitting ("planned") and registrations.

### Plan page

A timeline of the coming sittings with the subject on each. For every
subject: its state, the proposed or registered sitting, "Anmelden bis
<date>" while that date lies ahead, buttons "Angemeldet", "Anderen Termin
wählen", and after the exam "Bestanden" or "Nicht bestanden" (a failed
subject returns to open and gets planned again). Conflicts are shown at the
top. The home screen shows the next exam and any registration deadline
within 14 days.

### Daily run follows the plan

- New items come from the first subject in the planner's study order that
  still has unlearned material (all its modules, in module and chapter
  order), instead of from the first module by position. Modules without a
  subject come next once no planned subject has new material left. With no
  subjects at all, the current behaviour stays.
- Reviews still come from everything that is due. The backlog gate stays.
- In the last 21 days before an exam, the run also pulls items of that
  subject forward that would come due within those 21 days, up to the review
  cap, so the subject gets fresh shortly before the exam.

### Subject run

Started from the subject or from the home screen ("Fach üben"). It contains
items of that subject only: due items first, then new items (with intros),
then items pulled forward by nearest due date. It has the normal run length,
can be started as often as Paul likes, and its answers count for scheduling
as usual. It doesn't replace the daily run. A run records which subject it
belongs to (none for the daily run), and resume works per kind.

### Mock exam ("Bosskampf")

- Per subject. It unlocks once most of the subject's material has been
  introduced (default 80 % of its chapters).
- The duration is the subject's exam duration, with a visible timer. The
  items are drawn across the subject's chapters, weighted towards chapters
  with weaker recall, in a number that fits the duration (an estimate per
  item kind).
- It runs like an exam: no feedback until the end, then a score per item,
  the total in percent, pass or fail against a pass mark (default 50 %,
  adjustable per subject), and per chapter what went wrong. Free answers are
  graded at the end, one call per answer, under the existing daily cap.
  Items left ungraded because the cap was reached are shown as such, and
  Paul can rate them himself.
- Answers count for scheduling. Results are kept, so the subject page shows
  the history of mock exams.

### Weekly goal and progress

- Weekly goal: a run done (at least one answered item) on N of 7 days,
  default 4, Monday to Sunday, Berlin days. Shown on the home screen as
  dots for the week. A missed day breaks nothing, and there is no streak.
- Progress per subject: introduced (share of chapters introduced) and solid
  (share of the subject's items whose FSRS retrievability is at least 90 %
  today), as two bars on the subject and plan pages.

## Calls I made (Paul can overturn them)

- A subject is the DAA exam unit. Paul's studyrun modules sit below it.
- The exam plan comes in via a JSON import. The DAA PDF doesn't go into the
  public repo, and the JSON for Paul is produced outside it.
- The plan is computed, not stored. Only Paul's decisions are stored.
- The 21-day pull-forward window before an exam equals the registration
  period.
- The mock exam pass mark defaults to 50 %. The DAA's real pass mark is
  unknown.
- The weekly goal is 4 of 7 days, Monday to Sunday.

## Left to the builder

- Data model details, migrations, API shape, and how the pace is measured.
- UI layout within the Zen look.
- The per-kind time estimates for the mock exam.
