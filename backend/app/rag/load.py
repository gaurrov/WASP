"""Load a regulatory PDF from disk (e.g. the APH you downloaded) and ingest it synchronously.

Usage:
  python -m app.rag.load /data/regulatory/APH_2024-27.pdf \
      --title "AICTE Approval Process Handbook" --version 2024-27 \
      --effective-from 2024-07-01 --effective-to 2027-06-30 \
      --url "https://www.aicte-india.org/..."
"""

import argparse
import hashlib
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import RegulatorySource
from app.rag.tasks import ingest_source
from app.storage import ensure_bucket, get_s3


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a regulatory PDF")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--type", default="handbook")
    parser.add_argument("--effective-from", type=date.fromisoformat)
    parser.add_argument("--effective-to", type=date.fromisoformat)
    parser.add_argument("--url")
    args = parser.parse_args()

    data = args.pdf.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise SystemExit(f"{args.pdf} is not a PDF")
    ensure_bucket()
    with SessionLocal() as db:
        source = db.scalar(
            select(RegulatorySource).where(
                RegulatorySource.title == args.title, RegulatorySource.version == args.version
            )
        )
        if source is None:
            source = RegulatorySource(id=uuid.uuid4(), title=args.title, version=args.version)
            db.add(source)
        source.source_type = args.type
        source.effective_from, source.effective_to = args.effective_from, args.effective_to
        source.source_url = args.url
        source.sha256 = hashlib.sha256(data).hexdigest()
        source.storage_key = f"regulatory/{source.id}/{args.pdf.name}"
        get_s3().put_object(Bucket=get_settings().s3_bucket, Key=source.storage_key, Body=data)
        db.commit()
        source_id = str(source.id)

    ingest_source(source_id)  # run inline so the command reports the outcome
    with SessionLocal() as db:
        source = db.get(RegulatorySource, uuid.UUID(source_id))
        print(
            f"{source.title} {source.version}: {source.ingest_status.value}, "
            f"{source.chunk_count} chunks {source.ingest_error or ''}"
        )


if __name__ == "__main__":
    main()
