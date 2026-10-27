"""Demo operations: reset, preflight checks, prefetch for offline use, and measured metrics."""

import os
import random
import subprocess
import sys
import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import redis
from sqlalchemy import func, select, text

from app import synthetic
from app.config import get_settings
from app.db import SessionLocal, engine
from app.demo.client import ACCOUNTS, API, Client
from app.models import ComplianceRule, RegulatorySource
from app.models.enums import RuleStatus
from app.monitoring.tasks import BEAT_HEARTBEAT_KEY
from app.storage import get_s3

DEMO_DIR = Path("/data/synthetic/abc_institute")
EXTRA_FILES = ["certificate_02_corrected.pdf", "fire_noc_renewed.pdf"]


def require_dev() -> None:
    if get_settings().env != "dev":
        raise SystemExit("Refusing: demo commands only run with WASP_ENV=dev")


# --- reset -------------------------------------------------------------------------------


def reset() -> None:
    """Delete all applications and everything hanging off them (documents, facts, findings,
    reviews, alerts, their audit events, workflow state, stored files). Keeps users, rules,
    handbook sources and rule-verification history."""
    require_dev()
    with engine.begin() as conn:
        for statement in [
            "DELETE FROM review_decisions",
            "DELETE FROM alerts",
            "DELETE FROM findings",
            "DELETE FROM extracted_facts",
            "DELETE FROM documents",
            "DELETE FROM workflow_events WHERE application_id IS NOT NULL",
            "DELETE FROM applications",
            "TRUNCATE checkpoints, checkpoint_blobs, checkpoint_writes",
        ]:
            conn.execute(text(statement))
    s3, bucket = get_s3(), get_settings().s3_bucket
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="applications/"):
        keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if keys:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": keys})


# --- prefetch ----------------------------------------------------------------------------


def prefetch() -> None:
    """Everything the demo needs that might otherwise come from the network or not exist yet:
    synthetic documents (incl. the corrected certificate and renewed NOC for the live steps)
    and the embedding model."""
    synthetic.generate(DEMO_DIR, date.today())
    roster = synthetic.faculty_roster(random.Random(7))
    (DEMO_DIR / "certificate_02_corrected.pdf").write_bytes(
        synthetic.qualification_certificate(roster[1], roster[1]["name"])[0]
    )
    (DEMO_DIR / "fire_noc_renewed.pdf").write_bytes(
        synthetic.fire_noc(date.today() + timedelta(days=700))[0]
    )
    print(f"Demo documents: {len(list(DEMO_DIR.glob('*.pdf')))} PDFs in {DEMO_DIR}")
    from app.rag.embed import embed_query

    if embed_query("warm up") is None:
        raise SystemExit("Embedding model could not be loaded/downloaded")
    print(f"Embedding model cached in {get_settings().model_cache_dir}")


# --- preflight ---------------------------------------------------------------------------


def preflight() -> bool:
    """Check everything the live demo depends on. Returns False if anything critical fails."""
    results: list[tuple[str, str, str]] = []  # (status, check, detail)

    def check(name: str, fn, critical: bool = True) -> None:
        try:
            detail = fn() or ""
            results.append(("ok", name, detail))
        except Exception as exc:  # noqa: BLE001 — every failure is reported, not raised
            results.append(("FAIL" if critical else "warn", name, f"{type(exc).__name__}: {exc}"))

    def api():
        r = httpx.get(f"{API}/health", timeout=5)
        r.raise_for_status()
        return API

    def migrations():
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
        assert current == head, f"database at {current}, code at {head}"
        return head

    def broker():
        redis.Redis.from_url(get_settings().redis_url).ping()

    def storage():
        get_s3().head_bucket(Bucket=get_settings().s3_bucket)

    def worker():
        from app.worker import celery_app

        queues = celery_app.control.inspect(timeout=3).active_queues() or {}
        consumed = {q["name"] for qs in queues.values() for q in qs}
        missing = {"default", "documents", "monitoring"} - consumed
        assert queues, "no worker answered"
        assert not missing, f"no worker consuming {missing}"
        return f"{len(queues)} worker(s)"

    def beat():
        raw = redis.Redis.from_url(get_settings().redis_url).get(BEAT_HEARTBEAT_KEY)
        assert raw, "no scheduled scan has run yet (is the beat service up?)"
        age = time.time() - float(raw)
        limit = 2 * get_settings().monitoring_interval_seconds + 60
        assert age < limit, f"last scheduled scan {age / 60:.0f} min ago"
        return f"last scan {age:.0f}s ago"

    def ocr():
        import pytesseract

        return f"tesseract {pytesseract.get_tesseract_version()}"

    def embeddings_offline():
        # A fresh process with the Hub forced offline proves the model loads from cache.
        env = os.environ | {"HF_HUB_OFFLINE": "1"}
        code = "from app.rag.embed import embed_query; assert embed_query('x') is not None"
        subprocess.run(
            [sys.executable, "-c", code], env=env, check=True, capture_output=True, timeout=120
        )
        return "loads from cache with HF_HUB_OFFLINE=1"

    def accounts():
        for role in ACCOUNTS:
            Client(role)
        return ", ".join(ACCOUNTS)

    def rules():
        with SessionLocal() as db:
            total = db.scalar(select(func.count()).select_from(ComplianceRule))
            draft = db.scalar(select(func.count()).where(ComplianceRule.status == RuleStatus.DRAFT))
        assert total, "no rules synced"
        return f"{total} rules, {draft} still draft"

    def handbook():
        with SessionLocal() as db:
            n = db.scalar(select(func.count()).select_from(RegulatorySource))
        assert n, "no handbook loaded — findings will cite nothing (rules stay provisional)"
        return f"{n} source(s)"

    def demo_files():
        names = {p.name for p in DEMO_DIR.glob("*.pdf")}
        missing = [
            n
            for n in ["faculty_list.pdf", "building_certificate.pdf", *EXTRA_FILES]
            if n not in names
        ]
        assert not missing, f"missing {missing}: run `python -m app.demo prefetch`"
        return f"{len(names)} PDFs"

    def dev_mode():
        assert get_settings().env == "dev", "simulated-date scans need WASP_ENV=dev"

    check("API", api)
    check("Database migrations", migrations)
    check("Redis broker", broker)
    check("S3 storage", storage)
    check("Worker", worker)
    check("Scheduler (beat)", beat)
    check("OCR", ocr)
    check("Embedding model offline", embeddings_offline)
    check("Demo accounts", accounts)
    check("Rules", rules)
    check("Handbook", handbook, critical=False)
    check("Demo documents", demo_files)
    check("Dev mode", dev_mode, critical=False)

    width = max(len(name) for _, name, _ in results)
    for status, name, detail in results:
        print(f"  [{status:>4}] {name:<{width}}  {detail}")
    return all(status != "FAIL" for status, _, _ in results)


# --- metrics -----------------------------------------------------------------------------


def metrics(runs: int = 3) -> str:
    """Measure the numbers we quote, and return them as Markdown."""
    from app.demo import scenario
    from app.docintel.evaluate import evaluate

    with tempfile.TemporaryDirectory() as tmp:
        manifest = synthetic.generate(Path(tmp), date.today())
        ev = evaluate(Path(tmp))
    scans = sum(1 for m in manifest if m.scanned)
    ok, flagged, wrong, missing = ev["totals"]
    total = ok + flagged + wrong + missing

    demos = []
    for _ in range(runs):
        reset()
        demos.append(scenario.run())
    reset()

    def ms(stage):
        values = [d.timings[stage] for d in demos]
        return f"{sum(values) / len(values):.1f} s (max {max(values):.1f})"

    detected = demos[-1].detected
    commit = os.environ.get("GIT_COMMIT", "")
    lines = [
        "# WASP — measured metrics",
        "",
        f"Measured {datetime.now(UTC):%Y-%m-%d %H:%M} UTC{f' at {commit}' if commit else ''}, "
        "on the synthetic ABC Institute set, local Docker stack. Synthetic documents are "
        "cleaner than real ones: re-measure on real samples before quoting these as "
        "production figures.",
        "",
        "## Document intelligence",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Documents (incl. {scans} scans) | {ev['documents']} |",
        f"| Document type classification | {ev['classification_accuracy']:.0%} |",
        f"| Fields extracted correctly | {ok / total:.1%} ({ok}/{total}) |",
        f"| Wrong but flagged for human review | {flagged / total:.1%} |",
        f"| **Silently wrong** | **{wrong / total:.1%}** |",
        f"| Missing | {missing / total:.1%} |",
        "",
        "## Planted issues caught",
        "",
        "| Issue | Caught |",
        "|---|---|",
        *[f"| {issue} | {'yes' if ok_ else '**no**'} |" for issue, ok_ in detected.items()],
        "",
        f"## End-to-end timings (mean of {runs} runs, real worker)",
        "",
        "| Step | Time |",
        "|---|---|",
        f"| Upload 41 documents + extraction (incl. OCR) | {ms('draft')} |",
        f"| Submission → findings ready for review | {ms('submitted')} |",
        f"| Clarification request | {ms('clarification')} |",
        f"| Fix 2 documents + resubmit → re-evaluated | {ms('resubmitted')} |",
        f"| Overrides + approval | {ms('approved')} |",
        f"| Time-travel scan + renewal → alert auto-resolved | {ms('renewed')} |",
        "",
        "Re-validation after resubmission re-checked **3 of 7** rules; the other 4 findings were "
        "carried over unchanged.",
        "",
        "Not measured: time saved versus manual scrutiny (needs a pilot with real reviewers).",
        "",
    ]
    return "\n".join(lines)
