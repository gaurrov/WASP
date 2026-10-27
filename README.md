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

Run backend commands inside the container (this keeps everyone on the same Linux toolchain).
Tests use a separate `wasp_test` database and `wasp-test` bucket, created automatically:

```bash
docker compose exec backend pytest -q
docker compose exec backend ruff check . && docker compose exec backend ruff format .
docker compose exec backend alembic revision --autogenerate -m "describe change"
docker compose exec backend alembic upgrade head
```

After editing a model, always generate a migration and review it before committing.

### Loading the AICTE handbook (needed for citations)

Download the official **Approval Process Handbook 2024-25 to 2026-27** PDF from
[aicte-india.org](https://www.aicte-india.org/bureaus/approval/ap_documents), then either upload
it as admin on the **Handbook** page, or:

```bash
# put the PDF at ./data/regulatory/APH_2024-27.pdf, then
docker compose exec backend python -m app.rag.load /data/regulatory/APH_2024-27.pdf   --title "AICTE Approval Process Handbook" --version 2024-27   --effective-from 2024-07-01 --effective-to 2027-06-30
```

Then, as admin, open **Rules**, use *Find clause* on each draft rule, read the passages, and
*Verify* the clause that states the norm. If the handbook's number differs from the rule's
params, add a new rule version in `backend/app/rules/rules.yaml` instead of verifying.

### Synthetic documents and extraction accuracy

```bash
docker compose exec backend python -m app.synthetic          # writes ./data/synthetic/abc_institute
docker compose exec backend python -m app.docintel.evaluate  # field-level accuracy vs ground truth
```

The set mirrors the demo script: 20 faculty but 17 certificates, a misspelled name, a fire NOC
expiring in 30 days, and good/poor scans that exercise OCR. `tests/test_docintel.py` runs the same
evaluation as a regression gate: no field may be silently wrong (wrong values must be flagged).

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
    api/          FastAPI routers (auth, applications + documents)
    workflow/     LangGraph case workflow (Postgres-checkpointed): extraction wait, evaluation,
                  reviewer interrupt, clarification round-trip, incremental re-validation, decision
    rules/        rules.yaml + deterministic evaluators + engine (findings with evidence/citations)
    rag/          handbook chunking by clause, local embeddings, hybrid search (FTS + pgvector)
    docintel/     text (PyMuPDF / Tesseract OCR) → classify → field extraction, Celery task, evaluation
    synthetic.py  synthetic document generator with ground truth
    checklists.py required documents per application type (placeholder until APH rules in M3)
    audit.py      append-only workflow event log
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

Coming in later milestones: `app/monitoring/` (alerts).

## Workflow

- Branch from `main` (`feat/m1-upload`, `fix/...`), open a PR, CI must pass.
- One milestone = one or more small PRs; keep `main` demo-able.
