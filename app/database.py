"""Database engine, model, and session helpers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class IntelSubmission(Base):
    __tablename__ = "intel_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    source_url: Mapped[str] = mapped_column(Text)
    submitter_province: Mapped[str] = mapped_column(String(160), index=True)
    intel_type: Mapped[str] = mapped_column(String(80), index=True)
    target_province: Mapped[str] = mapped_column(String(160), index=True)
    target_kingdom: Mapped[str] = mapped_column(String(32), index=True)
    raw_html: Mapped[str] = mapped_column(Text)
    plain_text: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    parser_status: Mapped[str] = mapped_column(String(32), index=True)


def make_engine(database_url: str):
    kwargs = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **kwargs)


def initialize_database(engine) -> None:
    Base.metadata.create_all(engine)


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(session_factory) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

