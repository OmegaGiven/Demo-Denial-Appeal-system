"""
Stage 2: classify a denial into one of the six CLASSIFICATION_CATEGORIES
(db/models.py), with a calibrated confidence score.

Same structured-output approach as extract.py: a forced tool-use call with
`category` constrained to a JSON Schema enum -- Claude cannot return a
category outside the six valid values, so there's no freeform-text
parsing/validation step that could silently accept a typo'd or invented
category.

Phase 4: the six categories, and the CLASSIFICATION_TOOL schema built from
them, stay a single shared definition across every company profile -- they
are genuine root-cause buckets for any healthcare claim denial, not
eye-care- or DME-specific (see profiles/base.py's module docstring). Only
the system prompt (company framing + a profile-specific CARC-code guide)
varies, via `profiles.CompanyProfile.classification_system_prompt()`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from db.models import CLASSIFICATION_CATEGORIES, Classification, Denial
from profiles import CompanyProfile

from .common import (
    ANTHROPIC_MODEL,
    PipelineStageError,
    call_with_retry,
    get_client,
    record_token_usage,
)

CLASSIFICATION_TOOL_NAME = "record_classification"

CLASSIFICATION_TOOL = {
    "name": CLASSIFICATION_TOOL_NAME,
    "description": (
        "Record the root-cause category for this claim denial and a "
        "calibrated confidence score."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": list(CLASSIFICATION_CATEGORIES),
                "description": "The single best-fitting denial-reason category.",
            },
            "confidence": {
                "type": "number",
                "description": (
                    "Calibrated confidence in this category, from 0.0 (little "
                    "more than a guess) to 1.0 (unambiguous, e.g. an exact "
                    "CARC-code match to one category). Do not default to a "
                    "high number -- use the low end when the letter is "
                    "genuinely ambiguous or the CARC code could plausibly fit "
                    "more than one category."
                ),
            },
            "reasoning": {
                "type": "string",
                "description": (
                    "One or two sentences citing the specific CARC/RARC code "
                    "or phrase in the letter that supports this category."
                ),
            },
        },
        "required": ["category", "confidence", "reasoning"],
        "additionalProperties": False,
    },
}


@dataclass
class StageResult:
    success: bool
    data: dict | None
    raw_output: str
    error: str | None
    input_tokens: int
    output_tokens: int


def _build_user_message(denial: Denial, extracted_fields: dict) -> str:
    return (
        f"Extracted fields (from a prior pipeline stage):\n"
        f"{json.dumps(extracted_fields, indent=2)}\n\n"
        f"Full denial letter text:\n---\n{denial.raw_text}\n---\n\n"
        f"Classify this denial using the {CLASSIFICATION_TOOL_NAME} tool."
    )


def _run_once(
    client, denial: Denial, extracted_fields: dict, profile: CompanyProfile
) -> StageResult:
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=512,
        system=profile.classification_system_prompt(),
        tools=[CLASSIFICATION_TOOL],
        tool_choice={"type": "tool", "name": CLASSIFICATION_TOOL_NAME},
        messages=[{"role": "user", "content": _build_user_message(denial, extracted_fields)}],
    )

    raw_output = json.dumps([block.model_dump() for block in response.content], default=str)
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None or tool_block.name != CLASSIFICATION_TOOL_NAME:
        raise PipelineStageError(
            f"expected a '{CLASSIFICATION_TOOL_NAME}' tool_use block, got "
            f"stop_reason={response.stop_reason!r} "
            f"content_types={[b.type for b in response.content]!r}"
        )

    data = tool_block.input
    if data.get("category") not in CLASSIFICATION_CATEGORIES:
        raise PipelineStageError(f"invalid or missing category: {data.get('category')!r}")
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
        raise PipelineStageError(f"invalid or missing confidence: {confidence!r}")
    if not data.get("reasoning"):
        raise PipelineStageError("missing reasoning")

    data["confidence"] = float(confidence)

    return StageResult(
        success=True,
        data=data,
        raw_output=raw_output,
        error=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def classify_denial(
    db, denial: Denial, extracted_fields: dict, profile: CompanyProfile
) -> StageResult:
    """
    Run classification for one denial, given the fields extraction produced.
    Retries once on a transient or malformed-response failure. Writes a
    classifications row on success (classification failures are audited via
    the denial's status transition to needs_review in pipeline.run, since
    the classifications table -- unlike extractions -- has no room for a
    non-category error value in `category`, which is a Postgres enum
    column). Also writes a token_usage row on success. Does not commit.
    """
    client = get_client()
    try:
        result = call_with_retry(
            lambda: _run_once(client, denial, extracted_fields, profile),
            description=f"classify[{denial.id}]",
        )
    except PipelineStageError as exc:
        return StageResult(
            success=False,
            data=None,
            raw_output="",
            error=str(exc),
            input_tokens=0,
            output_tokens=0,
        )

    record_token_usage(
        db,
        denial_id=denial.id,
        stage="classification",
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    db.add(
        Classification(
            denial_id=denial.id,
            category=result.data["category"],
            confidence=result.data["confidence"],
            model_version=ANTHROPIC_MODEL,
        )
    )
    return result
