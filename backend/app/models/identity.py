import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin, str_enum
from app.models.enums import UserRole


class Institution(IdMixin, TimestampMixin, Base):
    """A tenant. Every institution-owned row carries institution_id for isolation."""

    __tablename__ = "institutions"

    name: Mapped[str] = mapped_column(String(255))
    aicte_id: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str | None] = mapped_column(String(64))
    city: Mapped[str | None] = mapped_column(String(64))
    contact_email: Mapped[str | None] = mapped_column(String(255))

    users: Mapped[list["User"]] = relationship(back_populates="institution")


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole))
    # Set only for institution users; reviewers and admins are AICTE-side.
    institution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institutions.id"))
    is_active: Mapped[bool] = mapped_column(default=True)

    institution: Mapped[Institution | None] = relationship(back_populates="users")
