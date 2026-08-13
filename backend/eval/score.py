"""
Phase 3 eval scoring: pulls the Phase 2 pipeline's already-persisted results
(extractions / classifications / appeals) for the 24 denials in
backend/data/eval_labeled.json out of the DB and scores them against that
file's hand-labeled ground truth, on three dimensions.

Deliberately does NOT call the Anthropic API or an LLM judge for any of this
-- everything here is exact string/substring comparison against known
literal values, so a re-run is free and its output is reproducible given the
same DB contents. That determinism is the point: this is a regression gate
meant to be run on every change to the pipeline, not a one-off quality
report.

Dimensions
----------
1. classification accuracy -- predicted Classification.category exactly
   equals eval_labeled.json's ground_truth_category. Binary per denial.

2. extraction accuracy -- predicted Extraction.extracted_fields['carc_code']
   exactly equals ground_truth_carc_code. Binary per denial; this is the
   dimension folded into the weighted overall score. We additionally check
   rarc_code, and -- as a drift sanity check, not part of the scored metric
   -- claim_ref and patient_ref against values recovered directly from the
   denial's own raw_text via regex (i.e. independent of anything the
   pipeline produced), so a silent extraction regression on the "easy"
   fields would show up even though it isn't carc/rarc.

3. appeal completeness -- for each denial's required_appeal_elements (free
   text describing a fact the drafted appeal must reference), we pull the
   literal tokens embedded in that requirement's own text (claim numbers,
   patient refs, CPT/ICD-10/CARC codes, prior-auth numbers, NPIs, dates --
   all of which the ground-truth file spells out explicitly in parentheses)
   and check each is a substring of the drafted appeal text. A requirement
   with no extractable literal token (e.g. "must address the timely filing
   gap directly") can't be checked this way without a semantic judgment
   call, which we're deliberately not making here -- those are counted
   separately as "unverifiable" and excluded from the completeness
   denominator, not silently scored as pass or fail.
   Only denials that actually reached appeal_drafted have a draft to score;
   denials routed to needs_review (low classification confidence, or a
   stage failure) have no appeal and are reported separately rather than
   folded into the completeness average as an implicit zero -- routing a
   low-confidence denial to a human is the pipeline working as designed,
   not an appeal-quality failure.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import Appeal, Classification, Denial, Extraction  # noqa: E402
from db.session import SessionLocal  # noqa: E402

EVAL_LABELED_PATH = Path(__file__).resolve().parent.parent / "data" / "eval_labeled.json"

# ---------------------------------------------------------------------------
# Overall-score weighting
# ---------------------------------------------------------------------------
# classification 0.4 / extraction 0.3 / appeal completeness 0.3.
# Classification gets the largest weight because it's the pipeline's single
# highest-leverage decision: it determines the CONFIDENCE_THRESHOLD routing
# (pipeline/run.py) and which category-specific guidance the appeal drafter
# uses, so a wrong category tends to cascade into a wrong or off-target
# appeal even when extraction and drafting both "work." Extraction and
# appeal completeness split the remainder evenly -- extraction accuracy is
# a prerequisite for a grounded appeal, but errors there are typically
# narrower (one wrong field) than a wrong classification.
WEIGHT_CLASSIFICATION = 0.4
WEIGHT_EXTRACTION = 0.3
WEIGHT_APPEAL_COMPLETENESS = 0.3

# Literal-token patterns pulled out of a required_appeal_elements string.
# Order doesn't matter; duplicates are deduped via a set.
_LITERAL_PATTERNS = [
    r"\bCLM-\d+\b",
    r"\bPT-\d+\b",
    r"\bAUTH-\d+\b",
    r"\bCARC \d+\b",
    r"\b\d{2}/\d{2}/\d{4}\b",
]


def _extract_literal_anchors(element_text: str) -> list[str]:
    """Pull the literal, checkable facts out of one required_appeal_elements
    sentence (claim/patient/auth refs, CARC codes, dates, CPT codes, NPIs,
    ICD-10 codes). Returns [] if the sentence is purely qualitative."""
    anchors: set[str] = set()
    for pattern in _LITERAL_PATTERNS:
        anchors.update(re.findall(pattern, element_text))
    for m in re.findall(r"NPI,?\s*(\d{6,10})", element_text):
        anchors.add(m)
    for m in re.findall(r"CPT code (\S+?)[\s)]", element_text + " "):
        anchors.add(m.rstrip(","))
    for m in re.findall(r"procedure ([A-Za-z0-9]+)\b", element_text):
        # duplicate_claim wording: "...separate encounter for procedure 67028"
        if re.match(r"^[A-Za-z]?\d{3,5}$", m):
            anchors.add(m)
    for m in re.findall(r"diagnosis ([A-Z]\d{2}\.?\w*)", element_text):
        anchors.add(m.rstrip(","))
    return sorted(anchors)


_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _anchor_present(anchor: str, draft_lower: str) -> bool:
    """Substring check for one literal anchor. Dates get special handling: a
    well-written appeal letter is entitled to render "07/10/2024" as
    "July 10, 2024" (both forms showed up in the real drafted letters), so a
    date anchor matches if the MM/DD/YYYY literal OR either common
    spelled-out rendering (with/without zero-padded day) appears."""
    if _DATE_RE.match(anchor):
        if anchor in draft_lower:
            return True
        dt = datetime.strptime(anchor, "%m/%d/%Y")
        spelled_padded = dt.strftime("%B %d, %Y").lower()
        spelled_unpadded = dt.strftime("%B %-d, %Y").lower()
        return spelled_padded in draft_lower or spelled_unpadded in draft_lower
    return anchor.lower() in draft_lower


def _ground_truth_sanity_fields(raw_text: str) -> dict:
    """Recover patient_ref / cpt_code / physician_npi directly from a
    denial's raw_text via regex, independent of anything the pipeline
    produced -- used only as the extraction-accuracy drift sanity check."""
    patient_ref = None
    m = re.search(r"Patient Reference:\s*(PT-\d+)", raw_text)
    if m:
        patient_ref = m.group(1)
    cpt_code = None
    m = re.search(r"Procedure:\s*CPT\s+([A-Za-z0-9]+)", raw_text)
    if m:
        cpt_code = m.group(1)
    physician_npi = None
    m = re.search(r"NPI\s*(\d+)", raw_text)
    if m:
        physician_npi = m.group(1)
    return {"patient_ref": patient_ref, "cpt_code": cpt_code, "physician_npi": physician_npi}


@dataclass
class DenialScore:
    synthetic_id: str
    claim_ref: str
    denial_found: bool = True
    extraction_found: bool = True
    classification_found: bool = True

    predicted_category: str | None = None
    ground_truth_category: str | None = None
    classification_correct: bool | None = None

    predicted_carc: str | None = None
    ground_truth_carc: str | None = None
    carc_match: bool | None = None
    predicted_rarc: str | None = None
    ground_truth_rarc: str | None = None
    rarc_match: bool | None = None
    # Sanity-check-only fields, not part of the weighted score.
    claim_ref_sanity_match: bool | None = None
    patient_ref_sanity_match: bool | None = None

    denial_status: str | None = None
    appeal_drafted: bool = False
    required_elements_total: int = 0
    required_elements_checkable: int = 0
    required_elements_satisfied: int = 0
    appeal_completeness_fraction: float | None = None
    missing_elements: list[str] = field(default_factory=list)
    unverifiable_elements: list[str] = field(default_factory=list)


def score_denial(db, record: dict) -> DenialScore:
    claim_ref = record["claim_ref"]
    ds = DenialScore(synthetic_id=record["synthetic_id"], claim_ref=claim_ref)

    denial = db.query(Denial).filter(Denial.claim_ref == claim_ref).first()
    if denial is None:
        ds.denial_found = False
        return ds
    ds.denial_status = denial.status

    # Most-recent row per stage, in case a denial was ever reprocessed.
    extraction = (
        db.query(Extraction).filter(Extraction.denial_id == denial.id)
        .order_by(Extraction.created_at.desc()).first()
    )
    classification = (
        db.query(Classification).filter(Classification.denial_id == denial.id)
        .order_by(Classification.created_at.desc()).first()
    )
    appeal = (
        db.query(Appeal).filter(Appeal.denial_id == denial.id)
        .order_by(Appeal.created_at.desc()).first()
    )

    # --- classification accuracy -----------------------------------------
    if classification is None:
        ds.classification_found = False
    else:
        ds.predicted_category = classification.category
        ds.ground_truth_category = record["ground_truth_category"]
        ds.classification_correct = ds.predicted_category == ds.ground_truth_category

    # --- extraction accuracy ------------------------------------------
    if extraction is None or extraction.extracted_fields.get("error"):
        ds.extraction_found = False
    else:
        fields = extraction.extracted_fields
        ds.predicted_carc = fields.get("carc_code")
        ds.ground_truth_carc = record["ground_truth_carc_code"]
        ds.carc_match = ds.predicted_carc == ds.ground_truth_carc

        ds.predicted_rarc = fields.get("rarc_code")
        ds.ground_truth_rarc = record.get("ground_truth_rarc_code")
        if ds.ground_truth_rarc:
            ds.rarc_match = ds.predicted_rarc == ds.ground_truth_rarc

        gt_sanity = _ground_truth_sanity_fields(record["raw_text"])
        ds.claim_ref_sanity_match = fields.get("claim_ref") == claim_ref
        if gt_sanity["patient_ref"]:
            ds.patient_ref_sanity_match = fields.get("patient_ref") == gt_sanity["patient_ref"]

    # --- appeal completeness ----------------------------------------------
    required_elements = record.get("required_appeal_elements", [])
    ds.required_elements_total = len(required_elements)

    if appeal is None:
        ds.appeal_drafted = False
        return ds

    ds.appeal_drafted = True
    draft_lower = appeal.draft_text.lower()
    satisfied = 0
    checkable = 0
    for element in required_elements:
        anchors = _extract_literal_anchors(element)
        if not anchors:
            ds.unverifiable_elements.append(element)
            continue
        checkable += 1
        if all(_anchor_present(anchor, draft_lower) for anchor in anchors):
            satisfied += 1
        else:
            ds.missing_elements.append(element)

    ds.required_elements_checkable = checkable
    ds.required_elements_satisfied = satisfied
    ds.appeal_completeness_fraction = (satisfied / checkable) if checkable else None

    return ds


def run_scoring() -> dict:
    """Score all 24 labeled denials against the DB and return the full
    breakdown (per-denial results + aggregate metrics + overall score)."""
    records = json.loads(EVAL_LABELED_PATH.read_text())
    db = SessionLocal()
    try:
        results = [score_denial(db, r) for r in records]
    finally:
        db.close()

    n = len(results)
    data_issues = [r.synthetic_id for r in results if not (r.denial_found and r.extraction_found and r.classification_found)]

    classification_scored = [r for r in results if r.classification_correct is not None]
    classification_accuracy = (
        sum(1 for r in classification_scored if r.classification_correct) / len(classification_scored)
        if classification_scored else None
    )

    carc_scored = [r for r in results if r.carc_match is not None]
    extraction_accuracy = (
        sum(1 for r in carc_scored if r.carc_match) / len(carc_scored) if carc_scored else None
    )
    rarc_scored = [r for r in results if r.rarc_match is not None]
    rarc_accuracy = sum(1 for r in rarc_scored if r.rarc_match) / len(rarc_scored) if rarc_scored else None
    claim_ref_sanity_scored = [r for r in results if r.claim_ref_sanity_match is not None]
    claim_ref_sanity_rate = (
        sum(1 for r in claim_ref_sanity_scored if r.claim_ref_sanity_match) / len(claim_ref_sanity_scored)
        if claim_ref_sanity_scored else None
    )
    patient_ref_sanity_scored = [r for r in results if r.patient_ref_sanity_match is not None]
    patient_ref_sanity_rate = (
        sum(1 for r in patient_ref_sanity_scored if r.patient_ref_sanity_match) / len(patient_ref_sanity_scored)
        if patient_ref_sanity_scored else None
    )

    drafted = [r for r in results if r.appeal_drafted and r.appeal_completeness_fraction is not None]
    appeal_completeness = (
        sum(r.appeal_completeness_fraction for r in drafted) / len(drafted) if drafted else None
    )
    needs_review = [r for r in results if not r.appeal_drafted]

    weighted_terms = []
    if classification_accuracy is not None:
        weighted_terms.append((WEIGHT_CLASSIFICATION, classification_accuracy))
    if extraction_accuracy is not None:
        weighted_terms.append((WEIGHT_EXTRACTION, extraction_accuracy))
    if appeal_completeness is not None:
        weighted_terms.append((WEIGHT_APPEAL_COMPLETENESS, appeal_completeness))
    total_weight = sum(w for w, _ in weighted_terms)
    overall_score = (sum(w * v for w, v in weighted_terms) / total_weight) if total_weight else None

    per_denial = []
    for r in results:
        per_denial.append({
            "synthetic_id": r.synthetic_id,
            "claim_ref": r.claim_ref,
            "denial_status": r.denial_status,
            "predicted_category": r.predicted_category,
            "ground_truth_category": r.ground_truth_category,
            "classification_correct": r.classification_correct,
            "predicted_carc": r.predicted_carc,
            "ground_truth_carc": r.ground_truth_carc,
            "carc_match": r.carc_match,
            "predicted_rarc": r.predicted_rarc,
            "ground_truth_rarc": r.ground_truth_rarc,
            "rarc_match": r.rarc_match,
            "claim_ref_sanity_match": r.claim_ref_sanity_match,
            "patient_ref_sanity_match": r.patient_ref_sanity_match,
            "appeal_drafted": r.appeal_drafted,
            "required_elements_total": r.required_elements_total,
            "required_elements_checkable": r.required_elements_checkable,
            "required_elements_satisfied": r.required_elements_satisfied,
            "appeal_completeness_fraction": r.appeal_completeness_fraction,
            "missing_elements": r.missing_elements,
            "unverifiable_elements": r.unverifiable_elements,
        })

    return {
        "n_denials": n,
        "data_issues": data_issues,
        "classification_accuracy": classification_accuracy,
        "extraction_accuracy": extraction_accuracy,
        "extraction_rarc_accuracy": rarc_accuracy,
        "extraction_sanity_claim_ref_match_rate": claim_ref_sanity_rate,
        "extraction_sanity_patient_ref_match_rate": patient_ref_sanity_rate,
        "appeal_completeness": appeal_completeness,
        "appeal_completeness_n_drafted": len(drafted),
        "n_needs_review_no_appeal": len(needs_review),
        "needs_review_claim_refs": [r.claim_ref for r in needs_review],
        "overall_score": overall_score,
        "weights": {
            "classification": WEIGHT_CLASSIFICATION,
            "extraction": WEIGHT_EXTRACTION,
            "appeal_completeness": WEIGHT_APPEAL_COMPLETENESS,
        },
        "per_denial": per_denial,
    }


if __name__ == "__main__":
    result = run_scoring()
    print(json.dumps(result, indent=2))
