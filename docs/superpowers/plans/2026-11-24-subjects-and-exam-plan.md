# Subjects, exam plan and exam preparation: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Paul groups his modules into DAA subjects, imports his exam plan, gets planned sittings with registration deadlines, and studyrun learns towards the next exam, with subject runs, mock exams, a weekly goal and per-subject progress.

**Architecture:** New tables `subjects`, `semesters`, `exam_attempts`, `mock_exams`; `modules.subject_id`; `runs.subject_id`. A pure planner module computes the plan from subjects, attempts, effort and pace on every request. Run assembly takes the planner's study order for new items and a 21-day pull-forward window. The mock exam is its own entity and route set. The frontend gains a subjects page, a plan page, a subject page and a mock exam player.

**Tech Stack:** as before: FastAPI, SQLAlchemy 2 async, Alembic, FSRS (`fsrs` 6.3), SvelteKit with the Zen tokens, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-24-subjects-and-exam-plan-design.md`

## Global Constraints

- Rules: at most one exam per calendar month (counting future planned and registered attempts and passed ones). Registration closes 21 days before a sitting. Never plan before the eligible date (start of `earliest_semester`) or before `not_before`. Aim at the recommended semester when feasible.
- Semester calendar: a start date per half-semester label (`3a`, `3b`, …, `7b`). A missing label makes subjects that need it "nicht planbar", and the import accepts that.
- Effort: unlearned active items (no ReviewState, or FSRS state Learning/Relearning) + chapters not introduced; chapters without items (pending/generating/failed) estimate 2 items per page; a subject without material → "Stoff fehlt", no proposal.
- Pace: items moved out of "new" per study day over the last 28 Berlin days (study day = a day with ≥ 1 review log); fallback `settings.run_new_items` per day when fewer than 7 study days exist.
- Study order: one subject at a time in plan order; the next one starts when the previous one's material is learned. Modules without a subject come after all planned subjects.
- Pull-forward: within 21 days before a planned or registered sitting, the daily run adds items of that subject due within those 21 days, up to `run_review_cap` total reviews.
- Mock exam: unlocks at ≥ 80 % of the subject's chapters introduced (excluding skipped); duration = subject duration; pass mark default 50 % (per subject); no feedback until the end; free answers graded at the end under the daily cap, ungraded → self-rating.
- Weekly goal: `weekly_goal_days = 4` (setting), Monday to Sunday, Berlin days, a day counts with ≥ 1 answered item (review log).
- Progress: introduced = introduced chapters / chapters (excluding skipped); solid = items with FSRS retrievability ≥ 0.9 today / active items.
- The exam-plan JSON for Paul is never committed. Test fixtures use invented subjects and dates.
- Everything else as in the earlier plans: German UI, Berlin days, Zen tokens only (no hex in components), ≥ 44 px targets, signed Conventional Commits, no attribution, humanizer on commit messages, nix dev shell for all commands, podman Postgres `studyrun-pg`.

## Review Focus

1. Today is a sitting day or 21 days before one: the deadline boundary (`today == sitting - 21` is still open; the day after is closed) and the exam day itself. Test in Task 3.
2. Two subjects share a sitting date (as in Paul's plan): the one-per-month rule must push the second one, never plan both. Test in Task 3.
3. Paul registers for a sitting the planner didn't propose (e.g. earlier): it stays fixed, others are redistributed around it, no silent change. Test in Task 3.
4. A subject run or mock exam started late in the evening and continued after midnight: resume must find it (per kind, not per Berlin day for mock exams). Test in Task 4 and Task 5.
5. The daily cap is reached in the middle of grading a mock exam: the remaining free answers become self-rated, the result is still computed. Test in Task 5.

---

### Task 1: Data model and migration

**Files:**
- Modify: `backend/src/studyrun/models/db.py`
- Create: `backend/migrations/versions/0004_subjects_and_exams.py`, tests in `backend/tests/models/test_subjects.py`

**Interfaces:**
- Produces:
  - `Subject(id, name: str unique, duration_minutes: int, earliest_semester: str, recommended_semester: int | None, not_before: date | None, pass_mark: int = 50, sittings: list[str] (JSONB, ISO dates, sorted), created_at)`
  - `Semester(label: str PK, starts_on: date)`
  - `AttemptStatus = planned | registered | passed | failed`; `ExamAttempt(id, subject_id → Subject cascade, sitting: date, status: AttemptStatus, created_at, updated_at)`
  - `Module.subject_id: int | None → Subject (SET NULL)`
  - `Run.subject_id: int | None → Subject (SET NULL)`
  - `MockExam(id, subject_id → Subject cascade, started_at, deadline: datetime, finished_at: datetime | None, entries: list[dict] JSONB, score: int | None, passed: bool | None)`

- [ ] **Step 1: Tests:** `test_subject_cascade_deletes_attempts_and_mock_exams`, `test_module_subject_set_null_on_delete`, `test_subject_name_unique`; the existing migration test must cover 0004.
- [ ] **Step 2: Run, FAIL.** **Step 3: Implement + migration (upgrade and downgrade).** **Step 4: full backend suite, ruff, mypy, PASS.**
- [ ] **Step 5: Commit** `feat(backend): add subjects, exam attempts and mock exams`.

### Task 2: Subjects API and import

**Files:**
- Create: `backend/src/studyrun/routes/subjects.py`, `backend/tests/routes/test_subjects.py`
- Modify: `backend/src/studyrun/routes/modules.py` (`PATCH /api/modules/{id}` accepts `subject_id: int | null`; `ModuleOut` gains `subject_id`)

**Interfaces:**
- Produces:
  - `POST /api/subjects/import` body `{semesters: {label: date}, subjects: [{name, duration_minutes, earliest_semester, recommended_semester?, sittings: [date]}]}` → `{created: int, updated: int}`. Upsert by name; never touches attempts, `not_before`, `pass_mark`, module assignments. Upserts semesters.
  - `GET /api/subjects` → list of `SubjectOut {id, name, duration_minutes, earliest_semester, recommended_semester, not_before, pass_mark, sittings, module_ids, attempts: [AttemptOut]}`; `GET /api/subjects/{id}`; `PATCH /api/subjects/{id} {not_before?, pass_mark? (1-100)}`.
  - `GET /api/semesters`, `PUT /api/semesters/{label} {starts_on}`.
  - `POST /api/subjects/{id}/attempts {sitting, status: planned|registered}` (sitting must be one of the subject's sittings → else 422; replaces an existing planned/registered future attempt of that subject); `PATCH /api/attempts/{id} {status}` (passed/failed only for sittings ≤ today; else 409); `DELETE /api/attempts/{id}` (only planned/registered).
- German error details.

- [ ] **Step 1: Tests:** import creates then updates (idempotent, keeps attempts and module links); invalid JSON shapes → 422; attempt rules (sitting not in list, result before the date, replace planned by registered); module assignment and unassignment.
- [ ] **Steps 2-4:** RED, implement, GREEN (+ ruff, mypy).
- [ ] **Step 5: Commit** `feat(backend): manage subjects, semesters and exam attempts`.

### Task 3: Planner

**Files:**
- Create: `backend/src/studyrun/planning/{__init__,effort,pace,planner}.py`, `backend/src/studyrun/routes/plan.py`, `backend/tests/planning/test_planner.py`, `test_effort.py`, `test_pace.py`

**Interfaces:**
- Produces:
  - `planner.plan(subjects: list[PlanSubject], semesters: dict[str, date], today: date, pace_per_day: float) -> Plan` (pure, no DB). `PlanSubject(id, name, earliest_semester, recommended_semester, not_before, sittings: list[date], effort_items: int, has_material: bool, attempts: list[(date, status)])`. `Plan(entries: list[PlanEntry], order: list[int], conflicts: list[Conflict])`; `PlanEntry(subject_id, state: open|planned|registered|passed|needs_result|no_material|not_plannable|sittings_pending, sitting: date | None, register_by: date | None, feasible: bool, study_from: date | None, study_until: date | None)`; `Conflict(subject_id, kind: no_feasible_sitting|two_in_month|before_not_before|no_material|missing_semester, message_de)`.
  - `effort.subject_effort(session, subject_id) -> tuple[int, bool]`; `pace.measured_pace(session, settings, now) -> float`.
  - `GET /api/plan` → `PlanOut` (entries with subject names, conflicts, `order`).
- Algorithm (the tests pin it): (1) fixed: registered attempts and their months; passed subjects done; registered past sittings without result → `needs_result`, month still occupied. (2) For open subjects with material, in order of (recommended semester, earliest eligible sitting, name): walk candidate sittings ≥ max(eligible date, not_before, today + 21 days) (registered/planned stored attempts are taken as given), prefer the first sitting inside the recommended semester window, otherwise the earliest after; skip months already taken; feasible when `study_from + ceil(effort/pace) days ≤ sitting`, where `study_from` is the previous subject's `study_until` (or today). If infeasible, try later sittings; if none, `no_feasible_sitting` conflict and the subject keeps the latest candidate with `feasible: false`. (3) A stored `planned` attempt Paul chose by hand is kept if still allowed, else a conflict.

- [ ] **Step 1: Tests (pure planner):** recommended-semester targeting; eligibility from semester start; `not_before`; deadline boundary (`today = sitting - 21` allowed, `sitting - 20` not); two subjects on the same date → second moves to another month; registered earlier sitting kept and others redistributed; effort too large → later sitting chosen; no material → no proposal + conflict; missing semester label → `not_plannable` + conflict; sittings all beyond the list → `sittings_pending`; past registered without result → `needs_result`. Effort and pace tests against the DB (unseen + learning items, page estimate for unready chapters, skipped chapters excluded, pace fallback).
- [ ] **Steps 2-4:** RED, implement, GREEN.
- [ ] **Step 5: Commit** `feat(backend): plan exam sittings from effort and pace`.

### Task 4: Runs follow the plan; subject run

**Files:**
- Modify: `backend/src/studyrun/study/assemble.py`, `backend/src/studyrun/routes/runs.py`, tests in `backend/tests/study/test_assemble.py`, `backend/tests/routes/test_runs.py`

**Interfaces:**
- Consumes: `planner.plan` and the effort/pace helpers (Task 3).
- Produces:
  - `build_run(session, settings, now, *, subject_id: int | None = None) -> list[RunEntry]`.
  - Daily (`subject_id=None`): new items and intros come from the first subject in `plan.order` with unlearned material, then modules without a subject, then today's behaviour; reviews from everything; pull-forward for the subject whose planned/registered sitting is within 21 days.
  - Subject run: only that subject's items: due first, new items with intros (gate counted within the subject), then pull-forward by nearest due; same caps as the daily run.
  - `POST /api/runs {subject_id?}`, `GET /api/runs/current?subject_id=`: one unfinished run per (Berlin day, subject_id); `RunOut` gains `subject_id` and `subject_name`.

- [ ] **Step 1: Tests:** focus follows plan order and moves on when a subject's material is learned; unassigned modules after planned subjects; no subjects → unchanged behaviour (existing tests stay green); pull-forward only inside 21 days and within the cap; subject run contains only that subject and falls back to pulled-forward items when nothing is due; resume per subject; daily and subject runs coexist the same day.
- [ ] **Steps 2-4:** RED, implement, GREEN; regenerate `schema.d.ts`.
- [ ] **Step 5: Commit** `feat(backend): learn towards the next exam and add subject runs`.

### Task 5: Mock exam backend

**Files:**
- Create: `backend/src/studyrun/study/mock.py`, `backend/src/studyrun/routes/mock.py`, tests `backend/tests/study/test_mock.py`, `backend/tests/routes/test_mock.py`

**Interfaces:**
- Produces:
  - `select_mock_items(session, subject_id, duration_minutes) -> list[int]`: per-kind minutes mc 1.5, true_false 1, cloze 2, free 6; fill ~90 % of the duration; draw across chapters weighted by 1 − mean retrievability (unseen counts as 0), at least one item per introduced chapter when time allows; deterministic for a given seed.
  - `POST /api/subjects/{id}/mock` → 409 unless unlocked; creates `MockExam` (deadline = now + duration) or returns the unfinished one. `GET /api/mock/{id}` (public views only, plus `deadline`, `answered` flags). `POST /api/mock/{id}/answers/{n} {answer}` stores without feedback (409 after finish). `POST /api/mock/{id}/finish` (also auto-applies when called after the deadline): checks objective answers locally, grades free answers (Feature.grade, daily cap), marks ungraded ones `grading_unavailable`, records reviews for every answered item, computes score (objective 0/100, free = grade score; unanswered 0) as the mean, `passed = score ≥ pass_mark`, per-chapter breakdown. `POST /api/mock/{id}/self-rate/{n}` for ungraded free answers (updates score). `GET /api/subjects/{id}/mocks` → history.

- [ ] **Step 1: Tests:** unlock threshold (79 % vs 80 %, skipped chapters excluded); selection fits the duration and spans chapters; no feedback in answer responses; finish after the deadline; cap reached mid-grading → remaining self-rate, score still computed; resume after midnight; reviews recorded once.
- [ ] **Steps 2-4:** RED, implement, GREEN; regenerate schema.
- [ ] **Step 5: Commit** `feat(backend): add mock exams per subject`.

### Task 6: Weekly goal and progress backend

**Files:**
- Create: `backend/src/studyrun/routes/progress.py`, `backend/tests/routes/test_progress.py`; Modify: `config.py` (`weekly_goal_days: int = 4`)

**Interfaces:**
- Produces: `GET /api/progress` → `{week: {days: [{date, done: bool}] (Mon-Sun), goal: int, done_count: int}, subjects: [{subject_id, introduced: float, solid: float}]}`.

- [ ] **Step 1: Tests:** week boundaries in Berlin (Sunday 23:30 vs Monday 00:10), DST week; introduced excludes skipped; solid via retrievability at now.
- [ ] **Steps 2-4, Step 5: Commit** `feat(backend): report the weekly goal and progress per subject`.

### Task 7: Frontend: subjects, plan, home, subject page

**Files:**
- Create: `frontend/src/routes/subjects/+page.svelte` (list, import JSON file upload, semester dates, not-before/pass mark edit), `frontend/src/routes/subjects/[id]/+page.svelte` (progress bars, modules, attempts, "Fach üben", "Bosskampf" when unlocked, mock history), `frontend/src/routes/plan/+page.svelte` (timeline of sittings with subjects, per subject state, `Anmelden bis …`, buttons Angemeldet / Anderen Termin wählen / Bestanden / Nicht bestanden / Ergebnis eintragen, conflicts on top), components and tests.
- Modify: `+layout.svelte` nav (Start, Plan, Fächer, Module, Gemeldet, Kosten — check 360 px in screenshots), home (`+page.svelte`: next exam with countdown, any registration deadline within 14 days, week dots, "Fach üben" for the current focus subject), modules page (subject selector per module), run page (title shows the subject for subject runs).

- [ ] **Step 1: Tests** per page/component (import upload sends the file; attempt buttons call the right endpoints; deadline banner appears ≤ 14 days; week dots; subject run starts with `subject_id`).
- [ ] **Steps 2-4:** RED, implement, GREEN (`pnpm test && pnpm check && pnpm build`); screenshots of the new pages via `scripts/screenshots.mjs` (add scenarios), both themes, 1280 and 360.
- [ ] **Step 5: Commit** `feat(frontend): add subjects, the exam plan and the subject page`.

### Task 8: Frontend: mock exam player

**Files:**
- Create: `frontend/src/routes/mock/[id]/+page.svelte`, components for the timer and the result view, tests.

**Interfaces:**
- Consumes: Task 5 endpoints.
- Timer counts down from `deadline` (server time, not client start); at 0 the page calls finish. Navigation between items, answered markers, "Abgeben" with a confirmation. The result view shows the total, pass/fail, per-chapter breakdown, each item with the right answer, and self-rating buttons for ungraded free answers.

- [ ] **Steps 1-4:** tests (timer reaches 0 → finish called once; reload resumes with the remaining time; no feedback before finish; self-rate updates the score), implement, GREEN, screenshots.
- [ ] **Step 5: Commit** `feat(frontend): add the mock exam player`.

### After the tasks (controller, needs Paul's go-ahead for publishing)

- Build Paul's import JSON from his exam plan PDF, the course outline (recommended semesters: Deutsch 3, Englisch 4, Mathematik I 4, Mathematik II 6, Naturwissenschaft 3, Politik 6, M1 6, M2 5, M3 5, M4 6, M5 6, M6 4, M7 7, M8 7) and his semester calendar (6-month semesters, 4a = 2026-10-01, b = +3 months), outside the repo.
- Release 0.3.0, bump the fluxcd app, roll out, and hand Paul the JSON to import.
