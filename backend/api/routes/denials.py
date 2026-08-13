"""Denial listing/detail, on-demand pipeline processing, appeal review, and
the unified audit-event (corrections + appeal-review decisions) trail."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import (
    AppealOut,
    AppealStatusUpdateRequest,
    AuditEventOut,
    CorrectionCreateRequest,
    DenialCreateRequest,
    DenialDetail,
    DenialListItem,
    DenialListResponse,
    ProcessResponse,
)
from db.models import Appeal, AuditEvent, Classification, Denial, Extraction
from profiles import PROFILES

router = APIRouter(prefix="/api/denials", tags=["denials"])

APPEAL_STATUSES = ("approved", "rejected", "sent")


def _get_denial_or_404(db: Session, denial_id: uuid.UUID) -> Denial:
    denial = db.get(Denial, denial_id)
    if denial is None:
        raise HTTPException(status_code=404, detail=f"no denial with id={denial_id}")
    return denial


@router.get("", response_model=DenialListResponse)
def list_denials(
    source_company: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> DenialListResponse:
    query = db.query(Denial)
    if source_company:
        query = query.filter(Denial.source_company == source_company)
    if status:
        query = query.filter(Denial.status == status)

    total = query.count()

    has_classification = exists().where(Classification.denial_id == Denial.id)
    has_appeal = exists().where(Appeal.denial_id == Denial.id)

    rows = (
        query.with_entities(Denial, has_classification.label("has_classification"), has_appeal.label("has_appeal"))
        .order_by(Denial.received_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        DenialListItem(
            id=denial.id,
            source_company=denial.source_company,
            status=denial.status,
            payer=denial.payer,
            claim_ref=denial.claim_ref,
            received_at=denial.received_at,
            has_classification=bool(has_classification_flag),
            has_appeal=bool(has_appeal_flag),
        )
        for denial, has_classification_flag, has_appeal_flag in rows
    ]

    return DenialListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=DenialListItem, status_code=201)
def create_denial(body: DenialCreateRequest, db: Session = Depends(get_db)) -> DenialListItem:
    """Manual create -- the live-demo "paste in a real denial letter"
    flow. Always lands as status="new" so the existing "Process with AI"
    button (detail view) has something to run against. `payer`/`claim_ref`
    are DB-required columns but optional here for a fast paste-and-go demo
    -- unset ones get obviously-a-placeholder defaults, never silently
    fabricated-looking real-seeming values."""
    if body.source_company not in PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown source_company={body.source_company!r}. Known profiles: {sorted(PROFILES)}",
        )

    denial = Denial(
        source_company=body.source_company,
        raw_text=body.raw_text,
        payer=body.payer or "Unknown (manual entry)",
        claim_ref=body.claim_ref or f"MANUAL-{uuid.uuid4().hex[:8]}",
        received_at=body.received_at or datetime.now(timezone.utc),
        status="new",
    )
    db.add(denial)
    db.commit()
    db.refresh(denial)

    return DenialListItem(
        id=denial.id,
        source_company=denial.source_company,
        status=denial.status,
        payer=denial.payer,
        claim_ref=denial.claim_ref,
        received_at=denial.received_at,
        has_classification=False,
        has_appeal=False,
    )


@router.get("/{denial_id}", response_model=DenialDetail)
def get_denial_detail(denial_id: uuid.UUID, db: Session = Depends(get_db)) -> DenialDetail:
    denial = _get_denial_or_404(db, denial_id)

    extraction = (
        db.query(Extraction)
        .filter(Extraction.denial_id == denial_id)
        .order_by(Extraction.created_at.desc())
        .first()
    )
    classification = (
        db.query(Classification)
        .filter(Classification.denial_id == denial_id)
        .order_by(Classification.created_at.desc())
        .first()
    )
    appeal = (
        db.query(Appeal)
        .filter(Appeal.denial_id == denial_id)
        .order_by(Appeal.created_at.desc())
        .first()
    )
    audit_events = (
        db.query(AuditEvent)
        .filter(AuditEvent.denial_id == denial_id)
        .order_by(AuditEvent.corrected_at.desc())
        .all()
    )

    return DenialDetail(
        id=denial.id,
        source_company=denial.source_company,
        status=denial.status,
        payer=denial.payer,
        claim_ref=denial.claim_ref,
        received_at=denial.received_at,
        created_at=denial.created_at,
        raw_text=denial.raw_text,
        extraction=extraction,
        classification=classification,
        appeal=appeal,
        audit_events=[AuditEventOut.model_validate(e) for e in audit_events],
    )


@router.post("/{denial_id}/process", response_model=ProcessResponse)
def process_denial(denial_id: uuid.UUID, db: Session = Depends(get_db)) -> ProcessResponse:
    """Runs the real extract -> classify -> draft_appeal pipeline for this one
    denial, on-demand. Makes real Anthropic API calls -- real cost."""
    # Local import: pipeline.run opens its own SessionLocal() and shouldn't
    # be pulled in at module-import time for routes that never call it.
    from pipeline.run import process_denial_by_id

    _get_denial_or_404(db, denial_id)
    try:
        status = process_denial_by_id(denial_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProcessResponse(denial_id=denial_id, status=status)


@router.post("/{denial_id}/appeal/draft", response_model=ProcessResponse)
def draft_appeal_for_denial(denial_id: uuid.UUID, db: Session = Depends(get_db)) -> ProcessResponse:
    """Runs *only* the appeal-drafting stage against this denial's current
    (most recent) extraction and classification rows -- does not touch
    extraction or classification. Distinct from POST /process, which reruns
    the full pipeline (and would overwrite a human classification
    correction just to get a fresh appeal). See
    pipeline.run.draft_appeal_only for how a classification.category
    correction, if one has been logged, is folded into the appeal prompt
    without mutating the classifications row. Makes a real Anthropic API
    call -- real cost."""
    from pipeline.run import draft_appeal_only

    _get_denial_or_404(db, denial_id)
    try:
        status = draft_appeal_only(denial_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProcessResponse(denial_id=denial_id, status=status)


@router.post("/{denial_id}/appeal/status", response_model=AppealOut)
def update_appeal_status(
    denial_id: uuid.UUID, body: AppealStatusUpdateRequest, db: Session = Depends(get_db)
) -> AppealOut:
    denial = _get_denial_or_404(db, denial_id)

    if body.status not in APPEAL_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {APPEAL_STATUSES}, got {body.status!r}",
        )

    appeal = (
        db.query(Appeal)
        .filter(Appeal.denial_id == denial_id)
        .order_by(Appeal.created_at.desc())
        .first()
    )
    if appeal is None:
        raise HTTPException(status_code=404, detail=f"no appeal drafted yet for denial_id={denial_id}")

    previous_status = appeal.status
    reviewed_at = datetime.now(timezone.utc)

    # Mutable "current state" -- still updated in place, same as before, so
    # the detail view's appeal panel keeps showing "last reviewed by X on Y".
    appeal.status = body.status
    appeal.reviewer = body.reviewer
    appeal.reviewed_at = reviewed_at
    # Mirror the review decision onto the denial's own status so the queue
    # list (which only shows denials.status, not the nested appeal) reflects
    # it too -- "approved"/"rejected" are valid denial_status enum values for
    # exactly this. "sent" has no denial-level equivalent (it's a downstream
    # state of an already-approved appeal), so it doesn't touch denial.status.
    if body.status in ("approved", "rejected"):
        denial.status = body.status

    # Permanent, append-only audit record of this decision -- unlike the
    # appeal row above, this is never updated or deleted by a later review,
    # reprocess, or re-review. This is what makes "who approved this and
    # when" recoverable even after the appeal row itself is later overwritten
    # (re-review) or superseded (reprocess creates a new Appeal row).
    audit_event = AuditEvent(
        denial_id=denial_id,
        appeal_id=appeal.id,
        event_type="appeal_review",
        field_corrected="appeal.status",
        old_value=previous_status,
        new_value=body.status,
        corrected_by=body.reviewer,
        corrected_at=reviewed_at,
    )
    db.add(audit_event)

    db.commit()
    db.refresh(appeal)
    return appeal


@router.post("/{denial_id}/corrections", response_model=AuditEventOut, status_code=201)
def create_correction(
    denial_id: uuid.UUID, body: CorrectionCreateRequest, db: Session = Depends(get_db)
) -> AuditEventOut:
    """Logs a human correction to an AI-produced field -- the compliance
    audit-trail feature. Does not mutate the corrected field itself
    (extraction/classification/appeal rows are left as the AI produced
    them); this only appends an audit row.

    One deliberate exception to "audit-only, no downstream effect": when
    field_corrected="classification.category", POST /{denial_id}/appeal/draft
    (pipeline.run.draft_appeal_only) looks up the most recent such
    correction and uses its new_value -- not the classifications row's
    original category -- when building the appeal-drafting prompt. This is
    the only place a correction ever influences behavior; the
    classifications row itself is still never overwritten, so the AI's
    original output and the audit trail both stay intact. See
    draft_appeal_only's docstring for the full rationale."""
    _get_denial_or_404(db, denial_id)

    correction = AuditEvent(
        denial_id=denial_id,
        event_type="correction",
        field_corrected=body.field_corrected,
        old_value=body.old_value,
        new_value=body.new_value,
        corrected_by=body.corrected_by,
        notes=body.notes,
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)
    return correction
