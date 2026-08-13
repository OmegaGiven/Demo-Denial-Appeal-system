#!/usr/bin/env python3
"""
Generates synthetic claim-denial letters for "Summit DME Providers" (a fictional
national complex rehab technology / durable medical equipment provider) --
the Phase 4 second-company dataset, proving the pipeline built for
Meridian Eye Care Partners (see generate_synthetic_data.py) generalizes
to a genuinely different claim type rather than being eye-care-only.

Design notes (same approach as generate_synthetic_data.py, deliberately):
- Deterministic: a fixed random seed makes output reproducible across runs.
- Data-driven: letters are assembled from pools of payers, physicians,
  equipment, diagnoses, and sentence fragments, with randomized selection
  per letter, so output reads as varied prose rather than mail-merged
  template text with blanks filled in.
- CARC/RARC codes used below are real, current X12-maintained codes. They
  are the SAME verified codes used in generate_synthetic_data.py's
  CATEGORIES (CARCs are generic across specialties, not eye-care- or
  DME-specific) -- re-verified against x12.org/codes for this phase via a
  live WebFetch of x12.org/codes/claim-adjustment-reason-codes and
  x12.org/codes/remittance-advice-remark-codes. One RARC that came up in a
  preliminary search (M127, "missing medical record") was checked and
  DROPPED because x12.org currently lists it as "Reserved for future
  use" -- not a usable code.
- HCPCS Level II equipment codes are real, current codes (verified via web
  search against AAPC/Palmetto GBA DMECS/CMS coding references): K0823
  (power wheelchair, group 2 standard), E1130 (wheelchair, standard),
  E0601 (CPAP device), E0470 (bi-level respiratory assist device, no
  backup rate), E0260 (semi-electric hospital bed), L1960 (custom-fabricated
  ankle-foot orthosis), L5856 (microprocessor-controlled knee-shin system,
  lower-limb prosthesis addition).
- No real people, patients, payers, or PHI of any kind. All names, payers,
  NPIs, member IDs, and claim numbers are synthetic and clearly fabricated.

Usage
-----
    python generate_synthetic_data_summit_dme_providers.py

Writes (relative to this file's directory):
    denials_summit_dme_providers.json   -- synthetic DME/CRT denial dataset
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

SEED = 20260814
OUTPUT_DIR = Path(__file__).resolve().parent
TOTAL_DENIALS = 14
SOURCE_COMPANY = "summit_dme_providers"

# ---------------------------------------------------------------------------
# Reference / entity pools (all synthetic)
# ---------------------------------------------------------------------------

PAYERS = [
    "Harborview Health Plan",
    "Meridian Community Insurance",
    "Northgate Assurance Co.",
    "Continental Care Alliance",
    "Pinnacle Point Health",
    "Summit Ridge Insurance",
    "Cascade Mutual Health",
    "Fieldstone Health Network",
    "Riverstone Health Partners",
    "Vantage Point Insurance",
]

BRANCH_LOCATIONS = [
    "Summit DME Providers - Westgate Branch",
    "Summit DME Providers - Eastborough CRT Center",
    "Summit DME Providers - Fairhaven Branch",
    "Summit DME Providers - Millbrook Respiratory Services",
    "Summit DME Providers - Stonebridge Branch",
]

PHYSICIAN_FIRST = [
    "Elena", "Rajiv", "Marcus", "Priya", "Daniel", "Sofia", "Thomas",
    "Naomi", "Victor", "Amara", "Kenji", "Lucia",
]
PHYSICIAN_LAST = [
    "Marsh", "Kapoor", "Delgado", "Okafor", "Bennett", "Halvorsen",
    "Whitfield", "Suárez", "Ivanov", "Chen", "Osei", "Reyes",
]

APPEAL_CONTACT_TITLES = ["Branch Manager", "Billing Manager", "Reimbursement Coordinator"]

# HCPCS Level II equipment codes, real/current, with a plausible
# billed-amount range (USD) and plain-language equipment_type. Amounts are
# synthetic.
EQUIPMENT = [
    ("K0823", "power wheelchair, group 2 standard, captain's chair, patient weight capacity up to 300 lbs", "power wheelchair", (3200, 5800)),
    ("E1130", "wheelchair, standard, fixed full-length arms, fixed or swing-away detachable footrests", "manual wheelchair", (450, 900)),
    ("E0601", "continuous positive airway pressure (CPAP) device", "CPAP device", (700, 1200)),
    ("E0470", "bi-level respiratory assist device, without backup rate feature", "BiPAP device", (1400, 2400)),
    ("E0260", "hospital bed, semi-electric (head and foot adjustment), with any type side rails, with mattress", "hospital bed", (1100, 2000)),
    ("L1960", "ankle-foot orthosis, custom-fabricated", "ankle-foot orthosis (AFO)", (900, 1700)),
    ("L5856", "addition to lower extremity prosthesis, endoskeletal knee-shin system, microprocessor control", "lower-limb prosthesis (microprocessor knee)", (12000, 22000)),
]

DIAGNOSES = [
    ("G82.20", "paraplegia, unspecified"),
    ("M62.81", "muscle weakness (generalized)"),
    ("G12.21", "amyotrophic lateral sclerosis"),
    ("G80.1", "spastic diplegic cerebral palsy"),
    ("G47.33", "obstructive sleep apnea (adult) (pediatric)"),
    ("J96.10", "chronic respiratory failure, unspecified with hypoxia or hypercapnia"),
    ("M17.11", "unilateral primary osteoarthritis, right knee"),
    ("Z89.512", "acquired absence of left leg below knee"),
    ("S82.001A", "unspecified fracture of right patella, initial encounter"),
    ("M21.6X1", "other acquired deformities of right foot"),
]

# ---------------------------------------------------------------------------
# Category definitions with verified real CARC/RARC codes -- re-verified
# against x12.org/codes for this phase (see module docstring).
# ---------------------------------------------------------------------------

CATEGORIES = {
    "coding_error": {
        "carc": [
            ("4", "The procedure code is inconsistent with the modifier used, or a required modifier is missing."),
            ("11", "The diagnosis is inconsistent with the procedure."),
        ],
        "rarc": [
            ("M51", "Missing/incomplete/invalid procedure code(s)."),
            ("N56", "Procedure code billed is not correct/valid for the services billed or the date of service billed."),
            ("M76", "Missing/incomplete/invalid diagnosis or condition."),
        ],
    },
    "missing_information": {
        "carc": [
            ("16", "Claim/service lacks information or has submission/billing error(s)."),
            ("197", "Precertification/authorization/notification/pre-treatment absent."),
        ],
        "rarc": [
            ("MA130", "Your claim contains incomplete and/or invalid information, and no appeal rights are afforded because the claim is unprocessable."),
            ("M76", "Missing/incomplete/invalid diagnosis or condition."),
        ],
    },
    "medical_necessity": {
        "carc": [
            ("50", "These are non-covered services because this is not deemed a 'medical necessity' by the payer."),
        ],
        "rarc": [
            ("N115", "This decision was based on a Local Coverage Determination (LCD)."),
            ("N130", "Consult plan benefit documents/guidelines for information about restrictions for this service."),
        ],
    },
    "timely_filing": {
        "carc": [
            ("29", "The time limit for filing has expired."),
        ],
        "rarc": [
            ("N211", "Alert: You may not appeal this decision."),
        ],
    },
    "eligibility": {
        "carc": [
            ("31", "Patient cannot be identified as our insured."),
            ("26", "Expenses incurred prior to coverage."),
            ("27", "Expenses incurred after coverage terminated."),
        ],
        "rarc": [
            ("N30", "Patient ineligible for this service."),
            ("MA83", "Did not indicate whether we are the primary or secondary payer."),
        ],
    },
    "duplicate_claim": {
        "carc": [
            ("18", "Exact duplicate claim/service."),
            ("97", "The benefit for this service is included in the payment/allowance for another service/procedure that has already been adjudicated."),
        ],
        "rarc": [
            ("N19", "Procedure code incidental to primary procedure."),
        ],
    },
}

CATEGORY_ORDER = [
    "coding_error",
    "missing_information",
    "medical_necessity",
    "timely_filing",
    "eligibility",
    "duplicate_claim",
]

# ---------------------------------------------------------------------------
# Sentence-fragment pools for letter composition. Two writing "voices": terse
# EOB-style auto-generated text, and a longer narrative manual-review letter.
# ---------------------------------------------------------------------------

TERSE_OPENERS = [
    "This letter serves as notification that the above-referenced claim has been denied.",
    "Please be advised the claim referenced above has been processed and denied.",
    "The claim identified below has been reviewed and denied under the terms of the member's plan.",
    "Notice of claim denial for the item(s) identified below.",
]

NARRATIVE_OPENERS = [
    "Thank you for submitting the above claim for review. After careful evaluation by our clinical and claims review staff, we are writing to inform you that the claim has been denied.",
    "We have completed our review of the claim referenced above. This letter explains our determination and the basis for it.",
    "Our durable medical equipment review team has completed a manual review of the submitted claim. Unfortunately, we are unable to approve payment at this time for the reasons outlined below.",
    "Following a secondary review by our medical claims department, we are issuing this formal notice of denial for the claim described below.",
]

TERSE_BODY_TEMPLATES = [
    "Claim {claim_ref} for patient reference {patient_ref}, date of service {dos}, was denied. Reason code: CARC {carc_code} - {carc_desc}",
    "Item billed under HCPCS {hcpcs} ({hcpcs_desc}) on {dos} was not paid. CARC {carc_code}: {carc_desc}",
    "Denial reason: CARC {carc_code} - {carc_desc} Remark: RARC {rarc_code} - {rarc_desc}",
]

NARRATIVE_BODY_TEMPLATES = [
    "The claim submitted for {patient_ref}, service date {dos}, billed HCPCS {hcpcs} ({hcpcs_desc}) with diagnosis {icd10} ({icd10_desc}), in the amount of ${amount:,.2f}, could not be approved for payment. The applicable adjustment reason is CARC {carc_code} ({carc_desc}).",
    "Upon review, our determination is that this claim cannot be paid as submitted. The reason for this denial corresponds to CARC {carc_code}: {carc_desc} In addition, remark code RARC {rarc_code} applies: {rarc_desc}",
    "Our review found that the item dispensed on {dos} (HCPCS {hcpcs}, {hcpcs_desc}) does not meet the requirements for reimbursement under this plan. This determination is coded as CARC {carc_code} - {carc_desc}",
]

CATEGORY_EXPLANATION = {
    "coding_error": [
        "Our coding review identified an inconsistency between the HCPCS code and the modifier submitted on this claim.",
        "The diagnosis code submitted does not support medical necessity for the HCPCS code billed, per our coding edits.",
        "Please review the HCPCS/ICD-10 code combination and modifier(s) submitted and resubmit with the corrected coding if appropriate.",
    ],
    "missing_information": [
        "This claim was missing information required for adjudication, specifically a valid Letter of Medical Necessity or prior authorization on file for this item.",
        "The claim as submitted lacked sufficient documentation to process; no Letter of Medical Necessity or Certificate of Medical Necessity was found on file for this date of service.",
        "Required fields and supporting documentation on the claim submission were incomplete, preventing this claim from being adjudicated.",
    ],
    "medical_necessity": [
        "Based on our Local Coverage Determination for this equipment category, the documentation submitted did not establish medical necessity for the level of equipment billed.",
        "Our clinical reviewers determined that the submitted Letter of Medical Necessity does not support the plan's medical necessity criteria for this item.",
        "This item is subject to medical necessity review, and the records provided at the time of submission were insufficient to support coverage of this equipment.",
    ],
    "timely_filing": [
        "This plan requires claims to be submitted within {filing_days} days of the date of service. Our records show this claim was received {days_late} days after that deadline.",
        "The filing deadline under the member's plan has passed. Claims submitted after the timely filing limit cannot be considered for payment absent a qualifying exception.",
        "Per the provider agreement, claims must be filed within {filing_days} days of service; this submission exceeded that window.",
    ],
    "eligibility": [
        "Our records do not show active coverage for this member on the date of service billed.",
        "The patient's coverage under this plan had a gap that includes the date of service submitted on this claim.",
        "We were unable to verify eligibility for the member identified on this claim as of the service date.",
    ],
    "duplicate_claim": [
        "Our system identified a prior claim on file for the same patient, date of service, and HCPCS code.",
        "This claim appears to duplicate a previously adjudicated claim for the same item; only one payment is allowed per equipment delivery for this HCPCS code.",
        "The item billed on this claim was already reimbursed under a separate, previously processed claim.",
    ],
}

TERSE_CLOSERS = [
    "If you believe this determination was made in error, you may submit a written appeal within 90 days of this notice.",
    "Appeal rights: A written appeal may be submitted within 90 days of the date of this letter.",
    "You have the right to appeal this decision. Appeals must be submitted in writing within 90 days.",
]

NARRATIVE_CLOSERS = [
    "If you have additional documentation that addresses the basis for this denial, we encourage you to submit a formal appeal within 90 days of this letter. Our appeals department can be reached at the number listed on the member's ID card.",
    "Should you disagree with this determination, you have the right to request a formal appeal. Appeals must be submitted in writing within 90 days of the date of this notice and should include any supporting clinical documentation.",
    "We understand this determination may be disappointing. You may exercise your right to appeal within 90 days of this letter; please include any additional records that support medical necessity or correct any noted deficiencies.",
    "This determination is not final. A written appeal, along with any supporting documentation, may be submitted within 90 days from the date of this notice for further review.",
]

SIGNOFFS = [
    "Claims Review Department",
    "Provider Relations & Claims Department",
    "DME Utilization Review Department",
    "Appeals & Grievances Unit",
]


@dataclass
class Entity:
    patient_ref: str
    claim_ref: str
    physician_name: str
    physician_npi: str
    branch: str
    payer: str
    dos: date
    received_at: date
    hcpcs: str
    hcpcs_desc: str
    equipment_type: str
    icd10: str
    icd10_desc: str
    amount: float
    category: str
    carc_code: str
    carc_desc: str
    rarc_code: str
    rarc_desc: str
    style: str
    auth_number: str | None = None
    lmn_reference: str | None = None
    extra: dict = field(default_factory=dict)


def _fake_npi(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(10))


def _fake_patient_ref(rng: random.Random) -> str:
    return f"PT-{rng.randint(100000, 999999)}"


def _fake_claim_ref(rng: random.Random) -> str:
    return f"CLM-{rng.randint(1000000, 9999999)}"


def _fake_auth_number(rng: random.Random) -> str:
    return f"AUTH-{rng.randint(10000, 99999)}"


def _fake_lmn_reference(rng: random.Random) -> str:
    return f"LMN-{rng.randint(2025, 2026)}-{rng.randint(1000, 9999)}"


def build_entity(idx: int, category: str, rng: random.Random) -> Entity:
    physician_name = f"Dr. {rng.choice(PHYSICIAN_FIRST)} {rng.choice(PHYSICIAN_LAST)}, MD"
    hcpcs, hcpcs_desc, equipment_type, amount_range = rng.choice(EQUIPMENT)
    icd10, icd10_desc = rng.choice(DIAGNOSES)
    carc_code, carc_desc = rng.choice(CATEGORIES[category]["carc"])
    rarc_code, rarc_desc = rng.choice(CATEGORIES[category]["rarc"])

    received_at = date(2025, 1, 1) + timedelta(days=rng.randint(0, 540))
    if category == "timely_filing":
        filing_days = rng.choice([90, 120, 180])
        dos = received_at - timedelta(days=filing_days + rng.randint(15, 120))
    else:
        dos = received_at - timedelta(days=rng.randint(5, 45))

    entity = Entity(
        patient_ref=_fake_patient_ref(rng),
        claim_ref=_fake_claim_ref(rng),
        physician_name=physician_name,
        physician_npi=_fake_npi(rng),
        branch=rng.choice(BRANCH_LOCATIONS),
        payer=rng.choice(PAYERS),
        dos=dos,
        received_at=received_at,
        hcpcs=hcpcs,
        hcpcs_desc=hcpcs_desc,
        equipment_type=equipment_type,
        icd10=icd10,
        icd10_desc=icd10_desc,
        amount=round(rng.uniform(*amount_range), 2),
        category=category,
        carc_code=carc_code,
        carc_desc=carc_desc,
        rarc_code=rarc_code,
        rarc_desc=rarc_desc,
        style=rng.choice(["terse", "narrative"]),
    )

    if category == "missing_information":
        # This category is where the LMN/auth is the whole point -- leave it
        # absent so the denial letter (and later the appeal) are actually
        # about supplying it.
        entity.extra["missing_lmn"] = True
    elif category != "timely_filing":
        entity.auth_number = _fake_auth_number(rng)
        entity.lmn_reference = _fake_lmn_reference(rng)

    if category == "timely_filing":
        entity.extra["filing_days"] = rng.choice([90, 120, 180])
        entity.extra["days_late"] = (entity.received_at - entity.dos - timedelta(days=entity.extra["filing_days"])).days

    return entity


def compose_letter(entity: Entity, rng: random.Random) -> str:
    lines: list[str] = []
    lines.append(entity.payer)
    lines.append("Claims Correspondence Unit")
    lines.append("")
    lines.append(entity.received_at.strftime("%B %d, %Y"))
    lines.append("")
    lines.append(entity.branch)
    lines.append(f"Attn: {rng.choice(APPEAL_CONTACT_TITLES)}")
    lines.append("")
    lines.append("RE: NOTICE OF CLAIM DENIAL")
    lines.append(f"Patient Reference: {entity.patient_ref}")
    lines.append(f"Claim Number: {entity.claim_ref}")
    lines.append(f"Date of Service: {entity.dos.strftime('%m/%d/%Y')}")
    lines.append(f"Billed Amount: ${entity.amount:,.2f}")
    lines.append(f"Item: HCPCS {entity.hcpcs} ({entity.hcpcs_desc})")
    lines.append(f"Equipment Type: {entity.equipment_type}")
    lines.append(f"Diagnosis: ICD-10 {entity.icd10} ({entity.icd10_desc})")
    lines.append(f"Prescribing Physician: {entity.physician_name}, NPI {entity.physician_npi}")
    lines.append(f"Branch: {entity.branch}")
    if entity.auth_number:
        lines.append(f"Prior Authorization on File: {entity.auth_number}")
    if entity.lmn_reference:
        lines.append(f"Letter of Medical Necessity on File: {entity.lmn_reference}")
    lines.append("")

    opener = rng.choice(TERSE_OPENERS if entity.style == "terse" else NARRATIVE_OPENERS)
    lines.append(opener)
    lines.append("")

    fmt_kwargs = dict(
        claim_ref=entity.claim_ref,
        patient_ref=entity.patient_ref,
        dos=entity.dos.strftime("%m/%d/%Y"),
        hcpcs=entity.hcpcs,
        hcpcs_desc=entity.hcpcs_desc,
        icd10=entity.icd10,
        icd10_desc=entity.icd10_desc,
        amount=entity.amount,
        carc_code=entity.carc_code,
        carc_desc=entity.carc_desc,
        rarc_code=entity.rarc_code,
        rarc_desc=entity.rarc_desc,
    )
    body_pool = TERSE_BODY_TEMPLATES if entity.style == "terse" else NARRATIVE_BODY_TEMPLATES
    lines.append(rng.choice(body_pool).format(**fmt_kwargs))
    lines.append("")

    explanation = rng.choice(CATEGORY_EXPLANATION[entity.category])
    explanation = explanation.format(
        filing_days=entity.extra.get("filing_days", 90),
        days_late=entity.extra.get("days_late", 30),
    )
    lines.append(explanation)
    lines.append("")

    closer = rng.choice(TERSE_CLOSERS if entity.style == "terse" else NARRATIVE_CLOSERS)
    lines.append(closer)
    lines.append("")
    lines.append("Sincerely,")
    lines.append(rng.choice(SIGNOFFS))
    lines.append(entity.payer)

    return "\n".join(lines)


def generate_dataset(seed: int = SEED, total: int = TOTAL_DENIALS):
    rng = random.Random(seed)

    # Even-ish spread across the 6 categories (14 denials -> mostly 2-3 per
    # category, matching the MEC dataset's even-distribution approach).
    categories: list[str] = []
    per_category = total // len(CATEGORY_ORDER)
    remainder = total - per_category * len(CATEGORY_ORDER)
    for i, cat in enumerate(CATEGORY_ORDER):
        count = per_category + (1 if i < remainder else 0)
        categories.extend([cat] * count)
    rng.shuffle(categories)

    denials = []
    for i, category in enumerate(categories, start=1):
        entity = build_entity(i, category, rng)
        letter_text = compose_letter(entity, rng)
        denial_id = f"RM-{i:03d}"
        denials.append(
            {
                "synthetic_id": denial_id,
                "source_company": SOURCE_COMPANY,
                "raw_text": letter_text,
                "payer": entity.payer,
                "claim_ref": entity.claim_ref,
                "received_at": entity.received_at.isoformat(),
                "status": "new",
                "ground_truth": {
                    "category": entity.category,
                    "carc_code": entity.carc_code,
                    "carc_description": entity.carc_desc,
                    "rarc_code": entity.rarc_code,
                    "rarc_description": entity.rarc_desc,
                    "patient_ref": entity.patient_ref,
                    "physician_name": entity.physician_name,
                    "physician_npi": entity.physician_npi,
                    "hcpcs_code": entity.hcpcs,
                    "hcpcs_description": entity.hcpcs_desc,
                    "equipment_type": entity.equipment_type,
                    "icd10_code": entity.icd10,
                    "icd10_description": entity.icd10_desc,
                    "date_of_service": entity.dos.isoformat(),
                    "billed_amount": entity.amount,
                    "auth_number": entity.auth_number,
                    "lmn_reference_number": entity.lmn_reference,
                    "style": entity.style,
                },
            }
        )

    return denials


def main():
    denials = generate_dataset()

    denials_path = OUTPUT_DIR / "denials_summit_dme_providers.json"
    denials_path.write_text(json.dumps(denials, indent=2, default=str))

    category_counts: dict[str, int] = {}
    equipment_counts: dict[str, int] = {}
    for d in denials:
        cat = d["ground_truth"]["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
        eq = d["ground_truth"]["equipment_type"]
        equipment_counts[eq] = equipment_counts.get(eq, 0) + 1

    print(f"Wrote {len(denials)} denials to {denials_path}")
    print("Category distribution:")
    for cat, count in sorted(category_counts.items()):
        print(f"  {cat}: {count}")
    print("Equipment-type distribution:")
    for eq, count in sorted(equipment_counts.items()):
        print(f"  {eq}: {count}")


if __name__ == "__main__":
    main()
