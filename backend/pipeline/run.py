"""
Orchestrates a denial through extract -> classify -> draft_appeal, advancing
db/models.py's Denial.status through its lifecycle as each stage completes:

    new -> processing -> classified -> appeal_drafted
                      (or) -> needs_review (low classification confidence,
                                             or any stage failing outright)

Callable two ways:
  - As a library function, for a later on-demand API endpoint:
        from pipeline.run import process_denial_by_id
  - As a batch script, from backend/:
        python -m pipeline.run --all
    which processes every denial currently in status="new".
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import CLASSIFICATION_CATEGORIES, AuditEvent, Classification, Denial, Extraction  # noqa: E402
from db.session import SessionLocal  # noqa: E402
from profiles import get_profile  # noqa: E402

from pipeline.classify import classify_denial  # noqa: E402
from pipeline.draft_appeal import draft_appeal  # noqa: E402
from pipeline.extract import extract_denial  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("pipeline.run")

# Confidence threshold below which a classified denial is routed to
# needs_review instead of continuing on to appeal drafting.
#
# 0.7 is a deliberately middle-of-the-road cut for a 6-way, well-specified
# categorization task (each category maps to fairly distinctive CARC codes
# per classify.py's CATEGORY_GUIDE): below it, the model is expressing real
# uncertainty about the root cause, and drafting an appeal that argues the
# wrong point wastes more staff time reviewing than it saves -- better to
# route straight to a human. Above it, the categorization task is
# constrained enough that false "high confidence" calls should be rare, and
# every drafted appeal still passes through appeals.status="draft" for
# human review before it's ever sent, so 0.7 doesn't need to be
# conservative to the point of paranoia. This is a starting point, not a
# tuned value -- Phase 3's eval harness against eval_labeled.json is what
# should actually calibrate it (e.g. by plotting confidence vs. correctness
# and picking the threshold that trades off review load against error rate).
CONFIDENCE_THRESHOLD = 0.7


def _log_ai_action(db, denial: Denial, *, stage: str, summary: str, notes: str | None = None) -> None:
    """Append an event_type="ai_action" row to the unified audit-event log
    (see db.models.AuditEvent) right after a pipeline stage succeeds, so the
    Audit History timeline tells the whole story -- AI extracted -> AI
    classified -> AI drafted -> human corrected -> human approved -- not just
    the human half of it. Does not commit; the caller owns the transaction
    boundary, same as every other write in this module.

    `stage` is the pipeline stage key ("extraction" | "classification" |
    "appeal_drafting") stored in field_corrected. old_value is always "" --
    there's no "previous value" for a stage running for the first time, this
    is a creation event, not an edit. corrected_by is always the literal
    string "AI", which is what the frontend keys off of to badge these
    events as system-originated rather than human-originated.
    """
    db.add(
        AuditEvent(
            denial_id=denial.id,
            event_type="ai_action",
            field_corrected=stage,
            old_value="",
            new_value=summary,
            corrected_by="AI",
            notes=notes,
        )
    )


def process_denial(db, denial: Denial) -> str:
    """Run one denial through the full pipeline. Commits after every status
    transition so a crash mid-pipeline leaves the denial in whatever state
    it last successfully reached, not in an inconsistent partial state."""
    profile = get_profile(denial.source_company)
    logger.info(
        "[%s] processing (claim_ref=%s, profile=%s)", denial.id, denial.claim_ref, profile.key
    )
    denial.status = "processing"
    db.commit()

    extraction = extract_denial(db, denial, profile)
    if not extraction.success:
        logger.error("[%s] extraction failed: %s", denial.id, extraction.error)
        denial.status = "needs_review"
        db.commit()
        return denial.status
    _log_ai_action(
        db, denial,
        stage="extraction",
        summary="Processed denial letter",
        notes=f"Extracted {len(extraction.data)} field(s) from the denial letter.",
    )
    db.commit()  # persist the successful extraction row + token_usage row + ai_action event

    classification = classify_denial(db, denial, extraction.data, profile)
    if not classification.success:
        logger.error("[%s] classification failed: %s", denial.id, classification.error)
        denial.status = "needs_review"
        db.commit()
        return denial.status
    _log_ai_action(
        db, denial,
        stage="classification",
        summary=f"Classified as {classification.data['category']}",
        notes=f"Confidence {classification.data['confidence']:.2f}.",
    )

    denial.status = "classified"
    db.commit()  # persist the classification row + token_usage row + status + ai_action event

    confidence = classification.data["confidence"]
    category = classification.data["category"]
    if confidence < CONFIDENCE_THRESHOLD:
        logger.warning(
            "[%s] confidence %.2f below threshold %.2f (category=%s) -- routing to needs_review",
            denial.id, confidence, CONFIDENCE_THRESHOLD, category,
        )
        denial.status = "needs_review"
        db.commit()
        return denial.status

    appeal = draft_appeal(db, denial, extraction.data, classification.data, profile)
    if not appeal.success:
        logger.error("[%s] appeal drafting failed: %s", denial.id, appeal.error)
        denial.status = "needs_review"
        db.commit()
        return denial.status
    _log_ai_action(
        db, denial,
        stage="appeal_drafting",
        summary="Drafted appeal",
        notes=f"Draft length {len(appeal.draft_text)} character(s).",
    )

    denial.status = "appeal_drafted"
    db.commit()
    logger.info(
        "[%s] done -> appeal_drafted (category=%s, confidence=%.2f)",
        denial.id, category, confidence,
    )
    return denial.status


def process_denial_by_id(denial_id: uuid.UUID | str) -> str:
    """Single-denial entry point -- e.g. for a future on-demand API endpoint
    that reprocesses one denial. Opens and closes its own session."""
    db = SessionLocal()
    try:
        denial = db.get(Denial, denial_id)
        if denial is None:
            raise ValueError(f"no denial with id={denial_id}")
        return process_denial(db, denial)
    finally:
        db.close()


def draft_appeal_only(denial_id: uuid.UUID | str) -> str:
    """
    Single-stage entry point: run *only* draft_appeal against a denial's
    existing (most recent) extraction and classification rows, without
    rerunning extraction or classification.

    Why this exists: a denial in needs_review (low classification
    confidence, so process_denial never reached draft_appeal) can have its
    classification hand-corrected via POST /corrections. That endpoint is
    audit-log-only by design -- see api/routes/denials.py's
    create_correction docstring -- it does NOT mutate the classifications
    row itself, so the AI's original (possibly wrong) category is still
    what's sitting in the classifications table after a correction. If we
    naively read that row here, a "draft appeal from current state" button
    would silently draft off the ORIGINAL category and the correction would
    have no effect, defeating the point. So: this function looks for the
    most recent corrections row with field_corrected="classification.category"
    for this denial, and if one exists, its new_value overrides the category
    used to build the appeal-drafting prompt -- the classifications row on
    disk is still untouched (audit trail intact), but the appeal reflects
    the human's correction.

    Raises ValueError if the denial doesn't exist, or has no extraction or
    no classification yet (both required inputs to draft_appeal) -- those
    are real precondition failures for this endpoint, not a pipeline stage
    failure, so they're surfaced as 4xx by the caller rather than routing
    the denial to needs_review.
    """
    db = SessionLocal()
    try:
        denial = db.get(Denial, denial_id)
        if denial is None:
            raise ValueError(f"no denial with id={denial_id}")

        extraction = (
            db.query(Extraction)
            .filter(Extraction.denial_id == denial.id)
            .order_by(Extraction.created_at.desc())
            .first()
        )
        if extraction is None:
            raise ValueError(
                f"denial {denial_id} has no extraction yet -- run full processing first"
            )

        classification_row = (
            db.query(Classification)
            .filter(Classification.denial_id == denial.id)
            .order_by(Classification.created_at.desc())
            .first()
        )
        if classification_row is None:
            raise ValueError(
                f"denial {denial_id} has no classification yet -- run full processing first"
            )

        category = classification_row.category
        reasoning = (
            f"Automated classification (model confidence {classification_row.confidence:.2f})."
        )

        correction = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.denial_id == denial.id,
                AuditEvent.field_corrected == "classification.category",
            )
            .order_by(AuditEvent.corrected_at.desc())
            .first()
        )
        if correction is not None:
            if correction.new_value not in CLASSIFICATION_CATEGORIES:
                raise ValueError(
                    f"denial {denial_id}'s most recent classification.category correction "
                    f"has an invalid new_value={correction.new_value!r}; must be one of "
                    f"{CLASSIFICATION_CATEGORIES}"
                )
            category = correction.new_value
            reasoning = (
                f"Category corrected by {correction.corrected_by} from "
                f"'{correction.old_value}' to '{correction.new_value}'"
                + (f": {correction.notes}" if correction.notes else "")
                + ". Draft this appeal around the CORRECTED category, not the original "
                "AI classification."
            )
            logger.info(
                "[%s] using human-corrected category=%s (was %s) for standalone appeal draft",
                denial.id, category, classification_row.category,
            )

        classification_data = {
            "category": category,
            "confidence": classification_row.confidence,
            "reasoning": reasoning,
        }

        profile = get_profile(denial.source_company)
        result = draft_appeal(
            db, denial, extraction.extracted_fields, classification_data, profile
        )
        if not result.success:
            db.rollback()
            raise ValueError(f"appeal drafting failed: {result.error}")
        _log_ai_action(
            db, denial,
            stage="appeal_drafting",
            summary="Drafted appeal",
            notes=f"Draft length {len(result.draft_text)} character(s).",
        )

        denial.status = "appeal_drafted"
        db.commit()
        logger.info("[%s] standalone appeal draft complete (category=%s)", denial.id, category)
        return denial.status
    finally:
        db.close()


def process_all_new(limit: int | None = None, source_company: str | None = None) -> dict[str, int]:
    """Batch entry point: process every denial with status='new', optionally
    scoped to one source_company/profile (e.g. to run just the newly-seeded
    Summit DME Providers denials without touching MEC's). Returns a dict of
    final-status -> count."""
    db = SessionLocal()
    try:
        query = db.query(Denial).filter(Denial.status == "new").order_by(Denial.claim_ref)
        if source_company:
            query = query.filter(Denial.source_company == source_company)
        if limit:
            query = query.limit(limit)
        denials = query.all()
        logger.info("found %d denial(s) with status='new'", len(denials))

        counts: dict[str, int] = {}
        for denial in denials:
            try:
                status = process_denial(db, denial)
            except Exception:
                # Anything that escapes process_denial is a bug, not an
                # expected pipeline failure (those are handled per-stage and
                # already route to needs_review). Still: don't let one
                # denial's unhandled exception kill the whole batch or leave
                # the session in a broken transaction for the next denial.
                logger.exception("[%s] unhandled error -- marking needs_review", denial.id)
                db.rollback()
                denial = db.get(Denial, denial.id)
                denial.status = "needs_review"
                db.commit()
                status = "needs_review"
            counts[status] = counts.get(status, 0) + 1
        return counts
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Run the denial triage + appeal-drafting pipeline.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Process every denial with status='new'.")
    group.add_argument("--denial-id", type=str, help="Process a single denial by id.")
    parser.add_argument(
        "--limit", type=int, default=None, help="Cap the number of denials processed with --all."
    )
    parser.add_argument(
        "--source-company",
        type=str,
        default=None,
        help=(
            "With --all, only process denials with this source_company "
            "(e.g. 'summit_dme_providers'). Must match a registered profile key "
            "in backend/profiles/. Omit to process --all's denials regardless "
            "of company."
        ),
    )
    args = parser.parse_args()

    if args.denial_id:
        status = process_denial_by_id(args.denial_id)
        print(f"denial {args.denial_id}: {status}")
    else:
        counts = process_all_new(limit=args.limit, source_company=args.source_company)
        print("\nBatch run complete:")
        for status, n in sorted(counts.items()):
            print(f"  {status}: {n}")


if __name__ == "__main__":
    main()
