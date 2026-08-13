"""Liveness/readiness check -- confirms the process is up AND can reach Postgres."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:  # pragma: no cover - only hit if Postgres is down
        db_status = f"error: {exc}"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
    )
