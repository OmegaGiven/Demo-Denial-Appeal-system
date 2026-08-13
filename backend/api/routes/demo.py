"""Phase 8 demo-only tooling: resets one already-processed denial per company
back to status="new" so the /profiles live-demo page always has something to
run the real pipeline against on screen.

This is deliberately NOT a general data-management endpoint. It:
  - only ever touches one denial at a time, picked deterministically (not by
    id -- callers can't target an arbitrary record);
  - only resets denials that are already fully processed (status != "new"),
    so it can never "lose" a denial that's still mid-review;
  - hard-deletes that one denial's extraction/classification/appeal/
    correction rows rather than just flipping status, so pipeline.run's
    single-denial path (which always INSERTs a new row per stage, never
    upserts -- see pipeline/extract.py, classify.py, draft_appeal.py) has a
    clean slate to reprocess into, and the /profiles UI shows a genuine
    before/after rather than stale rows from the last run peeking through.

Routed and tagged separately from api/routes/denials.py (the real
denial-review endpoints) on purpose, and the frontend gates this behind a
labeled "Demo Tools" section -- see README's Phase 8 section.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import DemoResetOut
from db.models import Appeal, AuditEvent, Classification, Denial, Extraction
from profiles import PROFILES

router = APIRouter(prefix="/api/demo", tags=["demo (interview case-study tooling, not production)"])


@router.post("/reset-sample", response_model=DemoResetOut)
def reset_sample_denial(source_company: str, db: Session = Depends(get_db)) -> DemoResetOut:
    """Picks one already-processed denial for `source_company` (lowest
    claim_ref, so repeated clicks cycle deterministically through different
    records instead of colliding), wipes its prior pipeline output, and
    resets it to status="new"."""
    if source_company not in PROFILES:
        raise HTTPException(
            status_code=404,
            detail=f"no profile registered for source_company={source_company!r}. Known: {sorted(PROFILES)}",
        )

    denial = (
        db.query(Denial)
        .filter(Denial.source_company == source_company, Denial.status != "new")
        .order_by(Denial.claim_ref)
        .first()
    )
    if denial is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"no already-processed denial found for source_company={source_company!r} "
                "to reset for the demo (either none exist, or every denial for this "
                "company is already status='new')."
            ),
        )

    db.query(AuditEvent).filter(AuditEvent.denial_id == denial.id).delete()
    db.query(Appeal).filter(Appeal.denial_id == denial.id).delete()
    db.query(Classification).filter(Classification.denial_id == denial.id).delete()
    db.query(Extraction).filter(Extraction.denial_id == denial.id).delete()
    denial.status = "new"
    db.commit()
    db.refresh(denial)

    return DemoResetOut(
        denial_id=denial.id,
        source_company=denial.source_company,
        claim_ref=denial.claim_ref,
        status=denial.status,
    )
