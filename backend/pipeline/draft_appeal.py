"""
Stage 3: draft an appeal letter for a denial, given its extraction and
classification.

Unlike extract/classify, this stage's output is prose, not structured data,
so it does not use tool-use -- there is no schema to force. What matters
here is that the letter cites the *specific* facts of this claim (claim
ref, patient ref, date of service, procedure/equipment code, physician +
NPI, prior auth number when relevant) rather than reading as a generic
template; the profile's system prompt and per-category guidance are built
around that, and the appeal is rejected (PipelineStageError, retried once)
if it comes back looking templated -- missing the claim ref, or too short
to plausibly address the denial.

Phase 4: the per-category guidance and the system-prompt template are no
longer hardcoded for one company -- they come from the resolved
`profiles.CompanyProfile`, via `profile.appeal_system_prompt(category)`.
The grounding check's required extracted-field keys also come from the
profile (`profile.appeal_grounding_fields`), since which fields are
worth grounding-checking can vary by claim type.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from db.models import Appeal, Denial
from profiles import CompanyProfile

from .common import ANTHROPIC_MODEL, PipelineStageError, call_with_retry, get_client, record_token_usage


@dataclass
class StageResult:
    success: bool
    draft_text: str | None
    error: str | None
    input_tokens: int
    output_tokens: int


def _build_user_message(denial: Denial, extracted_fields: dict, classification: dict) -> str:
    return (
        f"Extracted fields:\n{json.dumps(extracted_fields, indent=2)}\n\n"
        f"Classification: category={classification['category']!r}, "
        f"confidence={classification['confidence']:.2f}\n"
        f"Classification reasoning: {classification['reasoning']}\n\n"
        f"Original denial letter:\n---\n{denial.raw_text}\n---\n\n"
        "Draft the appeal letter now."
    )


def _run_once(
    client,
    denial: Denial,
    extracted_fields: dict,
    classification: dict,
    profile: CompanyProfile,
) -> StageResult:
    category = classification["category"]
    system_prompt = profile.appeal_system_prompt(category)

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=[
            {"role": "user", "content": _build_user_message(denial, extracted_fields, classification)}
        ],
    )

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    text_blocks = [b.text for b in response.content if b.type == "text"]
    draft_text = "\n".join(text_blocks).strip()

    if not draft_text or len(draft_text) < 200:
        raise PipelineStageError(f"appeal draft implausibly short ({len(draft_text)} chars)")

    # Reject drafts that leak model self-correction/meta-commentary into
    # the letter body (observed live: "April 21, 2025 -- wait, let me use
    # the correct date reasoning." landing in the opening line of an
    # otherwise-correct letter). This is unacceptable in a document meant
    # to be sent to a real payer, so it's treated the same as a failed
    # grounding check -- retried once rather than silently shipped.
    lowered = draft_text.lower()
    leak_markers = (
        "wait, let me",
        "wait -- let me",
        "let me reconsider",
        "let me recalculate",
        "let me use the correct",
        "actually, let me",
        "hold on, let me",
        "correct date reasoning",
    )
    found_leak = next((marker for marker in leak_markers if marker in lowered), None)
    if found_leak:
        raise PipelineStageError(
            f"appeal draft contains leaked model reasoning/self-correction text: {found_leak!r}"
        )

    # Cheap grounding check: the drafted letter should cite the claim number
    # we know is correct (from the denial row itself, not the extraction --
    # this also catches an extraction error corrupting the claim ref before
    # it reaches the letter) and whichever extracted fields this profile
    # designates as required grounding anchors (e.g. physician NPI). A
    # generic, ungrounded letter fails this and gets retried once.
    missing_anchors = []
    if denial.claim_ref not in draft_text:
        missing_anchors.append("claim_ref")
    for field_name in profile.appeal_grounding_fields:
        value = extracted_fields.get(field_name)
        if value and str(value) not in draft_text:
            missing_anchors.append(field_name)
    if missing_anchors:
        raise PipelineStageError(
            f"appeal draft is missing required grounding detail(s): {missing_anchors}"
        )

    return StageResult(
        success=True,
        draft_text=draft_text,
        error=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def draft_appeal(
    db, denial: Denial, extracted_fields: dict, classification: dict, profile: CompanyProfile
) -> StageResult:
    """
    Draft an appeal letter for one denial, given its extraction and
    classification. Retries once on a transient error or a draft that fails
    the grounding check. Writes an appeals row on success and a token_usage
    row. Does not commit.
    """
    client = get_client()
    try:
        result = call_with_retry(
            lambda: _run_once(client, denial, extracted_fields, classification, profile),
            description=f"draft_appeal[{denial.id}]",
        )
    except PipelineStageError as exc:
        return StageResult(
            success=False, draft_text=None, error=str(exc), input_tokens=0, output_tokens=0
        )

    record_token_usage(
        db,
        denial_id=denial.id,
        stage="appeal_drafting",
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    db.add(Appeal(denial_id=denial.id, draft_text=result.draft_text, status="draft"))
    return result
