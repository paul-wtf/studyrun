# studyrun design

Date: 2026-11-23
Status: draft, awaiting Paul's approval

## Why

Paul is studying part-time for the state-certified technician qualification
(distance learning at DAA-Technikum, course form L21, 4th semester as of
October 2026) while working full-time. He has 5 to 10 hours a week for it.
Right now he barely studies, because he can't get himself to start on
reading the course booklets or on a whole evening of calculation exercises.

studyrun should take over part of that classic studying with something easy
to start and not boring, and still prepare him for the exams. Classic
studying won't disappear, but there should be less of it.

It works if Paul studies on most days, a little each time, without it
feeling like a chore, and goes into each exam prepared.

## Goals

- Short daily sessions that need no decision about what to study.
- Learning by retrieval: questions, stepwise calculations, cases, and
  explaining things in his own words. Rereading plays no part.
- An AI tutor that talks with him about the material, grades free answers
  and walks him through problems.
- An exam plan that decides which module comes next and when each exam
  should be.
- Usable at the desk (mostly evenings, sometimes during work hours) and on
  the phone.
- API costs that are visible and capped.

## Non-goals

- Multi-user support. Paul is the only user.
- Replacing the booklets completely. They remain the source.
- Native mobile apps. A responsive web app, installable as a PWA, is enough.
- General knowledge content. Everything comes from Paul's own course
  material.
- Calendar sync, notifications and reminders in v1 (possible later).

## Anti-goals

Any of these makes the app a failure, even if it technically works:

- It turns into a chore of its own: long sessions, a pile of overdue
  reviews, or a streak that breaks after one missed day and makes him give
  up.
- It teaches things that are wrong or not in the course. Generated content
  that drifts from the booklets is worse than none.
- It eats the API credit. Paul has watched Claude extra usage run out
  quickly, so costs have to stay small and visible.
- The course material leaks. The booklets are DAA's copyrighted material
  and must never end up in a git repository or anywhere public.

## Constraints

- Exam rules: at most one exam per month. M6 (leadership and personnel
  responsibility) comes only after its advanced seminar, whose date is
  still open.
- API: the Claude API with Paul's own key from platform.claude.com, paid
  from the credit there (about €100). Anthropic's terms don't allow using
  the Claude Max subscription (OAuth) inside his own app, so the app uses
  an API key.
- Hosting: Paul's cluster `paulwtf`, deployed like his other self-written
  apps (see Stack).
- Course material: the booklets are PDFs with a text layer.
- Exam aids: the usual ones, meaning calculator, formula collection and
  dictionary.
- Still unknown until Paul is home: the booklets themselves, his
  specialization (Fachrichtung) and the exam plan (which modules are left,
  their exam formats, dates already set, the end of the course). The design
  must work for any subject and exam format.
- Also unknown: whether the cluster is reachable from his employer's
  network. The phone covers work hours either way.

## Approaches

1. Anki with cards generated from the booklets. It is ready immediately,
   proven, and has a phone app. It stays flashcard drilling, though, with
   no stepwise calculations and no exam plan, so it does little about the
   actual problem.
2. An own web app with a generated question bank and no AI at runtime:
   quizzes, calculations with changing numbers, cases, a daily session,
   streaks, mock exams and an exam planner. It has no running costs, but it
   can't grade free answers or hold a conversation.
3. Approach 2 plus an AI tutor through the Claude API. The tutor grades
   free answers, checks explanations and plays through cases as a
   dialogue, which makes this the most engaging option. It costs a few
   euros a month.

Paul picked 3. He was sceptical about the API costs, so the estimate and
the safeguards are below. Within 3 there were two variants: the tutor in
the app through the API, or the tutor in the Claude app with studyrun as a
connector (free under the subscription). Paul chose the API, since his
credit is on platform.claude.com.

## How Paul uses it

### studyrun teaches, the booklet is the reference

studyrun is Paul's first contact with a chapter; he does not read the
booklet beforehand. A new chapter opens with an introduction: the summary
card and a short lesson from the tutor, a few minutes long with a question
or two in between. After that, the chapter's items enter the rotation. The
booklet stays available for reference, and every item and every tutor
answer links to its page.

That makes the app responsible for all of the material. "Covered" in the
progress bars means introduced and practised in studyrun, and the planner
estimates the pace from runs alone.

### The daily run

The home screen shows one big button for today's run. A run takes 10 to 15
minutes, and the app puts it together from:

- review items that spaced repetition says are due,
- new items from the module the exam plan puts first, or the introduction
  of its next chapter,
- one longer item: a stepwise calculation, a case, or an "explain it" task
  graded by the tutor.

Types and topics are mixed, never ten of the same in a row. Paul can stop a
run at any point and it counts for what he did. Afterwards a short summary
says what went well and what comes back tomorrow.

Besides the run, Paul can start a tutor conversation on any chapter at any
time, or practise a single item type ("just calculations today").

### Item types

Every item is generated from the booklets and linked to the booklet and
page it comes from.

- Quick questions: multiple choice, true/false with a reason, fill in the
  gap. Feedback comes instantly with a short explanation.
- Short free answers: a definition, a list, a "why does …". The tutor
  grades them against the source passage and gives a score and what was
  missing.
- Stepwise calculations: a task with randomized numbers. At first the app
  shows the worked solution, and after each success it leaves one more
  step to Paul (faded worked examples) until he solves the task alone.
  Results are checked numerically, with tolerance and units.
- Cases: a short scenario from an industrial or operations setting, with
  questions about it, optionally played as a dialogue with the tutor. Paul
  works in operational technology and networks at an energy company, so
  cases from that world fit well.
- Explain it: Paul explains a concept in his own words, and the tutor asks
  back where the explanation is vague or wrong (Feynman technique).

### Tutor modes

- Explain to me: Paul explains and the tutor probes the gaps.
- Walk me through: the tutor guides him through a calculation by asking
  questions, without giving the solution.
- Case: the tutor plays a scenario (a fault, a decision, a staff
  conversation for M6) and reacts to what Paul does.
- Ask freely: questions about a chapter, answered from the booklet with
  page references.

The tutor answers in German, keeps it short, and works from the booklet
passage it was given. If the material doesn't cover something, it says so
and doesn't make anything up.

### Motivation

The mechanics are kept light. They should bring Paul back, not make him
grind.

- A weekly goal in place of a daily streak, for example runs on 4 of 7
  days. A missed day doesn't break anything.
- A progress bar per module showing how much of the material is covered
  and how solid it is.
- A boss fight before each exam: a mock exam under time pressure, built
  from the module's items and graded like the exam. It uses the format,
  duration and pass mark entered for that exam and allows the same aids
  (calculator, formula collection, dictionary), so calculation tasks
  assume a calculator. It unlocks once the module is covered well enough
  and can be repeated.
- No debt spiral: when reviews pile up after a break, the run caps them
  and spreads the backlog over the next days, so Paul never faces a huge
  overdue count.

### Exam plan

Paul enters his modules and their exams. An exam is a separate entity,
because a module can have more than one exam, or one that isn't a written
test. Each exam has a format (written, oral, project, …), a duration, a
pass mark, allowed aids, and a date once one is set. The course end date
bounds the plan. The constraints are M6 after the seminar date and at most
one exam per month. The first data comes from the exam plan Paul will send
along with the booklets.

The planner proposes an exam month for each unscheduled module from the
amount of material, his weekly study time and the constraints, and shows
the plan as a timeline. Paul can move exams. The planner flags conflicts:
two exams in one month, M6 before its seminar, or a module that can't be
covered in time at the current pace.

The plan drives the run. The module with the next exam gets most of the new
items, and the others get reviews so they don't fade.

## Content pipeline

1. Paul uploads a booklet (PDF) to a module in the app.
2. The backend sends it to Claude as PDF documents in chapter-sized
   chunks, through the Message Batches API. Sending the PDF instead of
   extracted text keeps formulas, tables and figures intact. Batches cost
   half the normal price and usually finish within an hour (at most 24
   hours), which is fine for a booklet uploaded once.
3. For each chapter, Claude produces a short summary card, the main
   concepts, and items of every type, each with its source page.
   Calculation items include a parameterized formula, value ranges and the
   worked steps.
4. The backend checks what it can: the schema, and each calculation
   formula evaluated with sample values against Claude's own result. Items
   that fail are dropped.
5. A second Claude pass, also batched, checks every remaining item against
   its source page, asking whether it is correct and whether it is actually in the
   booklet. Items that fail are dropped. Only then does the chapter go live.
6. While studying, Paul can flag any item as wrong, not in the course, or
   unclear. Flagged items leave the rotation and appear in a review list
   where he can delete or fix them.

Booklets and generated content live only in the app's database and
storage, never in the repository.

## Cost estimate and safeguards

Claude API prices as of October 2026, per million tokens: Opus 5.5 $4
input, $20 output, $0.20 cached input; Sonnet 5.5 $2, $10, $0.20.

- A tutor session of 15 to 20 minutes, with about 10 exchanges and 6,000
  cached tokens of instructions and source, costs about $0.08 on Sonnet 5.5
  and $0.15 on Opus 5.5. Daily use comes to about $2 to $5 a month.
- Grading one free answer costs under one cent.
- Generating content costs about $2.30 per 100 pages: Opus 5.5 generates,
  Sonnet 5.5 verifies, both through the Batch API at half price. A PDF page
  counts as text and image, about 3,500 input tokens, and both passes read
  it. 1,000 pages come to about $23, once. Without batching and with Opus
  for both passes it would be about $5.80 per 100 pages.

Safeguards:

- Every API call records its token usage and cost from the response's
  `usage` field. A cost page shows today, this month and each feature.
- A configurable daily cap for tutor and grading (default $0.50). Once it
  is reached, the AI features pause until the next day, and quizzes and
  calculations keep working. Content generation has its own budget and asks
  first when the estimate is high.
- Prompt caching for the system prompt and source passages.
- Paul also sets a spend limit in the Claude Console.
- The first real tutor session gets measured against this estimate before
  anything else builds on it.

## Stack

The stack matches Paul's other self-written apps (tidalwave, linkhop), so
build, deployment and operations work the same way.

| Layer | Tech |
|---|---|
| Backend | Python 3.12 (uv), FastAPI, SQLAlchemy 2 (async), asyncpg, Alembic |
| AI | Anthropic Python SDK, streaming for tutor replies |
| Spaced repetition | FSRS (`fsrs` package) |
| Frontend | SvelteKit (`adapter-static`), TypeScript, responsive, PWA manifest |
| Database | Postgres 16 (CNPG in production) |
| Uploaded PDFs | In the database or on a volume (builder's choice) |
| Tests | pytest, Vitest, Playwright |
| Packaging | Docker images on ghcr.io, Helm chart on GitHub Pages |
| Deploy | FluxCD app in `paulwtf-infra/fluxcd`, Traefik, cert-manager, external-dns |
| Auth | authentik forward-auth through a Traefik middleware, with a dedicated authentik application: 30-day session and no passkey check per session (the admin flow re-checks every 8 hours, which would interrupt nearly every run); no login in the app itself |
| Secrets | Claude API key and DB credentials from Vault through ExternalSecrets |

## Decided

- Tutor and grading run in the app through the Claude API with Paul's own
  key.
- Model: Opus 5.5 by default for tutor, grading and content generation,
  Sonnet 5.5 for the verification pass, configurable per feature. Sonnet
  5.5 would save a few euros a month on the tutor, and content quality
  matters more there.
- Content generation and verification go through the Message Batches API.
- Single user behind authentik, with no user model in the app.
- Content comes only from Paul's booklets.
- Deployed on `paulwtf` the same way as tidalwave.
- studyrun teaches each chapter; Paul does not read the booklet first.
- A dedicated authentik application with a 30-day session for studyrun.

The builder still has to verify that forward-auth works for the installed
PWA (redirects in standalone mode, the manifest and service worker,
streamed tutor replies) and that the frontend handles an expired session.

## Calls I made (Paul can overturn them)

- Name: `studyrun`, after the daily run.
- Repository: public under `paul-wtf` like the sibling apps, code only,
  with invented course content in test fixtures. A private repo would
  change nothing else.
- Content generation happens in the app and not offline in Claude Code, so
  Paul can add new booklets himself. With verification and batching it
  costs about $2.30 per 100 pages.
- A weekly goal in place of a streak, because a broken streak is a common
  reason to quit.
- Hostname: `studyrun.paul.wtf`.
- A verification pass for all generated items, since only calculations can
  be checked by machine. It adds about a quarter to the generation cost,
  and in return Paul doesn't have to approve every chapter.

## Left to the builder

- Data model, API shape, prompt wording, and how booklets are chunked.
- How the run is assembled (the balance between reviews, new items and the
  long item) and how the planner estimates effort per module, as long as
  both follow the behaviour described above.
- UI layout and visual design.
- Whether PDFs live in Postgres or on a volume.
