# studyrun core: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A deployed, single-user web app where Paul uploads a course booklet, gets verified quiz and free-answer items generated from it, and studies them in a daily run that is scheduled by spaced repetition, with API costs recorded and capped.

**Architecture:** A FastAPI backend with Postgres holds modules, booklets (PDF bytes), chapters, items, review state, runs and an API-call ledger. A worker task inside the backend process turns pending chapters into items through the Claude API (generate, validate, verify). A static SvelteKit frontend talks to `/api`. In production both sit behind authentik forward-auth on `studyrun.paul.wtf`.

**Tech Stack:** Python 3.12 (uv), FastAPI, SQLAlchemy 2 async, asyncpg, Alembic, pydantic-settings, `anthropic` SDK, `pypdf`, `fsrs`; SvelteKit (`adapter-static`), TypeScript, Vite, Vitest, pnpm; Docker, Helm, GitHub Actions, FluxCD, CNPG, Traefik, authentik.

**Spec:** `docs/superpowers/specs/2026-11-23-studyrun-design.md`

This is the first of three plans. It covers the content pipeline, the run with quick questions and free answers, flags, costs and deployment. The follow-up plans are outlined at the end.

## Global Constraints

- Mirror `~/git/tidalwave` for layout, tooling and conventions: `backend/` (src layout, `uv`, ruff line length 100, mypy, pytest-asyncio auto mode, `tests/testdb.py` + `conftest.py` transaction-per-test pattern), `frontend/` (pnpm, SvelteKit adapter-static, nginx image), `helm/studyrun/`, `.github/workflows/{backend,frontend,helm}.yml`. Copy and rename rather than reinvent.
- Env prefix `STUDYRUN_`. Python package `studyrun`. Images `ghcr.io/paul-wtf/studyrun-backend` and `-frontend`. Chart repo `https://paul-wtf.github.io/studyrun`.
- Single user, no auth code in the app. Everything under `/api` and `/` sits behind forward-auth in production.
- UI copy and all tutor/grader output are German. Code, comments, docs, commit messages are English.
- Booklets and generated content never go into git. Test fixtures use invented course content generated in the test itself.
- Claude: model IDs exactly `claude-opus-5-5` (default for generate and grade) and `claude-sonnet-5-5` (default for verify), configurable per feature. Generation and verification go through the Message Batches API (half price); grading is a normal synchronous request. Before writing the client, invoke the `claude-api` skill and read its `python/claude-api/README.md` (structured outputs, PDF document blocks, prompt caching, effort, refusal fallbacks) and `python/claude-api/batches.md`. Do not guess SDK signatures. Batch results arrive in any order; key them by `custom_id`. Enable the server-side refusal fallback (`fallbacks: "default"` with beta `server-side-fallback-2026-07-01`) as the skill prescribes for Opus 5.5. Effort: generate `high`, verify `medium`, grade `low`.
- Prices (USD per million tokens), in `config.py` as data: `claude-opus-5-5` input 4.00, output 20.00, cache read 0.20, cache write 5.00; `claude-sonnet-5-5` input 2.00, output 10.00, cache read 0.20, cache write 2.50. Batch requests cost half of every price. Cache write is assumed at 1.25× input; check it against the live pricing page linked from the skill's `shared/live-sources.md` and correct the table if it differs.
- Budget defaults: `daily_ai_cap_usd = 0.50` (grade, later tutor), `generation_daily_budget_usd = 10.00` (generate + verify), `generation_confirm_usd = 5.00`, `generation_estimate_usd_per_page = 0.025`, `generation_max_in_flight = 3` (chapters with an open batch at once; this bounds how far the daily generation budget can be overshot, since batch costs are only known on collection).
- "Today" and "this month" are local days in `Europe/Berlin` (setting `timezone`), never UTC days.
- Run defaults: `run_review_cap = 8`, `run_new_items = 4`. Chapters longer than `max_chapter_pages = 40` are split into windows of `chapter_window_pages = 15`.
- Upload limit `upload_max_bytes = 50 MiB`.
- Commits: Conventional Commits, scopes `backend`, `frontend`, `helm`, `ci`, `docs`, `deploy`. Commit message text goes through the `humanizer` skill (embedded mode) before committing. No `Co-Authored-By`, no mention of Claude, Claude Code, Anthropic or AI in any commit, comment or doc. Commits are gpg-signed; never disable signing. On host `dev`, run `echo probe | gpg --clearsign --pinentry-mode error -u "$(git config user.signingkey)" > /dev/null` before the first commit and stop to ask Paul to unlock if it fails.
- Comments: none by default. Only behaviour of foreign systems, deliberate absences, otherwise arbitrary-looking numbers, or why the obvious way was not taken.
- Anything the implementation itself leaves open (a missing column in an API response, a test that has to follow a new migration) is finished in the same task, not reported as a side finding. Things that were already broken before this branch are named and left alone.
- Backend tests need Postgres: `docker compose -f backend/docker-compose.yml up -d postgres` (on `paul-desktop`, `docker` is podman). Run tests with `uv run pytest -v` from `backend/`.

## Review Focus

1. Paul studies at 23:30 or 00:30 Berlin time. The daily cap, "today" on the cost page and the run's resume rule must use the Berlin day, including across the DST change. Test in Task 3 and Task 8.
2. The grading call fails mid-run (budget reached, API error, refusal). The run must go on: Paul sees the model answer and rates himself. Test in Task 8.
3. A bad upload: not a PDF, encrypted, no text layer, over the size limit, no outline. Each gets a clear German error or a sensible fallback, never a 500 or a stuck booklet. Test in Task 4 and Task 6.
4. Paul comes back after three weeks with 200 items due. The run still holds at most 8 reviews, never exposes an overdue count, and the backlog drains over the following days. Test in Task 7.
5. Claude returns malformed items (source page outside the chapter, MC answer index out of range, duplicate options, cloze without exactly one gap). They are dropped before verification, and a chapter whose items all fail ends `failed` with a reason instead of `ready` and empty. Test in Task 5.

---

### Task 1: Backend skeleton

**Files:**
- Create: `backend/pyproject.toml`, `backend/.python-version`, `backend/docker-compose.yml`, `backend/alembic.ini`, `backend/migrations/{env.py,script.py.mako}`, `backend/src/studyrun/{__init__,config,db,deps,main}.py`, `backend/src/studyrun/routes/{__init__,health}.py`, `backend/tests/{conftest,testdb}.py`, `backend/tests/test_health.py`, `backend/tests/test_config.py`, `.gitignore`
- Copy from tidalwave and rename: `testdb.py`, the fixtures in `conftest.py` (drop the Last.fm env vars), `migrations/env.py`, `db.py`.

**Interfaces:**
- Produces: `Settings` (all values in Global Constraints, plus `database_url`, `anthropic_api_key: str = ""`, `model_generate`, `model_verify`, `model_grade`, `log_level`); `get_settings()`, `get_session()` dependencies in `deps.py`; `create_app() -> FastAPI` with all routers mounted under `/api`; `GET /api/health -> {"status": "ok"}`; test fixtures `db_session` and `api` (yields `(client, app)`).
- Dependencies: fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, anthropic, pypdf, fsrs, python-multipart, tzdata. Dev: pytest, pytest-asyncio, ruff, mypy.

- [ ] **Step 1: Write `test_health_ok` (GET `/api/health` returns 200 and `{"status": "ok"}`) and `test_settings_defaults` (asserts `daily_ai_cap_usd == 0.50`, `timezone == "Europe/Berlin"`, `run_review_cap == 8`, `model_grade == "claude-opus-5-5"`, `model_verify == "claude-sonnet-5-5"`).**
- [ ] **Step 2: Run them.** `uv run pytest tests/test_health.py tests/test_config.py -v`. Expected: FAIL, module `studyrun` missing.
- [ ] **Step 3: Implement the skeleton files listed above.**
- [ ] **Step 4: Run tests, ruff and mypy.** `uv run pytest -v && uv run ruff check src tests && uv run mypy src`. Expected: all pass.
- [ ] **Step 5: Commit** `chore(backend): scaffold the FastAPI service`.

### Task 2: Data model and baseline migration

**Files:**
- Create: `backend/src/studyrun/models/{__init__,db}.py`, `backend/migrations/versions/<rev>_baseline_schema.py`, `backend/tests/models/test_db_models.py`, `backend/tests/test_migrations.py` (adapt tidalwave's: upgrade head in a scratch schema, compare with `Base.metadata`, downgrade to base).

**Interfaces:**
- Produces these SQLAlchemy models (all ids `int` identity, timestamps `timestamptz`):
  - `Module(id, name: str, position: int, created_at)`
  - `Booklet(id, module_id → Module, filename: str, pdf: bytes (LargeBinary), page_count: int, created_at)`
  - `Chapter(id, booklet_id → Booklet, index: int, title: str, first_page: int, last_page: int, status: ChapterStatus, error: str | None, waiting_reason: str | None, batch_id: str | None, draft: dict | None (JSONB, validated generated content between the two passes), summary: str | None, concepts: list[dict] (JSONB), introduced_at: datetime | None)`, unique `(booklet_id, index)`
  - `Item(id, chapter_id → Chapter, kind: ItemKind, payload: dict (JSONB), source_page: int, status: ItemStatus, flag_reason: FlagReason | None, created_at)`
  - `ReviewState(item_id PK → Item, card: dict (JSONB), due: datetime, last_review: datetime | None)`, index on `due`
  - `ReviewLog(id, item_id → Item, rating: int, correct: bool | None, score: int | None, answered_at)`
  - `Run(id, local_date: date, entries: list[dict] (JSONB), created_at, finished_at: datetime | None)`
  - `ApiCall(id, at, feature: Feature, model: str, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens: int, batch: bool, cost_usd: Numeric(10,6))`, index on `at`
- Enums (Python `StrEnum`, stored as strings): `ChapterStatus = pending | generating | verifying | ready | failed`; `ItemKind = mc | true_false | cloze | free`; `ItemStatus = active | flagged | deleted`; `FlagReason = wrong | not_in_course | unclear`; `Feature = generate | verify | grade | tutor`.
- Booklet status is derived from its chapters, not stored: `failed` if any chapter failed, `ready` if all ready, else `processing`.

- [ ] **Step 1: Write `test_chapter_cascade` (deleting a booklet deletes its chapters, items, review states), `test_item_payload_roundtrip` (JSONB payload with umlauts survives), and the migration test `test_upgrade_matches_metadata`.**
- [ ] **Step 2: Run.** Expected: FAIL, models missing.
- [ ] **Step 3: Implement the models and generate the migration with `alembic revision --autogenerate -m "baseline schema"`, then review it by hand.**
- [ ] **Step 4: Run `uv run pytest tests/models tests/test_migrations.py -v`.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(backend): add the data model`.

### Task 3: Cost ledger and budget

**Files:**
- Create: `backend/src/studyrun/ai/{__init__,pricing,ledger,budget,clock}.py`, `backend/tests/ai/test_pricing.py`, `test_ledger.py`, `test_budget.py`

**Interfaces:**
- Produces:
  - `Usage` dataclass `(input_tokens, output_tokens, cache_read_tokens, cache_write_tokens: int)`
  - `cost_usd(model: str, usage: Usage, *, batch: bool = False) -> Decimal`. Raises `UnknownModel` for a model missing from the price table.
  - `local_day_bounds(now: datetime, tz: str) -> tuple[datetime, datetime]` and `local_month_bounds(...)`, returning aware UTC datetimes
  - `async record_call(session, feature: Feature, model: str, usage: Usage, now: datetime, *, batch: bool = False) -> Decimal`
  - `async spent(session, features: set[Feature], start: datetime, end: datetime) -> Decimal`
  - `async ensure_budget(session, feature: Feature, settings: Settings, now: datetime) -> None`. Raises `BudgetExceeded(feature, spent, cap)`. `grade` and `tutor` share `daily_ai_cap_usd`; `generate` and `verify` share `generation_daily_budget_usd`.

- [ ] **Step 1: Write tests.**
  - `test_cost_opus`: 1,000,000 input + 100,000 output + 0 cache on `claude-opus-5-5` gives `Decimal("6.000000")`.
  - `test_cost_cache`: 500,000 cache read + 100,000 cache write on opus gives `0.10 + 0.50 = Decimal("0.600000")`.
  - `test_cost_batch_half`: the `test_cost_opus` usage with `batch=True` gives `Decimal("3.000000")`.
  - `test_unknown_model_raises`.
  - `test_berlin_day_late_evening`: `now = 2026-11-23T23:30+01:00` returns bounds `2026-11-22T23:00Z .. 2026-11-23T23:00Z`.
  - `test_berlin_day_after_midnight`: `now = 2026-11-24T00:30+01:00` falls into the next day.
  - `test_berlin_day_dst`: the day of 2027-03-28 is 23 hours long.
  - `test_budget_blocks_at_cap`: ledger has grade calls worth 0.50 today, so `ensure_budget(grade)` raises.
  - `test_budget_ignores_yesterday`: 0.50 at 23:59 the previous Berlin day, so it does not raise.
  - `test_generation_budget_separate`: 0.50 of grade calls do not block `generate`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Use `zoneinfo.ZoneInfo` and money as `Decimal`, quantized to 6 places.
- [ ] **Step 4: Run `uv run pytest tests/ai -v`.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(backend): record API costs and enforce daily budgets`.

### Task 4: Booklet splitting

**Files:**
- Create: `backend/src/studyrun/content/{__init__,pdf}.py`, `backend/tests/content/test_pdf.py`, `backend/tests/content/pdfs.py` (helper that builds test PDFs in memory with pypdf: N pages with text drawn via a minimal content stream, an optional outline, optional encryption)

**Interfaces:**
- Produces:
  - `ChapterSlice` dataclass `(title: str, first_page: int, last_page: int, pdf: bytes)`. Pages are 1-based PDF page numbers, inclusive.
  - `split_booklet(data: bytes, *, max_pages: int, window: int) -> list[ChapterSlice]`
  - `extract_slice(data: bytes, first_page: int, last_page: int) -> bytes`, used again by the worker
  - `BookletError(message_de: str)`, with a German message for the user
- Rules: chapters come from the top-level outline entries. Pages before the first entry join the first chapter. Without an outline, the whole booklet is cut into `window`-page slices titled `Seiten a–b`. A chapter over `max_pages` is cut into `window`-page parts titled `<title> (Teil n)`. Errors: not parseable, encrypted, or under 200 characters of extractable text in the first 5 pages ("keine Textebene").

- [ ] **Step 1: Write tests.** `test_outline_chapters` (outline at pages 1, 4, 9 of 12 gives ranges 1-3, 4-8, 9-12 with outline titles), `test_preamble_joins_first_chapter`, `test_no_outline_windows` (31 pages, window 15 gives 1-15, 16-30, 31-31), `test_long_chapter_split`, `test_slice_page_count`, `test_rejects_non_pdf`, `test_rejects_encrypted`, `test_rejects_no_text_layer`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement with `pypdf.PdfReader` / `PdfWriter` (`reader.outline`, `reader.get_destination_page_number`).**
- [ ] **Step 4: Run `uv run pytest tests/content/test_pdf.py -v`.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(backend): split booklets into chapters`.

### Task 5: Generation, validation and verification pipeline

**Files:**
- Create: `backend/src/studyrun/ai/llm.py` (protocols + Anthropic implementation), `backend/src/studyrun/content/{schemas,prompts,validate,pipeline,worker}.py`, `backend/tests/fakes.py` (`FakeLLM`, `FakeBatchLLM`), `backend/tests/content/test_validate.py`, `test_pipeline.py`, `test_worker.py`
- Modify: `backend/src/studyrun/main.py` (start and stop the worker in the lifespan, skipped when `STUDYRUN_WORKER_ENABLED=false`, which the test fixture sets)

**Interfaces:**
- Consumes: `ensure_budget`, `record_call`, `Usage` (Task 3); `extract_slice` (Task 4); models (Task 2).
- Produces:
  - `class LLM(Protocol): async def structured(self, *, session, feature: Feature, system: str, content: list[dict], schema: type[T], now: datetime) -> T`. The real `AnthropicLLM(settings)` calls `ensure_budget` first, sends the request (structured output, cached system prompt, effort per feature), calls `record_call` with the response usage, and raises `LLMUnavailable(reason)` on API errors or refusals.
  - `class BatchLLM(Protocol)` with `async submit(self, *, session, feature: Feature, custom_id: str, system: str, content: list[dict], schema: type[BaseModel], now: datetime) -> str` (calls `ensure_budget`, creates a one-request batch, returns the batch id) and `async collect(self, *, session, batch_id: str, feature: Feature, schema: type[T], now: datetime) -> T | None` (returns `None` while the batch is still processing; on success records the cost with `batch=True`; raises `LLMUnavailable` for an errored, expired or canceled result or a refusal). `AnthropicLLM` implements both protocols.
  - `FakeLLM(responses: list[BaseModel | Exception])` returns the queued responses in order and records `calls`. `FakeBatchLLM` hands out batch ids on submit and returns queued results on collect, with `None` entries to simulate a batch still processing.
  - Schemas (pydantic, discriminated by `kind`): `McItem(prompt, options: list[str] (3-5), answer_index: int, explanation, source_page)`, `TrueFalseItem(statement, correct: bool, explanation, source_page)`, `ClozeItem(text: str with exactly one "___", answers: list[str] (≥1), explanation, source_page)`, `FreeItem(prompt, model_answer, rubric: list[str] (1-5), source_excerpt: str (≤ 600 chars, verbatim from the booklet), source_page)`, `Concept(term, explanation)`, `ChapterContent(summary: str, concepts: list[Concept], items: list[ItemUnion])`, `Verdict(index: int, correct: bool, in_source: bool, note: str)`, `Verification(verdicts: list[Verdict])`.
  - `validate_items(items, first_page, last_page) -> list[ItemUnion]`
  - `async advance_chapter(session, llm: BatchLLM, chapter_id: int, now: datetime) -> None`, one step of the chapter's state machine
  - `async run_worker(factory, llm: BatchLLM, stop: asyncio.Event, poll_seconds: float = 60) -> None`
- Prompts (`prompts.py`, German output instructions): the generation prompt asks for about 2 items per page (minimum 8, maximum 40), roughly 50% mc, 15% true_false, 15% cloze, 20% free. Everything must come from the attached pages, with a source page per item and a verbatim excerpt for free items. The verification prompt gets the same chapter PDF plus the numbered items as JSON and returns one verdict per item.
- State machine (`advance_chapter`), with all state in the database so a restart loses nothing:
  - `pending`: extract the slice, submit the generation batch (`custom_id = f"gen-{chapter_id}"`), store `batch_id`, go to `generating`. `BudgetExceeded`: stay `pending` with `waiting_reason = "Tagesbudget für die Erzeugung erreicht"`.
  - `generating`: collect. `None`: stay. Result: validate; nothing valid left means `failed` with `"Keine gültigen Fragen erzeugt"`. Otherwise store the summary, concepts and valid items in `draft`, submit the verification batch (`custom_id = f"ver-{chapter_id}"`, same chapter PDF plus the numbered items), go to `verifying`.
  - `verifying`: collect. `None`: stay. Result: keep items whose verdict has `correct and in_source`; a missing verdict counts as rejected. Store them as `Item` rows (status `active`, no `ReviewState`, which marks them unseen), move summary and concepts onto the chapter, clear `draft` and `batch_id`, go to `ready`. No items left: `failed` with `"Keine Fragen haben die Prüfung bestanden"`.
  - `LLMUnavailable` or any other exception in any state: `failed` with the message, `batch_id` cleared.
- Worker, every `poll_seconds`: first advance every chapter in `generating` or `verifying`, then submit `pending` chapters while fewer than `generation_max_in_flight` are open. It submits in order of module position, booklet id, chapter index, and skips chapters whose `waiting_reason` was set earlier on the same Berlin day.

- [ ] **Step 1: Write the validation tests.** `test_drops_page_out_of_range`, `test_drops_bad_answer_index`, `test_drops_duplicate_options` (case-insensitive, trimmed), `test_drops_cloze_without_single_gap`, `test_drops_empty_strings`, `test_keeps_valid_items`.
- [ ] **Step 2: Write the pipeline tests with `FakeBatchLLM`.** `test_ready_with_verified_items` (5 generated, 1 invalid, verifier rejects 1, so 3 stored and the chapter is ready with its summary), `test_stays_while_batch_processing`, `test_missing_verdict_rejects`, `test_all_invalid_fails`, `test_all_rejected_fails`, `test_budget_exceeded_waits`, `test_batch_error_fails_with_message`, `test_worker_respects_max_in_flight` (5 pending chapters, at most 3 open batches), `test_worker_order`, `test_worker_skips_waiting_until_next_day`, `test_restart_resumes_from_batch_id` (a fresh worker collects a chapter already in `verifying`).
- [ ] **Step 3: Run.** Expected: FAIL.
- [ ] **Step 4: Implement** `llm.py` following the claude-api skill (PDF as a base64 `document` block before the text block; `cache_control` on the system prompt; batches per `batches.md`), then schemas, prompts, validate, pipeline and worker.
- [ ] **Step 5: Run `uv run pytest tests/content -v`.** Expected: PASS.
- [ ] **Step 6: Commit** `feat(backend): generate and verify items from booklet chapters`.

### Task 6: Modules and booklets API

**Files:**
- Create: `backend/src/studyrun/routes/{modules,booklets}.py`, `backend/tests/routes/test_modules.py`, `test_booklets.py`

**Interfaces:**
- Consumes: `split_booklet`, `BookletError` (Task 4); settings.
- Produces:
  - `GET /api/modules` returns `[{id, name, position, booklets: [{id, filename, page_count, status, chapters: {pending, generating, verifying, ready, failed}}]}]`, ordered by position.
  - `POST /api/modules {name}` returns 201 with the module, appended at the end.
  - `PATCH /api/modules/{id} {name?, position?}`. Changing the position renumbers the others to stay contiguous.
  - `POST /api/modules/{id}/booklets` (multipart `file`, form `confirm: bool = false`). Returns 201 with the booklet and its chapters, or 409 `{"needs_confirmation": true, "estimate_usd": float}` when `page_count * generation_estimate_usd_per_page > generation_confirm_usd` and `confirm` is false. 413 over `upload_max_bytes`. 422 `{"detail": <BookletError.message_de>}` for bad files.
  - `GET /api/modules/{id}/chapters` returns chapters with status, error, waiting_reason, title, page range and active item count.
  - `GET /api/booklets/{id}/pdf` returns the PDF (`application/pdf`, inline).
  - `POST /api/chapters/{id}/retry` sets a failed chapter to `pending` and clears its error. 409 if it isn't failed.

- [ ] **Step 1: Write tests.** `test_create_and_reorder_modules`, `test_upload_creates_pending_chapters`, `test_upload_needs_confirmation` (250 pages gives 409 with `estimate_usd == 6.25`, then `confirm=true` gives 201; 200 pages, estimating exactly 5.00, needs no confirmation), `test_upload_rejects_too_large`, `test_upload_rejects_non_pdf_with_german_message`, `test_pdf_download`, `test_retry_failed_chapter`, `test_retry_ready_chapter_conflicts`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Read the upload in chunks and stop at the limit. `retry` also clears `batch_id` and `draft`.
- [ ] **Step 4: Run `uv run pytest tests/routes -v`.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(backend): manage modules and upload booklets`.

### Task 7: Scheduling and run assembly

**Files:**
- Create: `backend/src/studyrun/study/{__init__,scheduling,assemble}.py`, `backend/tests/study/test_scheduling.py`, `test_assemble.py`

**Interfaces:**
- Consumes: models.
- Produces:
  - `rating_for_objective(correct: bool) -> fsrs.Rating` (Good / Again)
  - `rating_for_score(score: int) -> fsrs.Rating` (<50 Again, <75 Hard, <90 Good, ≥90 Easy)
  - `async record_review(session, item_id: int, rating: fsrs.Rating, now: datetime, *, correct: bool | None, score: int | None) -> None`. Creates or updates `ReviewState` via `fsrs.Scheduler().review_card` and writes a `ReviewLog`. Check the installed `fsrs` version's API (Card serialization) and pin it.
  - `RunEntry = {"type": "intro", "chapter_id": int} | {"type": "item", "item_id": int}`
  - `async build_run(session, settings, now: datetime) -> list[RunEntry]`
- Selection, using only `active` items of `ready` chapters:
  1. Reviews: due items (`ReviewState.due <= now`), earliest due first, at most `run_review_cap`.
  2. New items: unseen items (no `ReviewState`) of introduced chapters in the focus module, by chapter index then id, at most `run_new_items`. The focus module is the first by position that has unseen items or a ready chapter not yet introduced.
  3. If fewer than `run_new_items` new items were found and the focus module has a ready chapter not yet introduced (lowest index), add its intro entry and fill up with its first unseen items.
  4. If no free item is in the run, add the earliest-due free item, otherwise the first unseen free item from an introduced (or just-introduced) chapter.
  5. Order: interleave so that no two consecutive item entries share a kind, and none share a chapter where an alternative exists. The intro entry sits directly before the first item of its chapter.

- [ ] **Step 1: Write the scheduling tests.** `test_rating_for_score_bounds` (49, 50, 74, 75, 89, 90), `test_record_review_creates_state_and_log`, `test_again_due_sooner_than_easy`.
- [ ] **Step 2: Write the assembly tests.** `test_empty_library_gives_empty_run`, `test_reviews_capped_after_long_break` (200 due gives exactly 8 reviews; across three simulated days with all answered Good, the backlog shrinks each day), `test_intro_before_new_chapter_items`, `test_items_of_unintroduced_chapter_only_after_intro`, `test_one_free_item_included`, `test_no_consecutive_same_kind` (4 mc + 4 true_false due gives an alternating order), `test_flagged_deleted_and_failed_excluded`, `test_focus_module_follows_position`.
- [ ] **Step 3: Run.** Expected: FAIL.
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run `uv run pytest tests/study -v`.** Expected: PASS.
- [ ] **Step 6: Commit** `feat(backend): schedule reviews and assemble the daily run`.

### Task 8: Answers, grading and the runs API

**Files:**
- Create: `backend/src/studyrun/study/{answers,grading}.py`, `backend/src/studyrun/routes/runs.py`, `backend/tests/study/test_answers.py`, `test_grading.py`, `backend/tests/routes/test_runs.py`

**Interfaces:**
- Consumes: `build_run`, `record_review`, rating helpers (Task 7); `LLM`, `LLMUnavailable`, `BudgetExceeded` (Tasks 3 and 5).
- Produces:
  - `check_objective(item: Item, answer: dict) -> ObjectiveResult(correct: bool, expected: str, explanation: str)`. Answer shapes: mc `{"choice": int}`, true_false `{"value": bool}`, cloze `{"text": str}`.
  - `normalize_cloze(text: str) -> str`: casefold, trim, collapse whitespace, `ß` to `ss`, strip trailing `.,;:`, and for numbers use a decimal comma equal to a decimal point.
  - `GradeResult(score: int (0-100), feedback: str, missing: list[str])` and `async grade_free(session, llm, item: Item, text: str, now) -> GradeResult`. The prompt holds the question, model answer, rubric and `source_excerpt`, but not the PDF, so a grade stays under one cent.
  - `public_view(item) -> dict` without answers, model answers or verdicts.
  - Routes:
    - `POST /api/runs` returns the unfinished run of today's Berlin date if one exists, otherwise builds and stores a new one. Returns `{id, entries: [{n, type, done, chapter?|item?}]}`. An intro entry carries the chapter title, summary and concepts plus a booklet PDF link with `#page=`. An item entry carries `public_view` and the source link.
    - `POST /api/runs/{id}/entries/{n}/ack` (intro) sets `introduced_at`.
    - `POST /api/runs/{id}/entries/{n}/answer {answer}` returns for objective items `{correct, expected, explanation}`, for free items `{score, feedback, missing, model_answer}`, or, when grading is unavailable, `{grading_unavailable: true, reason, model_answer}`.
    - `POST /api/runs/{id}/entries/{n}/self-rate {rating: "again" | "good"}` is accepted only after `grading_unavailable`.
    - `POST /api/runs/{id}/finish` returns `{answered, correct, chapters_introduced: [title], due_tomorrow: int}`. A run can finish with entries undone, and answered entries keep their reviews.
  - `POST /api/items/{id}/flag {reason}` (here, since it is called from the run): status `flagged`, which removes the item from future runs.

- [ ] **Step 1: Write the answer tests.** `test_mc_correct_and_wrong`, `test_true_false`, `test_cloze_normalization` (`"Ohmsches Gesetz "` matches `"ohmsches gesetz"`, `"Maß"` matches `"Mass"`, `"0,5"` matches `"0.5"`, `"5"` does not match `"0.5"`).
- [ ] **Step 2: Write the grading tests with `FakeLLM`.** `test_grade_maps_score_to_rating`, `test_grade_prompt_has_excerpt_not_pdf`.
- [ ] **Step 3: Write the route tests.** `test_run_resumes_same_berlin_day` (a run created at 23:30 Berlin is resumed at 23:50, and a new one is built at 00:10), `test_ack_introduces_chapter`, `test_objective_answer_records_review`, `test_free_answer_graded`, `test_free_answer_budget_reached_offers_self_rating` (FakeLLM raises `BudgetExceeded`; then self-rate `good` records a Good review), `test_free_answer_api_error_offers_self_rating`, `test_self_rate_rejected_without_grading_failure`, `test_answer_twice_conflicts`, `test_public_view_hides_answers`, `test_finish_partial_run`, `test_flag_removes_from_next_run`.
- [ ] **Step 4: Run.** Expected: FAIL.
- [ ] **Step 5: Implement.**
- [ ] **Step 6: Run the full backend suite, ruff and mypy.** Expected: PASS.
- [ ] **Step 7: Commit** `feat(backend): answer, grade and run the daily session`.

### Task 9: Flags review and costs API

**Files:**
- Create: `backend/src/studyrun/routes/{items,costs}.py`, `backend/tests/routes/test_items.py`, `test_costs.py`

**Interfaces:**
- Produces:
  - `GET /api/flags` returns flagged items with full payload, reason, chapter title and source link.
  - `PUT /api/items/{id} {payload}` validates against the item's schema, sets it `active` again and clears the flag. Returns 422 on invalid payload.
  - `DELETE /api/items/{id}` sets status `deleted`.
  - `GET /api/costs` returns `{today: {total, by_feature}, month: {total, by_feature}, cap_today, remaining_today, generation_budget_today, generation_remaining_today}` in USD floats, using Berlin days.
- The frontend workflow exports `openapi.json` from `studyrun.main:app` before generating types, as tidalwave's `frontend.yml` does; no committed copy is needed.

- [ ] **Step 1: Write tests.** `test_flag_list`, `test_fix_reactivates`, `test_fix_rejects_invalid_payload`, `test_delete`, `test_costs_today_and_month_berlin`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(backend): review flagged items and report costs`.

### Task 10: Frontend scaffold, home and run player

**Files:**
- Create: `frontend/` scaffold copied from tidalwave and stripped to the basics (`package.json`, `svelte.config.js`, `vite.config.ts`, `tsconfig.json`, `nginx.conf`, `Dockerfile`, `src/app.html`, `static/manifest.webmanifest` + 192/512 icons), `src/lib/api/{schema.d.ts,client.ts}`, `src/routes/+layout.svelte`, `src/routes/+page.svelte` (home), `src/routes/run/+page.svelte`, `src/lib/components/{IntroCard,McQuestion,TrueFalseQuestion,ClozeQuestion,FreeQuestion,Feedback,RunSummary,SessionExpired}.svelte`, matching `*.test.ts`

**Interfaces:**
- Consumes: the API from Tasks 6-9 via types generated by `pnpm gen:api` from an `openapi.json` exported with `uv run python -c "from studyrun.main import create_app; import json; json.dump(create_app().openapi(), open('openapi.json','w'))"` in `backend/` (gitignored).
- Produces: `api.get/post/put/del<T>(path, body?)` in `client.ts`. It throws `SessionExpiredError` when a response under `/api` is a redirect or not JSON (authentik's login page), and the layout then shows `SessionExpired` with a "Neu anmelden" button that reloads the top-level page.
- No service worker. The manifest makes it installable, and leaving out offline caching avoids caching authentik's login page.
- Home: one big "Run starten" / "Run fortsetzen" button, today's spend against the cap in small print, an empty state that links to modules when there is nothing to study.
- Run player: one entry at a time with a progress bar. Intro cards show summary and concepts with a "Weiter" button (ack). Questions show `Feedback` after answering, with explanation, the source link (opens the booklet PDF at the page) and a "Melden" menu (wrong / not in the course / unclear). Free answers show score, feedback and missing points; on `grading_unavailable` they show the model answer and two buttons, "Wusste ich" and "Wusste ich nicht". A "Beenden" button is always visible and leads to `RunSummary`.
- Layout works one-handed on a phone (min. 360 px wide) and centred on a desk screen.

- [ ] **Step 1: Write component tests (Vitest + Testing Library).** `McQuestion` posts the chosen index and shows feedback; `ClozeQuestion` submits on Enter; `FreeQuestion` shows the self-rating buttons on `grading_unavailable`; `IntroCard` acks; run page moves to the next entry and shows the summary after `finish`; `client` throws `SessionExpiredError` for an HTML response.
- [ ] **Step 2: Run `pnpm test`.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `pnpm test && pnpm check && pnpm build`.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(frontend): add the home screen and the run player`.

### Task 11: Frontend modules, flags and costs pages

**Files:**
- Create: `src/routes/modules/+page.svelte`, `src/routes/modules/[id]/+page.svelte`, `src/routes/flags/+page.svelte`, `src/routes/costs/+page.svelte`, `src/lib/components/{UploadBooklet,ChapterList,FlagEditor}.svelte`, matching tests; navigation in `+layout.svelte`.

**Interfaces:**
- Consumes: Tasks 6 and 9 endpoints.
- Modules: list with up/down reordering, create. Module detail: booklets with status, chapters with status, error or waiting reason, and a retry button for failed ones. Polls every 30 s while anything is pending, generating or verifying, and says that a booklet usually takes up to an hour. Upload: on 409 it asks "Die Erzeugung kostet etwa X $. Fortfahren?" and resends with `confirm=true`; 413 and 422 messages are shown as returned.
- Flags: list with reason; edit form per item kind (fields of the payload), delete.
- Costs: today and this month by feature, cap and remaining, as plain numbers.

- [ ] **Step 1: Write tests.** Upload confirmation round trip; German error shown on 422; chapter list polls while generating or verifying and stops when everything is ready; flag edit sends the payload; costs page renders the numbers.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run `pnpm test && pnpm check && pnpm build`.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(frontend): manage modules, flags and costs`.

### Task 12: Packaging and CI

**Files:**
- Create: `backend/Dockerfile` (as tidalwave's, `studyrun.main:app`), `helm/studyrun/` (Chart, values, backend and frontend Deployments and Services, migration Job, Secret reference via `secrets.existingSecret`, optional Ingress off by default since production routing lives in fluxcd), `.github/workflows/{backend,frontend,helm}.yml` (copied from tidalwave, renamed, images built on release), `README.md` (what it is, local development, configuration table).
- Backend Deployment: `replicas: 1` and `strategy: Recreate`, because the in-process worker must not run twice.

- [ ] **Step 1: `helm lint helm/studyrun && helm template helm/studyrun | kubectl apply --dry-run=client -f -`.** Expected: no errors.
- [ ] **Step 2: Build both images locally (`docker build backend`, `docker build frontend`).** Expected: success. Run the backend image against the compose Postgres with `alembic upgrade head` and check `/api/health`.
- [ ] **Step 3: Commit** `chore(ci): package images, chart and workflows`.
- [ ] **Step 4: Ask Paul before creating the GitHub repository `paul-wtf/studyrun` (public) and pushing.** Then push, check that the backend and frontend workflows pass, and cut release `v0.1.0` so images and chart get published.

### Task 13: Deployment on paulwtf

**Files (in `~/git/fluxcd`, own branch and PR, mirroring `apps/tidalwave` and `apps/mcp-memory`):**
- Create: `apps/studyrun/{kustomization,namespace,repository,release,values,secrets,cert,ingress}.yaml`, `apps/studyrun/database/` (CNPG cluster, secret, backup plan and object store, podmonitor, as tidalwave)
- Modify: `apps/kustomization.yaml`; `infrastructure/authentik/blueprints/forward-auth.yaml`

**Interfaces:**
- `secrets.yaml`: ExternalSecret `studyrun-credentials` with `STUDYRUN_DATABASE_URL` from `studyrun/postgresql` and `STUDYRUN_ANTHROPIC_API_KEY` from Vault key `studyrun/anthropic` property `api-key`.
- `ingress.yaml`: a `authentik-forwardauth` Middleware in namespace `studyrun` (copy of mcp-memory's) and an IngressRoute for `studyrun.paul.wtf`. `PathPrefix(/api)` goes to the backend service on 8080, everything else to the frontend on 80, both through the middleware. The `external-dns` annotations match mcp-memory.
- Blueprint: proxy provider `Provider for studyrun.paul.wtf`, `mode: forward_single`, `external_host: https://studyrun.paul.wtf`, `authorization_flow` `default-provider-authorization-implicit-consent`, `access_token_validity: days=30`; application `studyrun` bound to group Administrator; add the provider to the embedded outpost's list.

- [ ] **Step 1: `kustomize build apps/studyrun` and `kubectl apply --dry-run=server -k apps/studyrun`.** Expected: no errors.
- [ ] **Step 2: Commit on a branch and open a PR in `paulwtf-infra/fluxcd`. Do not merge without Paul's explicit instruction.**
- [ ] **Step 3: Paul writes the Anthropic API key to Vault at `studyrun/anthropic` (`api-key`) and sets a spend limit in the Claude Console. After he merges, wait until the HelmRelease is Ready and the migration Job has completed (`flux get helmreleases -n studyrun`, `kubectl -n studyrun get jobs`).**
- [ ] **Step 4: Verify on the real system, with Paul.**
  - Desk browser: `https://studyrun.paul.wtf` asks for authentik login once, then the home screen loads.
  - Phone: install to the home screen, open from the icon, and the run starts without a passkey prompt. A day later the app still opens without logging in again.
  - Upload one of Paul's booklets. Chapters move to ready (usually within an hour), and the cost page's generation spend is within about 2× of `page_count * 0.025`.
  - Do one run with a free answer. The grade appears, and its recorded cost is under $0.01.
  - Record the measured numbers in the PR description and in a project memory (`project:studyrun`).

---

## Follow-up plans

Each gets its own plan once this one is live.

- **Plan 2: calculations, cases and the tutor.** Calculation items with parameterized formulas, safe evaluation, units and tolerance, faded worked steps; case items; "explain it" items; the four tutor modes with streamed replies; the tutor mini-lesson in chapter intros; the `tutor` feature under the daily cap.
- **Plan 3: exams and motivation.** Exams as entities (format, duration, pass mark, aids, date), course end date, the M6 seminar constraint and one exam per month, the planner and its timeline and conflicts, exam-driven focus replacing module position, the boss fight, the weekly goal and per-module progress bars.
