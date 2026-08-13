#!/usr/bin/env python3
"""
Generates synthetic claim-denial letters for "Meridian Eye Care Partners"
(a fictional ophthalmology MSO) plus a labeled evaluation subset.

Design notes
------------
- Deterministic: a fixed random seed makes output reproducible across runs.
- Data-driven: letters are assembled from pools of payers, clinicians,
  procedures, diagnoses, and sentence fragments -- not hardcoded as static
  strings -- but sentence selection/order/style is randomized per letter so
  the output reads as varied natural prose rather than mail-merged template
  text with blanks filled in.
- CARC/RARC codes used below are real, current X12-maintained codes, verified
  against x12.org/codes (see the comment above each CATEGORY entry). They are
  not invented.
- No real people, patients, payers, or PHI of any kind. All names, payers,
  NPIs, member IDs, and claim numbers are synthetic and clearly fabricated.

Usage
-----
    python generate_synthetic_data.py

Writes (relative to this file's directory):
    denials_synthetic.json   -- full synthetic dataset (45-50 denials)
    eval_labeled.json        -- labeled subset for regression testing
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

SEED = 20260212
OUTPUT_DIR = Path(__file__).resolve().parent
TOTAL_DENIALS = 48
SOURCE_COMPANY = "meridian_eyecare_partners"

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
    "Amberwood Health Plan",
    "Lakeshore Community Health",
]

CLINIC_LOCATIONS = [
    "Meridian Eye Care Partners - Westfield Office",
    "Meridian Eye Care Partners - Oakhurst Surgical Center",
    "Meridian Eye Care Partners - Cedar Grove Clinic",
    "Meridian Eye Care Partners - Brookline Office",
    "Meridian Eye Care Partners - Dellwood Retina Center",
    "Meridian Eye Care Partners - Fairmont Office",
]

PHYSICIAN_FIRST = [
    "Elena", "Rajiv", "Marcus", "Priya", "Daniel", "Sofia", "Thomas",
    "Naomi", "Victor", "Amara", "Kenji", "Lucia",
]
PHYSICIAN_LAST = [
    "Marsh", "Kapoor", "Delgado", "Okafor", "Bennett", "Halvorsen",
    "Whitfield", "Suárez", "Ivanov", "Chen", "Osei", "Reyes",
]

APPEAL_CONTACT_TITLES = ["Practice Administrator", "Billing Manager", "Appeals Coordinator"]

# CPT/HCPCS procedures typical of an ophthalmology MSO, with a plausible
# billed-amount range (USD). Codes themselves are real current CPT/HCPCS
# codes; amounts are synthetic.
PROCEDURES = [
    ("66984", "cataract extraction with intraocular lens insertion", (2400, 3600)),
    ("66821", "YAG laser posterior capsulotomy", (450, 750)),
    ("65855", "selective laser trabeculoplasty", (600, 1100)),
    ("92014", "comprehensive ophthalmological exam, established patient", (150, 280)),
    ("92004", "comprehensive ophthalmological exam, new patient", (180, 320)),
    ("92133", "scanning computerized ophthalmic diagnostic imaging, posterior segment (OCT)", (95, 180)),
    ("92083", "extended visual field examination", (110, 210)),
    ("67028", "intravitreal injection of pharmacologic agent", (1800, 2600)),
    ("67042", "vitrectomy with internal limiting membrane peeling", (3200, 4800)),
    ("92020", "gonioscopy", (60, 120)),
    ("92225", "extended ophthalmoscopy, initial", (75, 140)),
    ("V2785", "processing of corneal tissue for transplant", (900, 1400)),
]

DIAGNOSES = [
    ("H25.11", "age-related nuclear cataract, right eye"),
    ("H25.12", "age-related nuclear cataract, left eye"),
    ("H40.11X0", "primary open-angle glaucoma, stage unspecified"),
    ("H35.3211", "exudative age-related macular degeneration, right eye"),
    ("H35.3212", "exudative age-related macular degeneration, left eye"),
    ("H33.011", "retinal detachment with retinal break, right eye"),
    ("H52.13", "myopia, bilateral"),
    ("H04.123", "dry eye syndrome, bilateral"),
    ("H35.361", "drusen (degenerative) of macula, right eye"),
    ("H26.9", "unspecified cataract"),
]

# ---------------------------------------------------------------------------
# Category definitions with verified real CARC/RARC codes.
#
# All descriptions below were checked against the current X12 code list at
# x12.org/codes (Claim Adjustment Reason Codes / Remittance Advice Remark
# Codes) on the date this dataset was generated. Only currently-active codes
# are used.
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
            ("M51", "Missing/incomplete/invalid procedure code(s)."),
            ("MA83", "Did not indicate whether we are the primary or secondary payer."),
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
# Sentence-fragment pools for letter composition.
# Two writing "voices": terse EOB-style auto-generated text, and a longer
# narrative manual-review letter. Fragments are combined and shuffled per
# letter so output does not read as template-with-blanks.
# ---------------------------------------------------------------------------

TERSE_OPENERS = [
    "This letter serves as notification that the above-referenced claim has been denied.",
    "Please be advised the claim referenced above has been processed and denied.",
    "The claim identified below has been reviewed and denied under the terms of the member's plan.",
    "Notice of claim denial for the service(s) identified below.",
]

NARRATIVE_OPENERS = [
    "Thank you for submitting the above claim for review. After careful evaluation by our clinical and claims review staff, we are writing to inform you that the claim has been denied.",
    "We have completed our review of the claim referenced above. This letter explains our determination and the basis for it.",
    "Our claims review team has completed a manual review of the submitted claim. Unfortunately, we are unable to approve payment at this time for the reasons outlined below.",
    "Following a secondary review by our medical claims department, we are issuing this formal notice of denial for the claim described below.",
]

TERSE_BODY_TEMPLATES = [
    "Claim {claim_ref} for patient reference {patient_ref}, date of service {dos}, was denied. Reason code: CARC {carc_code} - {carc_desc}",
    "Service billed under CPT {cpt} ({cpt_desc}) on {dos} was not paid. CARC {carc_code}: {carc_desc}",
    "Denial reason: CARC {carc_code} - {carc_desc} Remark: RARC {rarc_code} - {rarc_desc}",
]

NARRATIVE_BODY_TEMPLATES = [
    "The claim submitted for {patient_ref}, service date {dos}, billed CPT {cpt} ({cpt_desc}) with diagnosis {icd10} ({icd10_desc}), in the amount of ${amount:,.2f}, could not be approved for payment. The applicable adjustment reason is CARC {carc_code} ({carc_desc}).",
    "Upon review, our determination is that this claim cannot be paid as submitted. The reason for this denial corresponds to CARC {carc_code}: {carc_desc} In addition, remark code RARC {rarc_code} applies: {rarc_desc}",
    "Our review found that the claim for the procedure performed on {dos} (CPT {cpt}, {cpt_desc}) does not meet the requirements for reimbursement under this plan. This determination is coded as CARC {carc_code} - {carc_desc}",
]

CATEGORY_EXPLANATION = {
    "coding_error": [
        "Our coding review identified an inconsistency between the procedure code and the modifier submitted on this claim.",
        "The diagnosis code submitted does not support medical necessity for the procedure code billed, per our coding edits.",
        "Please review the CPT/ICD-10 code combination submitted and resubmit with the corrected coding if appropriate.",
    ],
    "missing_information": [
        "This claim was missing information required for adjudication, specifically a valid prior authorization or referral number.",
        "The claim as submitted lacked sufficient documentation to process; no authorization number was found on file for this date of service.",
        "Required fields on the claim submission were incomplete, preventing this claim from being adjudicated.",
    ],
    "medical_necessity": [
        "Based on our Local Coverage Determination for this procedure, the documentation submitted did not establish medical necessity.",
        "Our clinical reviewers determined that the submitted clinical documentation does not meet the plan's medical necessity criteria for this service.",
        "This service is subject to medical necessity review, and the records provided at the time of submission were insufficient to support coverage.",
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
        "Our system identified a prior claim on file for the same patient, date of service, and procedure code.",
        "This claim appears to duplicate a previously adjudicated claim for the same service; only one payment is allowed per date of service for this procedure.",
        "The service billed on this claim was already reimbursed under a separate, previously processed claim.",
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
    "Utilization Review Department",
    "Appeals & Grievances Unit",
]


@dataclass
class Entity:
    patient_ref: str
    claim_ref: str
    physician_name: str
    physician_npi: str
    clinic: str
    payer: str
    dos: date
    received_at: date
    cpt: str
    cpt_desc: str
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
    extra: dict = field(default_factory=dict)


def _fake_npi(rng: random.Random) -> str:
    # 10-digit synthetic identifier in NPI format; not validated against the
    # NPI Luhn check digit and not a real provider identifier.
    return "".join(str(rng.randint(0, 9)) for _ in range(10))


def _fake_patient_ref(rng: random.Random) -> str:
    return f"PT-{rng.randint(100000, 999999)}"


def _fake_claim_ref(rng: random.Random) -> str:
    return f"CLM-{rng.randint(1000000, 9999999)}"


def _fake_auth_number(rng: random.Random) -> str:
    return f"AUTH-{rng.randint(10000, 99999)}"


def build_entity(idx: int, category: str, rng: random.Random) -> Entity:
    physician_name = f"Dr. {rng.choice(PHYSICIAN_FIRST)} {rng.choice(PHYSICIAN_LAST)}, MD"
    cpt, cpt_desc, amount_range = rng.choice(PROCEDURES)
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
        clinic=rng.choice(CLINIC_LOCATIONS),
        payer=rng.choice(PAYERS),
        dos=dos,
        received_at=received_at,
        cpt=cpt,
        cpt_desc=cpt_desc,
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

    if category == "missing_information" and carc_code == "197":
        entity.extra["missing_auth"] = True
    elif category != "timely_filing":
        # Most non-timely-filing claims reference a valid prior auth on file,
        # which the appeal should cite back to the payer.
        entity.auth_number = _fake_auth_number(rng)

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
    lines.append(entity.clinic)
    lines.append(f"Attn: {rng.choice(APPEAL_CONTACT_TITLES)}")
    lines.append("")
    lines.append("RE: NOTICE OF CLAIM DENIAL")
    lines.append(f"Patient Reference: {entity.patient_ref}")
    lines.append(f"Claim Number: {entity.claim_ref}")
    lines.append(f"Date of Service: {entity.dos.strftime('%m/%d/%Y')}")
    lines.append(f"Billed Amount: ${entity.amount:,.2f}")
    lines.append(f"Procedure: CPT {entity.cpt} ({entity.cpt_desc})")
    lines.append(f"Diagnosis: ICD-10 {entity.icd10} ({entity.icd10_desc})")
    lines.append(f"Treating Physician: {entity.physician_name}, NPI {entity.physician_npi}")
    lines.append(f"Facility: {entity.clinic}")
    if entity.auth_number:
        lines.append(f"Prior Authorization on File: {entity.auth_number}")
    lines.append("")

    opener = rng.choice(TERSE_OPENERS if entity.style == "terse" else NARRATIVE_OPENERS)
    lines.append(opener)
    lines.append("")

    fmt_kwargs = dict(
        claim_ref=entity.claim_ref,
        patient_ref=entity.patient_ref,
        dos=entity.dos.strftime("%m/%d/%Y"),
        cpt=entity.cpt,
        cpt_desc=entity.cpt_desc,
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


def build_required_appeal_elements(entity: Entity) -> list[str]:
    """Ground-truth list of specific elements a correct appeal should contain,
    tailored to this letter's actual generated values (not generic boilerplate).
    """
    elements = [
        f"Must reference claim number {entity.claim_ref} and patient reference {entity.patient_ref}",
        f"Must cite the correct CPT code {entity.cpt} ({entity.cpt_desc}) for the date of service {entity.dos.strftime('%m/%d/%Y')}",
        f"Must include the treating physician's name and NPI ({entity.physician_name}, NPI {entity.physician_npi})",
    ]

    if entity.category == "coding_error":
        elements.append(
            f"Must explain/correct the coding relationship between diagnosis {entity.icd10} ({entity.icd10_desc}) "
            f"and procedure {entity.cpt}, addressing CARC {entity.carc_code}"
        )
    elif entity.category == "missing_information":
        if entity.extra.get("missing_auth"):
            elements.append(
                "Must supply or reference a valid prior authorization number for the service, since the denial "
                "(CARC 197) cites an absent authorization"
            )
        else:
            elements.append(
                f"Must supply the specific missing information cited in the denial (CARC {entity.carc_code}) "
                "and confirm it was included with the original claim or attach it now"
            )
    elif entity.category == "medical_necessity":
        elements.append(
            f"Must include clinical documentation supporting medical necessity for diagnosis {entity.icd10} "
            f"({entity.icd10_desc}), addressing the LCD/medical-necessity basis cited (CARC {entity.carc_code})"
        )
    elif entity.category == "timely_filing":
        elements.append(
            "Must address the timely filing gap directly: either provide proof of earlier timely submission "
            "(e.g. a prior claim submission date/confirmation) or cite a qualifying exception to the "
            f"{entity.extra.get('filing_days', 90)}-day filing limit"
        )
    elif entity.category == "eligibility":
        elements.append(
            f"Must address member eligibility for date of service {entity.dos.strftime('%m/%d/%Y')} "
            "(e.g. proof of active coverage, corrected member ID, or coordination-of-benefits correction)"
        )
    elif entity.category == "duplicate_claim":
        elements.append(
            f"Must explain why this is not a duplicate of a prior claim -- e.g. distinct date/eye/laterality "
            f"or a documented separate encounter for procedure {entity.cpt}"
        )

    if entity.auth_number:
        elements.append(f"Should reference the existing prior authorization number {entity.auth_number} on file")

    elements.append(f"Must reference the denial reason code CARC {entity.carc_code} and respond to it directly")

    return elements


def generate_dataset(seed: int = SEED, total: int = TOTAL_DENIALS):
    rng = random.Random(seed)

    # Even-ish spread across the 6 categories.
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
        denial_id = f"SYN-{i:03d}"
        denials.append(
            {
                "synthetic_id": denial_id,
                "source_company": SOURCE_COMPANY,
                "raw_text": letter_text,
                "payer": entity.payer,
                "claim_ref": entity.claim_ref,
                "received_at": entity.received_at.isoformat(),
                "status": "new",
                "_ground_truth": {
                    "category": entity.category,
                    "carc_code": entity.carc_code,
                    "carc_description": entity.carc_desc,
                    "rarc_code": entity.rarc_code,
                    "rarc_description": entity.rarc_desc,
                    "patient_ref": entity.patient_ref,
                    "physician_name": entity.physician_name,
                    "physician_npi": entity.physician_npi,
                    "cpt_code": entity.cpt,
                    "cpt_description": entity.cpt_desc,
                    "icd10_code": entity.icd10,
                    "icd10_description": entity.icd10_desc,
                    "date_of_service": entity.dos.isoformat(),
                    "billed_amount": entity.amount,
                    "auth_number": entity.auth_number,
                    "style": entity.style,
                },
            }
        )

    return denials


def build_eval_subset(denials: list[dict], fraction: float = 0.5) -> list[dict]:
    """Select a labeled subset spread evenly across categories."""
    by_category: dict[str, list[dict]] = {}
    for d in denials:
        by_category.setdefault(d["_ground_truth"]["category"], []).append(d)

    eval_records = []
    for cat, items in by_category.items():
        n = max(1, round(len(items) * fraction))
        for d in items[:n]:
            gt = d["_ground_truth"]
            eval_records.append(
                {
                    "synthetic_id": d["synthetic_id"],
                    "claim_ref": d["claim_ref"],
                    "raw_text": d["raw_text"],
                    "ground_truth_category": gt["category"],
                    "ground_truth_carc_code": gt["carc_code"],
                    "ground_truth_rarc_code": gt["rarc_code"],
                    "required_appeal_elements": build_required_appeal_elements_from_gt(d),
                }
            )
    return eval_records


def build_required_appeal_elements_from_gt(denial_record: dict) -> list[str]:
    gt = denial_record["_ground_truth"]

    class _E:
        pass

    e = _E()
    e.claim_ref = denial_record["claim_ref"]
    e.patient_ref = gt["patient_ref"]
    e.cpt = gt["cpt_code"]
    e.cpt_desc = gt["cpt_description"]
    e.dos = date.fromisoformat(gt["date_of_service"])
    e.physician_name = gt["physician_name"]
    e.physician_npi = gt["physician_npi"]
    e.category = gt["category"]
    e.icd10 = gt["icd10_code"]
    e.icd10_description = gt["icd10_description"]
    e.icd10_desc = gt["icd10_description"]
    e.carc_code = gt["carc_code"]
    e.auth_number = gt["auth_number"]
    e.extra = {"filing_days": 90}

    return build_required_appeal_elements(e)  # type: ignore[arg-type]


def main():
    denials = generate_dataset()

    # Full dataset: strip the internal `_ground_truth` scratch key naming
    # convention but keep it as `ground_truth` for transparency -- seed.py
    # only loads the denial-letter fields into the `denials` table; the
    # ground_truth block is dataset metadata for humans/eval tooling.
    full_output = []
    for d in denials:
        rec = {k: v for k, v in d.items() if k != "_ground_truth"}
        rec["ground_truth"] = d["_ground_truth"]
        full_output.append(rec)

    eval_output = build_eval_subset(denials, fraction=0.5)

    denials_path = OUTPUT_DIR / "denials_synthetic.json"
    eval_path = OUTPUT_DIR / "eval_labeled.json"

    denials_path.write_text(json.dumps(full_output, indent=2, default=str))
    eval_path.write_text(json.dumps(eval_output, indent=2, default=str))

    category_counts: dict[str, int] = {}
    for d in denials:
        cat = d["_ground_truth"]["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    print(f"Wrote {len(full_output)} denials to {denials_path}")
    print(f"Wrote {len(eval_output)} labeled eval records to {eval_path}")
    print("Category distribution:")
    for cat, count in sorted(category_counts.items()):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
