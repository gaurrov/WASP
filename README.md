<div align="center">

<img src="docs/images/mark.svg" width="72" height="72" alt="WASP seal">

# WASP

**AICTE approval scrutiny, with the evidence attached.**

Workflow Automation System Project, built for Smart India Hackathon 2026, problem statement **SIH26262**<br>
*Integrated AICTE Approval Workflow Automation, Compliance Monitoring and Alert Management System*

[![CI](https://github.com/gaurrov/WASP/actions/workflows/ci.yml/badge.svg)](https://github.com/gaurrov/WASP/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/Python-3.12-18263d)
![React 19](https://img.shields.io/badge/React-19-18263d)
![PostgreSQL + pgvector](https://img.shields.io/badge/PostgreSQL-pgvector-18263d)
![LangGraph](https://img.shields.io/badge/workflow-LangGraph-4338a0)
![Runs offline](https://img.shields.io/badge/runs-offline-2f6b4f)

[Quick start](#quick-start) &nbsp;|&nbsp; [Demo playbook](docs/DEMO.md) &nbsp;|&nbsp; [Measured results](docs/METRICS.md) &nbsp;|&nbsp; [Build plan](docs/PLAN.md) &nbsp;|&nbsp; [Module reference](#module-reference)

</div>

<br>

![An approved case in WASP: findings with evidence, and the reviewer's reasons](docs/images/case.png)

## What it does

Institutions applying to AICTE upload dozens of documents: faculty lists, degree certificates,
fire safety certificates, land and building records. Reviewers then check them by hand against
the Approval Process Handbook. WASP does the reading and the cross-checking, and leaves the
decision with people.

- **Reads every document, including scans.** Each extracted value keeps the page and position it
  came from, and how sure the reading is. Anything uncertain is flagged, never trusted.
- **Checks it against versioned rules.** Deterministic checks find missing documents, faculty
  without certificates, mismatched names, faculty shortfalls and expiring certificates. Rules that
  encode an AICTE norm cite the handbook clause, and stay *provisional* until someone verifies it.
- **Runs the case to a decision.** A reviewer confirms or overrides each finding, asks for a
  clarification, or decides. When the institution resubmits, only the checks its changes can
  affect run again.
- **Keeps watching after approval.** Expiring certificates, overdue responses and slow reviews
  become alerts that escalate over time and close only when the documents show the obligation is
  met.
- **Records everything.** Every upload, check, review, decision and alert is in the audit trail.

The principle throughout: **AI extracts and interprets, deterministic rules decide, people approve.**

## Results

Measured on the synthetic demo set with outbound internet blocked (details and caveats in
[docs/METRICS.md](docs/METRICS.md)):

| Measure | Result |
|---|---|
| Document type identified correctly | **100%** of 43 documents, including 3 scans |
| Fields read correctly | **99.4%**; the rest were flagged for a person, **0% silently wrong** |
| Planted problems caught | **6 of 6**: missing document, uncertified faculty, misspelled name, poor scan, faculty shortfall, expiring NOC |
| Re-checking after a fix | **3 of 7** rules re-run; the other findings carried over unchanged |
| Full demo story, end to end | about **8 seconds**, passing 5 of 5 rehearsals |

## How it works

```mermaid
flowchart LR
    A[Institution uploads<br>PDFs and scans] --> B[Document intelligence<br>PyMuPDF and Tesseract OCR]
    B --> C[(Extracted facts<br>value, page, box, confidence)]
    H[Approval Process Handbook] --> I[Clause index<br>keyword + semantic]
    C --> D[Rules engine<br>rules.yaml]
    I --> D
    D --> E[Findings<br>with evidence and citations]
    E --> F{Reviewer}
    F -- approve or reject --> G[Decision<br>and audit trail]
    F -- ask for clarification --> J[Institution fixes<br>and resubmits]
    J -- only affected rules re-run --> D
    G --> K[Monitoring<br>expiry, deadlines, SLAs]
    K --> L[Alerts that close<br>when the data says so]
```

1. **Upload.** Files go to S3-compatible storage. The type is verified from the file itself,
   duplicates are rejected, and a replacement creates a new version.
2. **Extraction.** Native PDF text is used where present and pages without text are OCR'd. A
   classifier checks each file is what the institution says it is.
3. **Evaluation.** On submission the case workflow waits for extraction, then runs the rules.
   Each finding records the facts it relied on and the handbook passages it cites.
4. **Review.** The workflow pauses for a reviewer. A clarification request pauses it again until
   the institution resubmits.
5. **Monitoring.** Scheduled and event-driven scans turn obligations into deduplicated alerts.
6. **Audit.** Every transition is an append-only event.

## Screenshots

<table>
  <tr>
    <td width="50%"><img src="docs/images/evidence.png" alt="Evidence viewer"><br><b>Evidence viewer.</b> Every value is boxed where it was read; uncertain readings are amber.</td>
    <td width="50%"><img src="docs/images/overview.png" alt="Reviewer overview"><br><b>Overview.</b> Cases by stage, the reviewer's work list, and open alerts.</td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/images/case.png" alt="Case file"><br><b>Case file.</b> Findings, documents and audit trail, with the decision panel alongside.</td>
    <td width="50%"><img src="docs/images/sign-in.png" alt="Sign in"><br><b>Sign in.</b> Institution, reviewer and administrator roles.</td>
  </tr>
</table>

## Quick start

Requires Docker Desktop (Compose v2).

```bash
git clone https://github.com/gaurrov/WASP.git && cd WASP
docker compose up --build
```

| Service | URL |
|---|---|
| Web app | http://localhost:5173 |
| API and interactive docs | http://localhost:8000/docs |
| S3 storage (SeaweedFS) | http://localhost:8333 |
| PostgreSQL with pgvector | localhost:15432 (`wasp` / `wasp`; set `WASP_DB_PORT` in `.env` to change) |

If a container fails with *port is already allocated* or *ports are not available*, another program
on your machine holds that port: stop it, or for Postgres pick a free port with `WASP_DB_PORT`.

On first start the backend runs migrations, creates the storage bucket, syncs the rules and seeds
three demo accounts. The password for all of them is `wasp1234`.

| Role | Email | Can |
|---|---|---|
| Institution | institution@wasp.dev | Create applications, upload documents, submit, respond to clarifications |
| Reviewer | reviewer@wasp.dev | Review queue, findings, clarifications, decisions, handbook search |
| Administrator | admin@wasp.dev | Everything a reviewer can, plus load handbooks and verify rules |

To try the full story with prepared documents:

```bash
docker compose exec backend python -m app.demo prefetch           # demo PDFs and the embedding model
docker compose exec backend python -m app.demo load --stage draft # an application, ready to submit
```

Then follow the 7-minute run sheet in [docs/DEMO.md](docs/DEMO.md).

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI, SQLAlchemy 2, Alembic, Pydantic | Typed endpoints and reviewed migrations |
| Workflow | LangGraph with a PostgreSQL checkpointer | Cases wait days for people and resume in any worker |
| Background work | Celery with Redis, Celery beat | OCR, indexing, workflow events and scheduled monitoring off the request path |
| Document intelligence | PyMuPDF, Tesseract OCR, Pillow | Native text where possible, OCR with per-word confidence where not |
| Retrieval | PostgreSQL full-text + pgvector, fastembed (`bge-small-en-v1.5`, ONNX) | Hybrid clause search that runs on a laptop, offline |
| Storage | PostgreSQL 17, SeaweedFS (S3-compatible) | One database for records and vectors; documents in object storage |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query | Self-hosted font and icons, so the UI works offline too |
| Delivery | Docker Compose, GitHub Actions | One command to run; CI on every push |

## Project layout

```
WASP/
├── backend/
│   ├── app/            FastAPI app and domain modules (see Module reference)
│   ├── alembic/        database migrations
│   └── tests/          pytest suite (isolated test database and bucket)
├── frontend/src/       React app: pages, components, typed API client
├── docs/               build plan, demo playbook, measured metrics, screenshots
├── infra/              service configuration (SeaweedFS credentials)
├── docker-compose.yml          the full stack
└── docker-compose.offline.yml  override that blocks internet access, for the venue
```

---

## Module reference

### Backend (`backend/app/`)

| Module | Responsibility | Entry points |
|---|---|---|
| `main.py` | FastAPI app, CORS, router registration | `uvicorn app.main:app` |
| `config.py` | All settings, read from `WASP_*` environment variables | `get_settings()` |
| `db.py` | SQLAlchemy engine and session factory | `get_db()` dependency, `SessionLocal` |
| `auth.py` | Password hashing (bcrypt), JWT issue/verify, role guard | `CurrentUser`, `require_roles(...)` |
| `storage.py` | S3 client and bucket bootstrap | `get_s3()`, `ensure_bucket()` |
| `worker.py` | Celery app, queue routing, eager mode for tests | `celery -A app.worker worker` |
| `audit.py` | Append-only event log written in the caller's transaction | `record_event(...)` |
| `checklists.py` | Required documents per application type (**placeholder**, see limitations) | `APPLICATION_TYPES` |
| `seed.py` | Idempotent bootstrap: bucket, demo users, rules sync, checkpoint tables | `python -m app.seed` |
| `synthetic.py` | Deterministic synthetic document set with ground truth and planted issues (scans use seeded noise, so OCR results are reproducible) | `python -m app.synthetic` |

#### `api/` — HTTP layer

Thin routers: validate input, enforce visibility, call domain modules, return Pydantic models.
Visibility rules live in `applications.load_application()` and are reused everywhere: institution
users see only their own applications, reviewers never see drafts, admins see all; anything not
visible is a **404** (not 403) so existence isn't leaked.

| Router | Covers |
|---|---|
| `health.py` | liveness + database check |
| `auth.py` | login (OAuth2 password form), current user |
| `applications.py` | application types, create/list/detail, document upload/replace/delete, submit/resubmit |
| `documents.py` | extracted facts and page geometry, original file, rendered page PNGs, re-extraction |
| `findings.py` | findings with evidence, citations and latest review; re-evaluate |
| `regulatory.py` | handbook sources (upload, re-ingest), hybrid search, rules list, clause candidates, rule verification |
| `workflow.py` | case status and audit timeline, finding review, clarification request, approve/reject |

#### `models/` — persistence (SQLAlchemy 2, Alembic migrations in `backend/alembic/`)

| File | Tables |
|---|---|
| `identity.py` | `institutions` (tenants), `users` (role, optional institution) |
| `application.py` | `applications` (declared values, status, clarification, decision), `documents` (versions, extraction results, page geometry), `extracted_facts` (value, raw text, confidence, page, bbox) |
| `regulatory.py` | `regulatory_sources` (edition, effective dates, ingest status), `regulatory_chunks` (clause text, `vector(384)` embedding, generated `tsvector`), `compliance_rules` (versioned definitions + verification state) |
| `compliance.py` | `findings` (status, evidence fact ids, citation chunk ids, `is_current`), `review_decisions`, `alerts` (used from M5), `workflow_events` (audit log) |
| `enums.py` | All status enums, stored as VARCHAR so adding a value needs no migration |

#### `docintel/` — document intelligence

| File | Does |
|---|---|
| `text.py` | PDF/image → pages → **visual lines** of positioned words. Native text via PyMuPDF; pages with < 20 chars are OCR'd with Tesseract (per-word confidence). Words are grouped by vertical position so table rows and "Label: value" pairs stay on one line. Coordinates are PDF points. |
| `classify.py` | Weighted keyword classifier on page 1 → `(type, confidence)`. Stored next to the declared type; mismatches are flagged, never auto-corrected. |
| `fields.py` | Per-type labelled-field patterns (`FieldSpec`) plus a faculty-table parser. Each match keeps raw text, page, bbox and mean word confidence. A value that matches but won't parse (e.g. OCR's "25°07 /2021") is kept with confidence capped at 0.4 so it goes to review. |
| `dates.py` | Day-first date parsing for Indian certificate formats |
| `pipeline.py` | `process(bytes, mime, declared_type)` → text, classification, fields |
| `tasks.py` | Celery task: fetch from S3, run pipeline, replace facts (idempotent), notify the workflow |
| `evaluate.py` | Field-level accuracy against the synthetic set's ground truth (`python -m app.docintel.evaluate`) |

**To support a new document type:** add it to `models/enums.py:DocumentType`, keywords in
`classify.py`, `FieldSpec`s in `fields.py`, a generator + expected values in `synthetic.py`, and
(if required) a checklist entry in `checklists.py`.

#### `rag/` — regulatory retrieval

| File | Does |
|---|---|
| `chunk.py` | Splits a handbook into **clause-level** chunks using its own numbering (`2.3.1`, `Chapter III`, `Appendix 6`); long clauses split with overlap |
| `embed.py` | Local ONNX embeddings (fastembed, `BAAI/bge-small-en-v1.5`, 384-d). Optional: if the model can't load, search falls back to keyword-only |
| `search.py` | `hybrid_search()`: Postgres full-text + pgvector cosine, fused with reciprocal-rank fusion, filtered to sources **in force on the given date** |
| `tasks.py` | Celery ingestion task (idempotent) |
| `load.py` | CLI to ingest a PDF from disk |

#### `rules/` — compliance rules

| File | Does |
|---|---|
| `rules.yaml` | The rule set. **Internal** rules (data consistency) start approved; **regulatory** rules start as *draft* with a `norm_note` explaining where the numbers came from. |
| `evaluators.py` | One pure function per rule type: `(EvalContext, params) → Result`. Missing evidence returns `unable_to_determine`, never `pass`. |
| `context.py` | `EvalContext` (documents, facts, helpers) and `Result` (status, reason, evidence, `decisive` evidence) |
| `engine.py` | `sync_rules()` (yaml → DB, never un-verifies a rule), `evaluate()` (all rules or a subset), low-confidence guard, citation lookup |

Current rules: `DOC-REQ-001` required documents · `DOC-TYPE-001` declared vs detected type ·
`FAC-DECL-001` declared vs listed faculty · `FAC-QUAL-001` faculty ↔ certificate matching (fuzzy
names, degree consistency) · `FAC-RATIO-001` student-faculty ratio *(draft)* · `FAC-CADRE-001`
cadre ratio *(draft)* · `FIRE-NOC-001` fire NOC validity and expiry warning *(draft)*.

**Low-confidence guard:** a pass/fail that rests on a fact below `WASP_LOW_CONFIDENCE_THRESHOLD`
becomes `needs_review`. Evaluators can mark which evidence is *decisive*, so e.g. "3 faculty have
no certificate" stays a definite failure even if a fourth name was read badly.

**To add a rule:** write an evaluator in `evaluators.py` (decorate with `@evaluator`), add an entry
to `rules.yaml` with `required_evidence` (used for incremental re-validation), and a test.
To change a rule's logic or numbers, add a **new version** rather than editing the old one.

#### `workflow/` — case workflow (LangGraph)

| File | Does |
|---|---|
| `graph.py` | The state machine: `wait_for_extraction → evaluate → human_review → (finalize | request_clarification → await_institution → …)`. Nodes that pause only call `interrupt()`; side effects live in separate nodes so resuming never repeats them. |
| `runner.py` | `advance(application_id, event)` starts or resumes a case under a per-case Postgres advisory lock; `status()` reports where it waits. Checkpoints use `langgraph-checkpoint-postgres`. |
| `affected.py` | Incremental re-validation: which rules can a document change affect (by declared evidence type, or because a finding cites a fact from a changed document) |
| `reviews.py` | Latest review decision per finding |
| `tasks.py` | `send_event()` → Celery task that advances the case |

Events: `None` (start), `documents_changed`, `reevaluate`, `request_clarification`, `resubmitted`,
`decide`. Unexpected events leave the case waiting where it is.

#### `monitoring/` — compliance monitoring and alerts

| File | Does |
|---|---|
| `obligations.py` | Detectors that derive what should be alerted on *now* from current data: **certificate expiry** (any extracted `valid_until`; medium within 90 days, high within 30, critical once expired), **clarification response** (the institution's deadline after a clarification request), **review SLA** (reviewer pool, from 2 days before the SLA). |
| `scan.py` | Reconciles alerts with obligations. One alert per obligation (`dedup_key`), so repeated scans update instead of duplicating. Lifecycle: `active → overdue → escalated`; `acknowledged` by a user; `resolved` **only when the obligation disappears from the data** (e.g. a renewed certificate is processed) or a reviewer records an alternative outcome; `reopened` if the condition returns (a manually resolved alert reopens only if things get worse). Every transition is an audit event. |
| `tasks.py` | `scan_all` (scheduled by Celery **beat**) and `scan_application` (event-driven: after extraction and every workflow transition) |

Renewals: outside draft/clarification, an institution may still **replace a document that an open
expiry alert points at** (recorded as `compliance_document_updated`); processing it clears the alert.

#### `demo/` — demo tooling

| File | Does |
|---|---|
| `scenario.py` | The demo story as asserted stages (`draft → submitted → clarification → resubmitted → approved → renewed`), driven through the real HTTP API and worker |
| `client.py` | Minimal API client (per-role login) and polling helper |
| `ops.py` | `reset` (dev only; keeps users, rules, handbooks), `preflight` (API, migrations, Redis, S3, worker queues, beat heartbeat, OCR, embedding model **offline**, accounts, rules, handbook, demo files), `prefetch`, `metrics` |
| `__main__.py` | CLI: `python -m app.demo {prefetch,preflight,reset,load,rehearse,metrics}` |

`rehearse --times N` resets and runs the whole story N times, failing loudly at the first
unexpected result; `load --stage S` recovers a live demo at any point.

**To add a monitored obligation:** write a detector `(db, application, now) -> list[Obligation]`
in `obligations.py`, add it to `DETECTORS`, give it a stable `dedup_key`, and add a test.

### Frontend (`frontend/src/`)

React 19 + TypeScript + Vite + Tailwind 4, TanStack Query for server state, lucide icons.
The design is a case-file tool for regulators: cool paper and navy ink, with a single accent,
violet stamp ink, kept for decisions, focus and the evidence currently selected. The type is
Atkinson Hyperlegible Next, designed by the Braille Institute for legibility.

| File | Does |
|---|---|
| `main.tsx` | Routes and auth guard |
| `api.ts` | Fetch wrapper (bearer token, error parsing), login |
| `auth.tsx` | `AuthProvider` / `useAuth()` backed by `/auth/me` |
| `applications.ts` | Typed API client for every endpoint |
| `index.css` | Design tokens (Tailwind `@theme`): ink, paper, stamp violet, status tones; self-hosted font; focus and reduced-motion rules |
| `components/ui.tsx` | Shared primitives: buttons, panels, pills, notices, fields, page header, date and value formatting, case references |
| `pages/Login.tsx` | Sign-in, illustrated with a real finding; demo-account shortcuts in dev |
| `pages/Dashboard.tsx` | Overview: cases by stage, the reviewer's work list or the institution's applications and next steps, open alerts |
| `pages/ApplicationsList.tsx` | Institution's applications / reviewer's queue |
| `pages/NewApplication.tsx` | Create draft with declared values |
| `pages/ApplicationDetail.tsx` | The case file: header with reference, findings, documents (long groups collapse; files needing attention stay visible), audit trail, and a sticky panel for the next step |
| `pages/DocumentViewer.tsx` | **Evidence viewer**: page images with clickable bounding boxes per extracted value; `?fact=` preselects |
| `pages/RulesPage.tsx` | Rules, their norms and verification; find and verify clauses |
| `pages/HandbookPage.tsx` | Upload/index handbook editions; search them |
| `pages/AlertsPage.tsx` | Alert center (open / resolved / all); admin scan with optional simulated date |
| `components/AlertCard.tsx` | Alert with severity, status, due date; acknowledge / upload renewal / resolve with note |
| `components/Layout.tsx` | Left rail with role-aware navigation and alert count; horizontal on small screens |
| `components/FindingsPanel.tsx` | Findings with evidence, citations, provisional/expiring badges, per-finding review |
| `components/WorkflowPanel.tsx` | Clarification and decision notices, the reviewer's decision panel, audit timeline |

### Infrastructure

| Path | Does |
|---|---|
| `docker-compose.yml` | Postgres 17 + pgvector, Redis, SeaweedFS (S3), backend, worker, **beat** (scheduler), frontend. Backend, worker and beat share one image. |
| `backend/Dockerfile` | Python 3.12 + uv + Tesseract |
| `docker-compose.offline.yml` | Override that blocks all outbound internet for the Python services (unreachable proxy, Hugging Face offline) to prove the demo needs none |
| `infra/seaweedfs-s3.json` | S3 credentials for SeaweedFS |
| `.github/workflows/ci.yml` | Backend (ruff, migrations, `alembic check`, pytest with Tesseract, S3 and cached model) and frontend (typecheck + build) |
| `data/` (git-ignored) | Synthetic documents, downloaded handbooks |
| `docs/` | `PLAN.md` (build plan), `DEMO.md` (demo playbook), `METRICS.md` (measured numbers) |

---

## Data model

```mermaid
erDiagram
    INSTITUTION ||--o{ USER : has
    INSTITUTION ||--o{ APPLICATION : files
    APPLICATION ||--o{ DOCUMENT : contains
    DOCUMENT ||--o{ EXTRACTED_FACT : yields
    APPLICATION ||--o{ FINDING : receives
    COMPLIANCE_RULE ||--o{ FINDING : produces
    FINDING ||--o{ REVIEW_DECISION : "reviewed in"
    APPLICATION ||--o{ ALERT : raises
    APPLICATION ||--o{ WORKFLOW_EVENT : records
    REGULATORY_SOURCE ||--o{ REGULATORY_CHUNK : "split into"
    COMPLIANCE_RULE }o--o| REGULATORY_SOURCE : "verified against"
```

- Findings are versioned: re-evaluation marks old findings `is_current = false`; incremental
  re-validation only replaces the affected rules' findings.
- Documents are versioned: a replacement is a new row (`supersedes_id`), the old one stays as
  evidence for earlier findings.
- LangGraph's own tables (`checkpoints*`) hold workflow state and are excluded from Alembic.

---

## API reference

All under `/api`; interactive docs at http://localhost:8000/docs. **I** = institution,
**R** = reviewer, **A** = admin.

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/health` | — | Liveness + DB |
| POST | `/auth/login` | — | Get a JWT (form: `username`, `password`) |
| GET | `/auth/me` | any | Current user |
| GET | `/application-types` | any | Types and their document checklists |
| GET/POST | `/applications` | any / I | List visible applications / create a draft |
| GET | `/applications/{id}` | any | Detail, current documents, checklist status |
| POST | `/applications/{id}/documents` | I | Upload (`file`, `doc_type`, optional `replaces_id`) |
| DELETE | `/applications/{id}/documents/{doc}` | I | Delete (drafts only) |
| POST | `/applications/{id}/submit` | I | Submit, or resubmit after clarification |
| GET | `/documents/{id}` | any | Extracted facts, page geometry, type mismatch |
| GET | `/documents/{id}/content` | any | Original file |
| GET | `/documents/{id}/pages/{n}.png` | any | Rendered page |
| POST | `/documents/{id}/reprocess` | R, A | Re-run extraction |
| GET | `/applications/{id}/findings` | any | Findings + evidence + citations + review |
| POST | `/applications/{id}/evaluate` | R, A | Full re-evaluation |
| GET | `/applications/{id}/workflow` | any | Where the case waits, round, audit events |
| POST | `/findings/{id}/review` | R, A | Confirm or override (override needs a comment) |
| POST | `/applications/{id}/clarification` | R, A | Ask the institution to fix findings |
| POST | `/applications/{id}/decision` | R, A | Approve or reject (approval blocked while findings are unreviewed or confirmed) |
| GET/POST | `/regulatory/sources` | R, A / A | List / upload a handbook edition |
| POST | `/regulatory/sources/{id}/reingest` | A | Re-index |
| GET | `/regulatory/search?q=` | R, A | Hybrid clause search |
| GET | `/rules` | R, A | Rules and verification state |
| GET | `/rules/{id}/candidates` | R, A | Handbook passages likely to contain the rule's norm |
| POST | `/rules/{id}/verify` | A | Pin a rule to the clause you confirmed |
| GET | `/alerts?status=&application_id=` | any | Alerts (`open`/`resolved`/`all`); institutions see their own institution-facing alerts |
| GET | `/alerts/summary` | any | Open alert counts for the nav badge |
| POST | `/alerts/{id}/acknowledge` | any | Acknowledge |
| POST | `/alerts/{id}/resolve` | R, A | Resolve with a note (alternative outcome) |
| POST | `/monitoring/scan` | A | Run the scan now; `as_of` (simulated date) only when `WASP_ENV=dev` |

---

## Background jobs

| Task | Queue | Triggered by |
|---|---|---|
| `app.docintel.process_document` | `documents` | upload, reprocess |
| `app.rag.ingest_source` | `documents` | handbook upload, re-ingest |
| `app.workflow.advance_case` | `default` | submit, resubmit, extraction finished, reviewer actions |
| `app.monitoring.scan_application` | `monitoring` | extraction finished, any workflow transition |
| `app.monitoring.scan_all` | `monitoring` | Celery beat, every `WASP_MONITORING_INTERVAL_SECONDS` |

Tasks are idempotent and use late acknowledgement, so a crashed worker's task is redelivered
safely. If Redis is down, uploads still succeed and documents stay `pending` until reprocessed.

---

## Configuration

Settings come from `WASP_*` environment variables (or `backend/.env`); `docker-compose.yml`
provides dev defaults.

| Variable | Default | Meaning |
|---|---|---|
| `WASP_DATABASE_URL` | `postgresql+psycopg://wasp:wasp@localhost:15432/wasp` | Postgres |
| `WASP_DB_PORT` | `15432` | Host port Compose publishes Postgres on (read from the root `.env`) |
| `WASP_REDIS_URL` | `redis://localhost:6379/0` | Celery broker/result backend |
| `WASP_CELERY_EAGER` | `false` | Run tasks inline (tests) |
| `WASP_S3_ENDPOINT` / `_ACCESS_KEY` / `_SECRET_KEY` / `_BUCKET` | SeaweedFS dev values | Object storage |
| `WASP_JWT_SECRET` | dev-only value | **Set a random 32+ byte secret outside dev** |
| `WASP_JWT_TTL_MINUTES` | `480` | Token lifetime |
| `WASP_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed browser origins |
| `WASP_LOW_CONFIDENCE_THRESHOLD` | `0.80` | Below this, extracted values are flagged for review |
| `WASP_EMBEDDING_MODEL` / `_DIM` | `BAAI/bge-small-en-v1.5` / `384` | Must match each other and the migration |
| `WASP_MODEL_CACHE_DIR` | `/models` | Embedding model cache |
| `WASP_ENV` | `dev` | `dev` enables simulated-date monitoring scans |
| `WASP_MONITORING_INTERVAL_SECONDS` | `3600` (`300` in compose) | Scheduled scan interval |
| `WASP_EXPIRY_WARNING_DAYS` / `WASP_EXPIRY_URGENT_DAYS` | `90` / `30` | Certificate expiry → medium / high alert |
| `WASP_CLARIFICATION_RESPONSE_DAYS` | `15` | Institution's response deadline |
| `WASP_REVIEW_SLA_DAYS` | `7` | Reviewer's target time to act |
| `WASP_ESCALATE_AFTER_DAYS` | `7` | Overdue this long → escalated |
| `OMP_THREAD_LIMIT` | `1` (compose) | One Tesseract thread per worker process |

---

## Development

Run backend commands **inside the container** so everyone uses the same Linux toolchain (this
also avoids Windows Application Control blocking native Python wheels on the host):

```bash
docker compose exec backend pytest -q
docker compose exec backend ruff check . && docker compose exec backend ruff format .
docker compose exec backend alembic revision --autogenerate -m "describe change"   # review it!
docker compose exec backend alembic upgrade head
```

- New backend dependency: `cd backend && uv add <package>`, then `docker compose build backend`
  (rebuilds the image the worker shares).
- Frontend: `cd frontend && npm install && npm run dev`, or use the compose service.
  `npm run build` typechecks and builds.
- Code changes reload automatically in the backend and frontend; restart the worker after
  backend changes: `docker compose restart worker`.

### Loading the AICTE handbook (needed for citations)

Download the official **Approval Process Handbook 2024-25 to 2026-27** PDF from
[aicte-india.org](https://www.aicte-india.org/bureaus/approval/ap_documents), then either upload
it as admin on the **Handbook** page, or put it at `./data/regulatory/APH_2024-27.pdf` and run:

```bash
docker compose exec backend python -m app.rag.load /data/regulatory/APH_2024-27.pdf \
  --title "AICTE Approval Process Handbook" --version 2024-27 \
  --effective-from 2024-07-01 --effective-to 2027-06-30
```

Then, as admin, open **Rules**, use *Find clause* on each draft rule, read the passages, and
*Verify* the clause that states the norm. If the handbook's number differs from the rule's
params, add a new rule version in `rules.yaml` instead of verifying.

### Running offline

Nothing at runtime needs the internet once images are built and `python -m app.demo prefetch`
has run (it caches the embedding model). To prove it:

```bash
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d --force-recreate
docker compose exec backend python -m app.demo rehearse --times 3
```

The frontend reinstalls packages only when `package-lock.json` changes, and keeps them in a named
volume, so it restarts offline too.

### Synthetic documents and extraction accuracy

```bash
docker compose exec backend python -m app.synthetic          # ./data/synthetic/abc_institute
docker compose exec backend python -m app.docintel.evaluate  # field-level accuracy vs ground truth
```

Current result: classification 100%, fields 99.4% correct, 0.6% wrong-but-flagged for review,
0% silently wrong (see [docs/METRICS.md](docs/METRICS.md)). Synthetic documents are cleaner than
real ones; re-measure on real samples.

---

## Testing and CI

- Tests use a separate `wasp_test` database and `wasp-test` bucket (created automatically) and run
  Celery tasks inline, so upload → extraction → workflow → findings is exercised end to end.
- `test_docintel.py` is an **extraction quality gate**: no field may be silently wrong.
- `test_workflow.py` runs the full demo cycle, including asserting that resubmission re-checks
  exactly the affected rules.
- `test_monitoring.py` covers deduplication, time-driven overdue/escalation (simulated scans),
  automatic resolution by renewal, manual resolution, clarification deadlines and review SLAs.
- `tests/fixtures.py` contains a *test-only* regulation PDF; it is not AICTE text.
- `python -m app.demo rehearse` is the end-to-end check against the *running* stack (real
  worker, beat, storage); run it before any demo.
- CI runs on every push and PR (see `.github/workflows/ci.yml`).

Branch from `main` (`feat/...`, `fix/...`), open a PR, CI must pass. One milestone may be several
small PRs; keep `main` demo-able.

---

## Known limitations

- **Handbook not loaded.** Regulatory rules stay *draft* (findings marked provisional) until the
  APH 2024-27 is ingested and each rule is verified against its clause.
- **Placeholder checklist.** `checklists.py` lists illustrative documents; replace with the APH list.
- **OCR confidence isn't a guarantee.** While tuning the synthetic poor scan, some noise/blur
  levels made Tesseract misread a name *with* high confidence. Cross-document checks (faculty
  list ↔ certificate) are the backstop; don't rely on the confidence threshold alone.
- **Pattern-based extraction.** Works on the layouts it was written for; real documents vary. An
  LLM fallback for fields the patterns miss is planned once a provider is chosen.
- **Single decision role.** Any reviewer can approve/reject; production needs a separate,
  authorized approver role.
- **In-app alerts only.** Email/SMS delivery isn't wired yet; alerts are the notification record,
  so a delivery channel means sending on `alert_raised` / `alert_escalated` events.
- **Approved applications aren't re-evaluated** when a renewal is uploaded: monitoring clears the
  alert, but findings stay as they were at decision time.


---

<div align="center">
<sub>Built for Smart India Hackathon 2026, SIH26262. The demo uses synthetic documents only; no real institution's records are included.</sub>
</div>
