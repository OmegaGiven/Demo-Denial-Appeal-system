"""Shared FastAPI dependencies -- currently just the DB session."""

from __future__ import annotations

from typing import Generator

from sqlalchemy.orm import Session

from db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Per-request SQLAlchemy session, closed after the request completes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
