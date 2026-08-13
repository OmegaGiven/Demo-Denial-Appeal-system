"""Small aggregate endpoints for the Phase 7 monitoring dashboard that don't
belong under /denials, /eval, or /usage.

Kept intentionally minimal -- this is not a general analytics layer, just the
one aggregate the dashboard needs and the existing endpoints (`/api/eval/runs`,
`/api/usage`) don't already provide.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import ConfidenceBucket, ConfidenceDistributionResponse
from db.models import Classification, Denial

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Bucket edges chosen from the real observed confidence spread (0.45-0.98
# across the 62-denial live population as of Phase 7): a wide low band
# (below the pipeline's 0.7 needs_review routing threshold), a band just
# above it, and two bands splitting the dense high-confidence cluster so the
# histogram doesn't collapse into "everything is in one bucket."
CONFIDENCE_BUCKETS = [
    (0.0, 0.5, "0.00-0.50"),
    (0.5, 0.7, "0.50-0.70"),
    (0.7, 0.85, "0.70-0.85"),
    (0.85, 1.01, "0.85-1.00"),  # upper edge nudged past 1.0 so confidence=1.0 lands in the last bucket
]


@router.get("/confidence-distribution", response_model=ConfidenceDistributionResponse)
def get_confidence_distribution(
    source_company: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ConfidenceDistributionResponse:
    """Buckets classification confidence across the live denial population
    (not the 24-record labeled eval set -- every denial that has reached
    classification). A denial reprocessed more than once contributes only
    its most recent classification, via a per-denial max(created_at)
    subquery, so the distribution reflects current pipeline behavior rather
    than double-counting historical reprocessing runs."""
    latest_per_denial = (
        db.query(
            Classification.denial_id.label("denial_id"),
            func.max(Classification.created_at).label("max_created_at"),
        )
        .group_by(Classification.denial_id)
        .subquery()
    )

    query = (
        db.query(Classification.confidence, Classification.denial_id)
        .join(
            latest_per_denial,
            (Classification.denial_id == latest_per_denial.c.denial_id)
            & (Classification.created_at == latest_per_denial.c.max_created_at),
        )
    )
    if source_company:
        query = query.join(Denial, Denial.id == Classification.denial_id).filter(
            Denial.source_company == source_company
        )

    confidences = [row[0] for row in query.all()]

    buckets = []
    for lo, hi, label in CONFIDENCE_BUCKETS:
        count = sum(1 for c in confidences if lo <= c < hi)
        buckets.append(ConfidenceBucket(label=label, min_confidence=lo, max_confidence=min(hi, 1.0), count=count))

    return ConfidenceDistributionResponse(
        source_company=source_company,
        total_classified=len(confidences),
        buckets=buckets,
    )
