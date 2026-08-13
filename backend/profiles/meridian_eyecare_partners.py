"""
CompanyProfile for Meridian Eye Care Partners (eye-care MSO) -- the
original Phase 2 pipeline's company, now expressed as a profile.

All text below is carried over verbatim from the pre-Phase-4
extract.py/classify.py/draft_appeal.py so this profile reproduces the
original pipeline's behavior exactly; the refactor should not change MEC's
outputs.
"""

from __future__ import annotations

from .base import CompanyProfile

EXTRACTION_TOOL = {
    "name": "record_extraction",
    "description": (
        "Record the structured fields extracted from an insurance claim "
        "denial letter. Only include values that are explicitly stated in "
        "the letter -- never infer, guess, or fabricate a value that isn't "
        "present in the text."
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
                "description": "Date of service, normalized to YYYY-MM-DD.",
            },
            "billed_amount": {
                "type": "number",
                "description": "Billed amount in US dollars as a plain number, no currency symbol or commas.",
            },
            "cpt_code": {
                "type": "string",
                "description": "CPT procedure code, digits only (e.g. '67028').",
            },
            "cpt_description": {
                "type": "string",
                "description": "The procedure description accompanying the CPT code, if the letter states one.",
            },
            "diagnosis_code": {
                "type": "string",
                "description": "ICD-10 diagnosis code exactly as written (e.g. 'H35.3212').",
            },
            "diagnosis_description": {
                "type": "string",
                "description": "The diagnosis description accompanying the ICD-10 code, if the letter states one.",
            },
            "physician_name": {
                "type": "string",
                "description": "Treating physician's name including credentials (e.g. 'Dr. Amara Delgado, MD').",
            },
            "physician_npi": {
                "type": "string",
                "description": "Treating physician's NPI number, digits only.",
            },
            "payer_name": {
                "type": "string",
                "description": "Name of the insurance payer that issued the denial letter.",
            },
            "carc_code": {
                "type": "string",
                "description": "Claim Adjustment Reason Code number, digits only (e.g. '29').",
            },
            "carc_description": {
                "type": "string",
                "description": "The CARC's description text as stated in the letter, if given.",
            },
            "rarc_code": {
                "type": "string",
                "description": (
                    "Remittance Advice Remark Code, if one is cited in the letter "
                    "(e.g. 'N211'). Omit this property entirely if no RARC is present."
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
        },
        "required": [
            "patient_ref",
            "claim_ref",
            "date_of_service",
            "billed_amount",
            "cpt_code",
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
    "You are a meticulous medical billing/coding assistant for Meridian "
    "Eye Care Partners, an eye-care multi-specialty organization (MSO). You "
    "extract structured data from insurance claim denial letters with zero "
    "tolerance for fabrication: every field you report must be traceable to "
    "an exact phrase in the letter. If a field genuinely is not present in "
    "the letter, leave it out of your tool call rather than guessing at it."
)

CLASSIFICATION_SYSTEM_PROMPT_INTRO = (
    "You are a claims-appeals specialist for Meridian Eye Care Partners, "
    "an eye-care MSO. Given a denial letter and the fields already extracted "
    "from it, classify the denial's root cause into exactly one of the "
    "following categories, and give a calibrated confidence score -- low "
    "confidence is a correct and useful answer when the letter is genuinely "
    "ambiguous; it is not something to avoid."
)

# Brief category definitions plus representative CARC codes, so the model
# has more to go on than the bare category names -- these are not exhaustive
# CARC lists, just enough to disambiguate the six categories from each other.
CATEGORY_GUIDE = """
- coding_error: a billing/coding problem with the claim as submitted --
  invalid, mutually exclusive, unbundled, or mismatched CPT/HCPCS/ICD-10
  code, missing or incorrect modifier. Typical CARCs: 4, 11, 16 (when paired
  with a coding-specific RARC), 97, 234.
- missing_information: the payer needs additional information or
  documentation to adjudicate the claim -- missing records, missing referral,
  incomplete claim data. Typical CARCs: 16 (paired with an informational
  RARC requesting documentation), 252.
- medical_necessity: the payer determined the service was not medically
  necessary, or lacks clinical documentation to support necessity. Typical
  CARCs: 50, 149, 167.
- timely_filing: the claim was submitted after the payer's filing deadline.
  Typical CARC: 29.
- eligibility: the patient was not eligible or covered on the date of
  service, or the service is not a covered benefit under the plan. Typical
  CARCs: 26, 27, 31, 96.
- duplicate_claim: the payer identified this claim as a duplicate of one
  already processed. Typical CARC: 18.
""".strip()

APPEAL_GUIDANCE = {
    "coding_error": (
        "Identify the specific coding issue the denial cites, state the "
        "correct code/modifier/combination and why it applies to the "
        "documented procedure and diagnosis, and request the claim be "
        "reprocessed under the corrected coding."
    ),
    "missing_information": (
        "State plainly that the requested information/documentation is "
        "being provided with this appeal (referencing what it is, based on "
        "the extracted fields), and request reprocessing once it is on "
        "file."
    ),
    "medical_necessity": (
        "Provide a substantive clinical justification for medical "
        "necessity: cite the diagnosis, why the procedure is the "
        "appropriate standard of care for that diagnosis, and any relevant "
        "clinical context implied by the letter. Request reconsideration on "
        "medical-necessity grounds."
    ),
    "timely_filing": (
        "Address the timely-filing gap directly. If the letter or extracted "
        "fields suggest a qualifying exception (e.g. evidence the original "
        "claim was submitted on time, or a payer-caused delay), assert it "
        "explicitly. Otherwise request a good-cause exception and state "
        "what supporting evidence of timely original submission is being "
        "provided."
    ),
    "eligibility": (
        "Assert that the patient was eligible/covered on the date of "
        "service (or explain why the service is a covered benefit under "
        "the plan), referencing the date of service and patient reference. "
        "If a prior authorization number was extracted, cite it as evidence "
        "the service was pre-approved. Request reconsideration."
    ),
    "duplicate_claim": (
        "Explain concretely why this claim is not a duplicate -- e.g. a "
        "distinct date of service, procedure, or laterality from any prior "
        "claim -- and request the claim be reprocessed as a unique, "
        "non-duplicate submission."
    ),
}

APPEAL_SYSTEM_PROMPT_TEMPLATE = (
    "You are drafting a formal written appeal on behalf of Meridian "
    "Eye Care Partners, an eye-care MSO, appealing an insurance claim denial. "
    "You will be given the denial letter, the structured fields already "
    "extracted from it, and the classified denial category with the "
    "reasoning behind it.\n\n"
    "Write a complete, ready-to-send professional appeal letter. Hard "
    "requirements:\n"
    "- Reference the specific facts of THIS claim by name: the claim "
    "number, patient reference, date of service, CPT code (with its "
    "description), and the treating physician's name and NPI. Cite the "
    "prior authorization number too if one was extracted and it is "
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
    "body, and a signature block for Meridian Eye Care Partners' "
    "billing/appeals department.\n"
    "- Output ONLY the letter text -- no preamble, no commentary, no "
    "markdown formatting.\n"
    "- Compute any date silently before writing it. Never show your work, "
    "hesitation, or self-corrections in the letter body (e.g. never write "
    "something like 'wait, let me use the correct date' or similar "
    "mid-sentence reasoning) -- the letter must read as a final, "
    "already-proofread document from the first character."
)

PROFILE = CompanyProfile(
    key="meridian_eyecare_partners",
    display_name="Meridian Eye Care Partners",
    extraction_tool=EXTRACTION_TOOL,
    extraction_system_prompt=EXTRACTION_SYSTEM_PROMPT,
    classification_system_prompt_intro=CLASSIFICATION_SYSTEM_PROMPT_INTRO,
    category_guide=CATEGORY_GUIDE,
    appeal_guidance=APPEAL_GUIDANCE,
    appeal_system_prompt_template=APPEAL_SYSTEM_PROMPT_TEMPLATE,
)
