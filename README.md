# WASP — Workflow Automation System Project

**SIH26262 · Integrated AICTE Approval Workflow Automation, Compliance Monitoring and Alert Management System**

WASP automates AICTE approval scrutiny: it extracts facts from institution documents, checks them
against versioned, clause-cited rules, routes uncertain findings to human reviewers through a
LangGraph workflow, and keeps monitoring compliance (expiring certificates, deadlines, regulatory
changes) after approval.

Core principle: **AI extracts and interprets, deterministic rules decide, humans approve.** Every
finding links to its evidence (document, page, value) and the regulatory clause it was checked against.

See [docs/PLAN.md](docs/PLAN.md) for scope, milestones, team split and the demo script.

## Quick start

Requires Docker Desktop.

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Web app | http://localhost:5173 |
| API + Swagger docs | http://localhost:8000/docs |
| S3 storage (SeaweedFS) | http://localhost:8333 |
| Postgres (pgvector) | localhost:5432 (`wasp` / `wasp`) |

On startup the backend runs migrations and seeds demo accounts (password `wasp1234`):

| Role | Email |
|---|---|
| Institution | institution@wasp.dev |
| Reviewer | reviewer@wasp.dev |
| Admin | admin@wasp.dev |

## Development

Run backend commands inside the container (this keeps everyone on the same Linux toolchain):

```bash
docker compose exec backend pytest -q
docker compose exec backend ruff check . && docker compose exec backend ruff format .
docker compose exec backend alembic revision --autogenerate -m "describe change"
docker compose exec backend alembic upgrade head
```

After editing a model, always generate a migration and review it before committing.

Frontend:

```bash
cd frontend && npm install && npm run dev   # or use the compose service
npm run build                               # typecheck + production build
```

To add backend dependencies: `cd backend && uv add <package>`, then `docker compose build backend`.

## Layout

```
backend/
  app/
    api/          FastAPI routers
    models/       SQLAlchemy models (institutions → applications → documents → facts → findings → alerts)
    auth.py       JWT auth + require_roles()
    worker.py     Celery app (queues: default, documents, monitoring)
    storage.py    S3 client
    seed.py       demo data
  alembic/        migrations
  tests/
frontend/         React + TypeScript + Vite + Tailwind
infra/            service config (SeaweedFS S3 credentials)
docs/PLAN.md      build plan
```

Coming in later milestones: `app/docintel/` (OCR + extraction), `app/rag/` (regulatory hybrid
retrieval), `app/rules/` (versioned rule evaluators), `app/workflow/` (LangGraph),
`app/monitoring/` (alerts), `data/synthetic/` (demo document generator).

## Workflow

- Branch from `main` (`feat/m1-upload`, `fix/...`), open a PR, CI must pass.
- One milestone = one or more small PRs; keep `main` demo-able.
