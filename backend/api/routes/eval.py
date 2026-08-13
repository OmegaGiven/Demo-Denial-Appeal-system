"""Eval-run history and on-demand eval triggering."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import EvalRunOut
from db.models import EvalRun

router = APIRouter(prefix="/api/eval", tags=["eval"])


@router.get("/runs", response_model=list[EvalRunOut])
def list_eval_runs(db: Session = Depends(get_db)) -> list[EvalRun]:
    return db.query(EvalRun).order_by(EvalRun.run_at.desc()).all()


@router.post("/run", response_model=EvalRunOut)
def trigger_eval_run(db: Session = Depends(get_db)) -> EvalRun:
    """Runs eval.score's deterministic scoring against the existing DB
    contents (no LLM calls) and writes a new eval_runs row, mirroring
    `python -m eval.run_eval`'s DB-write logic without its CLI printing/exit
    code."""
    # Local imports: keep eval/*.py's sys.path bootstrapping out of module
    # import time for routes that never call it.
    from eval.run_eval import get_git_commit
    from eval.score import run_scoring

    result = run_scoring()
    run = EvalRun(
        accuracy_score=result["overall_score"],
        details=result,
        git_commit=get_git_commit(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
