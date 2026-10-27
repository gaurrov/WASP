"""Create the storage bucket, demo users and institution, and sync rules.yaml. Idempotent.

Usage: python -m app.seed
"""

from sqlalchemy import select

from app.auth import hash_password
from app.db import SessionLocal
from app.models import Institution, User
from app.models.enums import UserRole
from app.rules.engine import sync_rules
from app.storage import ensure_bucket
from app.workflow.runner import setup_checkpointer

DEMO_PASSWORD = "wasp1234"


def seed() -> None:
    ensure_bucket()
    with SessionLocal() as db:
        institution = db.scalar(select(Institution).where(Institution.aicte_id == "1-DEMO-0001"))
        if institution is None:
            institution = Institution(
                name="ABC Institute of Technology",
                aicte_id="1-DEMO-0001",
                state="Tamil Nadu",
                city="Chennai",
                contact_email="principal@abc-institute.example",
            )
            db.add(institution)
            db.flush()

        users = [
            ("institution@wasp.dev", "ABC Institute Admin", UserRole.INSTITUTION, institution.id),
            ("reviewer@wasp.dev", "AICTE Reviewer", UserRole.REVIEWER, None),
            ("admin@wasp.dev", "WASP Admin", UserRole.ADMIN, None),
        ]
        for email, name, role, institution_id in users:
            if db.scalar(select(User).where(User.email == email)) is None:
                db.add(
                    User(
                        email=email,
                        full_name=name,
                        password_hash=hash_password(DEMO_PASSWORD),
                        role=role,
                        institution_id=institution_id,
                    )
                )
        db.commit()
        sync_rules(db)
    setup_checkpointer()
    print(f"Seeded demo users (password: {DEMO_PASSWORD})")


if __name__ == "__main__":
    seed()
