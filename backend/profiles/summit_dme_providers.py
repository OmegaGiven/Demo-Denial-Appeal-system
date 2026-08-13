"""
CompanyProfile for Summit DME Providers -- a fictional national complex rehab
technology (CRT) / durable medical equipment (DME) provider. This is the
second client company added in Phase 4, to prove the pipeline built for
Meridian Eye Care Partners generalizes rather than being eye-care-only.

What genuinely differs from the MEC profile, and why:
  - Extraction schema: DME claims are billed under HCPCS Level II codes
    (not CPT), so `hcpcs_code`/`hcpcs_description` replace `cpt_code`/
    `cpt_description`. Two fields are DME-specific and have no MEC
    equivalent:
      - `equipment_type` -- what class of equipment the claim is for (e.g.
        "power wheelchair", "CPAP device", "ankle-foot orthosis"). Useful
        both for the model's own reasoning and for downstream reporting.
      - `lmn_reference_number` -- a Letter of Medical Necessity is a real,
        DME-specific document requirement: Medicare and most commercial
        payers require a physician-signed LMN (or a CMS-847-style
        Certificate of Medical Necessity for certain item categories)
        establishing medical necessity for DME/CRT equipment before the
        claim will be paid, which eye-care procedure claims have no
        equivalent of. Optional field (like `prior_auth_number`) -- only
        populated if the letter actually cites one.
  - Category guide (classify.py) and appeal guidance (draft_appeal.py) are
    reframed around DME/CRT specifics: HCPCS Level II codes and DME
    modifiers (NU/RR/UE/KX) instead of CPT modifiers, LMN/CMN
    documentation instead of clinical chart notes, and Medicare DME MAC
    LCDs instead of generic payer LCDs for medical-necessity arguments.
  - The six CLASSIFICATION_CATEGORIES themselves are unchanged from
    MEC -- they are genuine root-cause buckets for any healthcare claim
    denial, not eye-care-specific, so there was nothing to invent there.

CARC codes below are the same real, X12-maintained codes used in the MEC
profile (verified against x12.org/codes -- see the WebFetch verification
in this phase's work) -- CARCs are generic across specialties, not
eye-care- or DME-specific, so reusing the verified numbers is correct, not
lazy. Only the *typical* set per category and the RARC pairings are
adjusted where DME claims genuinely differ (e.g. CARC 197
precertification-absent is far more common for DME than for routine
eye-care office visits, since Medicare requires prior authorization for
certain power mobility devices and other DME categories).
"""

from __future__ import annotations

from .base import CompanyProfile

EXTRACTION_TOOL = {
    "name": "record_extraction",
    "description": (
        "Record the structured fields extracted from an insurance claim "
        "denial letter for a durable medical equipment (DME) / complex "
        "rehab technology (CRT) claim. Only include values that are "
        "explicitly stated in the letter -- never infer, guess, or "
        "fabricate a value that isn't present in the text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "patient_ref": {
                "type": "string",
                "description": "Patient reference/ID as stated in the letter (e.g. 'PT-107231').",
            },
            "claim_ref": {
                "type": "string",
                "description": "The payer's claim number for this denial (e.g. 'CLM-6123212').",
            },
            "date_of_service": {
                "type": "string",
                "description": "Date of service (equipment delivery/dispense date), normalized to YYYY-MM-DD.",
            },
            "billed_amount": {
                "type": "number",
                "description": "Billed amount in US dollars as a plain number, no currency symbol or commas.",
            },
            "hcpcs_code": {
                "type": "string",
                "description": "HCPCS Level II code for the equipment/item billed, exactly as written (e.g. 'K0862', 'E0601').",
            },
            "hcpcs_description": {
                "type": "string",
                "description": "The equipment/item description accompanying the HCPCS code, if the letter states one.",
            },
            "equipment_type": {
                "type": "string",
                "description": (
                    "Plain-language equipment category this claim is for, e.g. "
                    "'power wheelchair', 'CPAP device', 'ankle-foot orthosis', "
                    "'hospital bed'. Derive from the letter's own description of "
                    "the item, not from the HCPCS code alone."
                ),
            },
            "diagnosis_code": {
                "type": "string",
                "description": "ICD-10 diagnosis code exactly as written (e.g. 'M62.81').",
            },
            "diagnosis_description": {
                "type": "string",
                "description": "The diagnosis description accompanying the ICD-10 code, if the letter states one.",
            },
            "physician_name": {
                "type": "string",
                "description": "Prescribing/ordering physician's name including credentials (e.g. 'Dr. Amara Delgado, MD').",
            },
            "physician_npi": {
                "type": "string",
                "description": "Prescribing physician's NPI number, digits only.",
            },
            "payer_name": {
                "type": "string",
                "description": "Name of the insurance payer that issued the denial letter.",
            },
            "carc_code": {
                "type": "string",
                "description": "Claim Adjustment Reason Code number, digits only (e.g. '197').",
            },
            "carc_description": {
                "type": "string",
                "description": "The CARC's description text as stated in the letter, if given.",
            },
            "rarc_code": {
                "type": "string",
                "description": (
                    "Remittance Advice Remark Code, if one is cited in the letter "
                    "(e.g. 'N30'). Omit this property entirely if no RARC is present."
                ),
            },
            "rarc_description": {
                "type": "string",
                "description": "The RARC's description text, if given. Omit if there is no RARC.",
            },
            "prior_auth_number": {
                "type": "string",
                "description": (
                    "Prior authorization number, ONLY if the letter references one. "
                    "Omit this property entirely if no prior authorization is mentioned."
                ),
            },
            "lmn_reference_number": {
                "type": "string",
                "description": (
                    "Letter of Medical Necessity (LMN) or Certificate of Medical "
                    "Necessity (CMN) reference/tracking number, ONLY if the letter "
                    "references one on file. Omit this property entirely if no "
                    "LMN/CMN is mentioned."
                ),
            },
        },
        "required": [
            "patient_ref",
            "claim_ref",
            "date_of_service",
            "billed_amount",
            "hcpcs_code",
            "equipment_type",
            "diagnosis_code",
            "physician_name",
            "physician_npi",
            "payer_name",
            "carc_code",
        ],
        "additionalProperties": False,
    },
}

EXTRACTION_SYSTEM_PROMPT = (
    "You are a meticulous DME/CRT billing and reimbursement assistant for "
    "Summit DME Providers, a national complex rehab technology (CRT) and "
    "durable medical equipment (DME) provider (wheelchairs and mobility "
    "equipment, respiratory equipment, orthotics/prosthetics, hospital "
    "beds, and related items). You extract structured data from insurance "
    "claim denial letters with zero tolerance for fabrication: every field "
    "you report must be traceable to an exact phrase in the letter. If a "
    "field genuinely is not present in the letter, leave it out of your "
    "tool call rather than guessing at it."
)

CLASSIFICATION_SYSTEM_PROMPT_INTRO = (
    "You are a claims-appeals specialist for Summit DME Providers, a national "
    "complex rehab technology (CRT) and durable medical equipment (DME) "
    "provider. Given a denial letter and the fields already extracted from "
    "it, classify the denial's root cause into exactly one of the "
    "following categories, and give a calibrated confidence score -- low "
    "confidence is a correct and useful answer when the letter is "
    "genuinely ambiguous; it is not something to avoid."
)

CATEGORY_GUIDE = """
- coding_error: a billing/coding problem with the claim as submitted --
  invalid HCPCS code, missing or incorrect DME modifier (e.g. NU for new
  equipment, RR for rental, UE for used, KX for documentation-on-file
  attestation), or mismatched HCPCS/ICD-10 combination. Typical CARCs: 4,
  11, 16 (when paired with a coding-specific RARC), 97, 234.
- missing_information: the payer needs additional information or
  documentation to adjudicate the claim -- most commonly a missing Letter
  of Medical Necessity (LMN) or Certificate of Medical Necessity (CMN),
  missing physician order/prescription, or incomplete claim data. Typical
  CARCs: 16 (paired with an informational RARC requesting documentation),
  197 (precertification/authorization absent -- common for DME since many
  payers, including Medicare, require prior authorization for certain
  power mobility devices and other equipment categories), 252.
- medical_necessity: the payer determined the equipment was not medically
  necessary, or the LMN/clinical documentation on file does not support the
  level of equipment billed (e.g. a power wheelchair denied where the
  documentation only supports a manual wheelchair or cane). Typical CARCs:
  50, 149, 167.
- timely_filing: the claim was submitted after the payer's filing deadline.
  Typical CARC: 29.
- eligibility: the patient was not eligible or covered on the date of
  service, or the equipment/item is not a covered benefit under the plan.
  Typical CARCs: 26, 27, 31, 96.
- duplicate_claim: the payer identified this claim as a duplicate of one
  already processed -- e.g. billed twice for the same equipment delivery,
  or billed as a purchase after an identical rental claim, rather than a
  distinct replacement/repair/upgrade. Typical CARC: 18.
""".strip()

APPEAL_GUIDANCE = {
    "coding_error": (
        "Identify the specific coding issue the denial cites, state the "
        "correct HCPCS code/modifier/combination (e.g. the correct "
        "new-vs-rental-vs-used modifier, or KX attestation) and why it "
        "applies to the documented equipment and diagnosis, and request the "
        "claim be reprocessed under the corrected coding."
    ),
    "missing_information": (
        "State plainly that the requested information/documentation is "
        "being provided with this appeal. If the denial or extracted "
        "fields indicate a missing LMN/CMN, explicitly reference the "
        "Letter of Medical Necessity (citing its reference number if one "
        "was extracted, or stating that a completed LMN signed by the "
        "prescribing physician is enclosed) and request reprocessing once "
        "it is on file."
    ),
    "medical_necessity": (
        "Provide a substantive clinical justification for medical "
        "necessity grounded in the patient's diagnosis and functional "
        "limitations: cite the diagnosis, the equipment type, why this "
        "specific equipment (not a lesser alternative) is medically "
        "necessary and consistent with the applicable Medicare DME MAC "
        "Local Coverage Determination (LCD) or the payer's equivalent "
        "coverage criteria, and reference the LMN/physician order "
        "supporting it. Request reconsideration on medical-necessity "
        "grounds."
    ),
    "timely_filing": (
        "Address the timely-filing gap directly. If the letter or "
        "extracted fields suggest a qualifying exception (e.g. evidence "
        "the original claim was submitted on time, or a payer-caused "
        "delay), assert it explicitly. Otherwise request a good-cause "
        "exception and state what supporting evidence of timely original "
        "submission is being provided."
    ),
    "eligibility": (
        "Assert that the patient was eligible/covered on the date of "
        "service (or explain why the equipment is a covered benefit under "
        "the plan), referencing the date of service and patient reference. "
        "If a prior authorization number was extracted, cite it as "
        "evidence the equipment was pre-approved. Request reconsideration."
    ),
    "duplicate_claim": (
        "Explain concretely why this claim is not a duplicate -- e.g. a "
        "distinct date of service, a replacement/repair rather than an "
        "original purchase, or a rental-to-purchase conversion rather than "
        "a second billing for the same equipment -- and request the claim "
        "be reprocessed as a unique, non-duplicate submission."
    ),
}

APPEAL_SYSTEM_PROMPT_TEMPLATE = (
    "You are drafting a formal written appeal on behalf of Summit DME "
    "Providers, a national complex rehab technology (CRT) and durable "
    "medical equipment (DME) provider, appealing an insurance claim "
    "denial. You will be given the denial letter, the structured fields "
    "already extracted from it, and the classified denial category with "
    "the reasoning behind it.\n\n"
    "Write a complete, ready-to-send professional appeal letter. Hard "
    "requirements:\n"
    "- Reference the specific facts of THIS claim by name: the claim "
    "number, patient reference, date of service, HCPCS code (with its "
    "equipment description) and equipment type, and the prescribing "
    "physician's name and NPI. Cite the prior authorization number and/or "
    "LMN/CMN reference number too if either was extracted and it is "
    "relevant to this denial category.\n"
    "- Directly address the stated denial reason (CARC/RARC code and "
    "category) with a substantive counter-argument or corrective action -- "
    "not a generic request for reconsideration.\n"
    "- Category-specific guidance for this denial "
    "({category}): {guidance}\n"
    "- Do not fabricate any fact not present in the extracted fields or the "
    "letter (e.g. do not invent clinical notes, dates, or documentation "
    "that wasn't given to you) -- where the letter is asking you to assert "
    "something you don't have evidence for, phrase it as what is being "
    "submitted/attached rather than inventing the content.\n"
    "- Standard business-letter format: date, addressee (the payer's "
    "appeals department), RE line with claim number and patient reference, "
    "body, and a signature block for Summit DME Providers' billing/appeals "
    "department.\n"
    "- Output ONLY the letter text -- no preamble, no commentary, no "
    "markdown formatting.\n"
    "- Compute any date silently before writing it. Never show your work, "
    "hesitation, or self-corrections in the letter body (e.g. never write "
    "something like 'wait, let me use the correct date' or similar "
    "mid-sentence reasoning) -- the letter must read as a final, "
    "already-proofread document from the first character."
)

PROFILE = CompanyProfile(
    key="summit_dme_providers",
    display_name="Summit DME Providers",
    extraction_tool=EXTRACTION_TOOL,
    extraction_system_prompt=EXTRACTION_SYSTEM_PROMPT,
    classification_system_prompt_intro=CLASSIFICATION_SYSTEM_PROMPT_INTRO,
    category_guide=CATEGORY_GUIDE,
    appeal_guidance=APPEAL_GUIDANCE,
    appeal_system_prompt_template=APPEAL_SYSTEM_PROMPT_TEMPLATE,
)
