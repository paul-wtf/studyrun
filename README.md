# studyrun

A single-user study app. You upload a course booklet as a PDF, studyrun splits it into
chapters, has Claude generate and verify practice items per chapter, and schedules them as
daily runs with spaced repetition (FSRS). Free-text answers are graded by Claude. The UI and
all generated content are German.

- `backend/`: FastAPI, SQLAlchemy, Alembic, PostgreSQL. A worker inside the API process
  drives generation and verification through the Message Batches API.
- `frontend/`: SvelteKit (static adapter), served by nginx.
- `helm/studyrun/`: Helm chart for both images plus a migration hook.

There is no authentication in the app. Put it behind a forward-auth proxy.

Booklets and generated content never go into git. Tests build their own invented PDFs.

## Local development

Tools (Python 3.12, uv, Node 24, pnpm, helm) come from the nix dev shell:

    nix --extra-experimental-features 'nix-command flakes' develop

Start Postgres (any Postgres 16 with user, password and database `studyrun` works):

    docker compose -f backend/docker-compose.yml up -d postgres

Backend:

    cd backend
    uv sync
    uv run alembic upgrade head
    STUDYRUN_ANTHROPIC_API_KEY=... uv run uvicorn studyrun.main:app --port 8080 --reload
    uv run pytest -v

Tests use the database `studyrun_test`; point `STUDYRUN_TEST_DATABASE_URL` elsewhere if
needed. Lint and types: `uv run ruff check src tests` and `uv run mypy src`.

Frontend:

    cd frontend
    pnpm install
    pnpm dev
    pnpm check && pnpm test

After an API change, regenerate the client types:

    cd backend && uv run python -c "from studyrun.main import app; import json; json.dump(app.openapi(), open('openapi.json','w'))"
    cd ../frontend && pnpm gen:api

## Configuration

All settings are environment variables with the prefix `STUDYRUN_`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `STUDYRUN_DATABASE_URL` | `postgresql+asyncpg://studyrun:studyrun@localhost:5432/studyrun` | Database connection |
| `STUDYRUN_ANTHROPIC_API_KEY` | empty | Claude API key |
| `STUDYRUN_LOG_LEVEL` | `INFO` | Log level |
| `STUDYRUN_TIMEZONE` | `Europe/Berlin` | Defines "today" and "this month" for runs and budgets |
| `STUDYRUN_WORKER_ENABLED` | `true` | Run the generation worker in the API process |
| `STUDYRUN_MODEL_GENERATE` | `claude-opus-5-5` | Model for item generation |
| `STUDYRUN_MODEL_VERIFY` | `claude-sonnet-5-5` | Model for item verification |
| `STUDYRUN_MODEL_GRADE` | `claude-opus-5-5` | Model for grading answers |
| `STUDYRUN_DAILY_AI_CAP_USD` | `0.50` | Daily spend cap for grading |
| `STUDYRUN_GENERATION_DAILY_BUDGET_USD` | `10.00` | Daily spend cap for generation and verification |
| `STUDYRUN_GENERATION_CONFIRM_USD` | `5.00` | Estimated cost above which generation needs confirmation |
| `STUDYRUN_GENERATION_ESTIMATE_USD_PER_PAGE` | `0.025` | Cost estimate per booklet page |
| `STUDYRUN_GENERATION_MAX_IN_FLIGHT` | `3` | Chapters with an open batch at once |
| `STUDYRUN_RUN_REVIEW_CAP` | `8` | Reviews per run |
| `STUDYRUN_RUN_NEW_ITEMS` | `4` | New items per run |
| `STUDYRUN_MAX_CHAPTER_PAGES` | `40` | Chapters longer than this are split into windows |
| `STUDYRUN_CHAPTER_WINDOW_PAGES` | `15` | Window size for split chapters |
| `STUDYRUN_UPLOAD_MAX_BYTES` | `52428800` | Largest accepted upload (50 MiB) |

## Deployment

Releases publish `ghcr.io/paul-wtf/studyrun-backend` and `ghcr.io/paul-wtf/studyrun-frontend`
and the chart at `https://paul-wtf.github.io/studyrun`. The chart does not create credentials: `secrets.existingSecret` is required and must name a
Secret with `STUDYRUN_DATABASE_URL` and `STUDYRUN_ANTHROPIC_API_KEY` (the migration hook
runs before release resources exist, so the Secret has to be there already).
The backend runs as a single replica with the `Recreate` strategy because the worker must
not run twice. The Ingress is off by default: route `/api` to the backend service (port
8080) and everything else to the frontend service (port 80).
