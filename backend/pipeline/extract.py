"""
Stage 1: structured field extraction from a denial letter's raw_text.

Uses a forced tool-use call (tool_choice pinned to the single extraction
tool) instead of asking Claude for freeform JSON and hoping it parses --
forcing the tool call means the SDK hands back an already-parsed Python dict
(ToolUseBlock.input) instead of a string we'd have to json.loads() and hope
is well-formed. The "verification reflex" this buys: a malformed response
becomes a missing/empty tool_use block or an absent required field, both of
which we check for explicitly and retry on, rather than a JSON parse
exception (or worse, silently-wrong data) buried downstream.

Phase 4: the extraction tool schema and system prompt are no longer
hardcoded here -- they come from a `profiles.CompanyProfile`, resolved by
the caller (pipeline.run) from `denial.source_company`, so this module
drives extraction for any registered company profile identically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from db.models import Denial, Extraction
from profiles import CompanyProfile

from .common import (
    ANTHROPIC_MODEL,
    PROMPT_VERSION,
    PipelineStageError,
    call_with_retry,
    get_client,
    record_token_usage,
)


@dataclass
class StageResult:
    success: bool
    data: dict | None
    raw_output: str
    error: str | None
    input_tokens: int
    output_tokens: int


def _run_once(client, denial: Denial, profile: CompanyProfile) -> StageResult:
    tool_name = profile.extraction_tool_name
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        system=profile.extraction_system_prompt,
        tools=[profile.extraction_tool],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Extract the structured fields from this denial letter using "
                    f"the {tool_name} tool.\n\n---\n\n{denial.raw_text}"
                ),
            }
        ],
    )

    # Full content-block dump, not just text -- for a forced tool call there
    # is typically no text block at all, so this is the genuine "raw model
    # response" for the audit trail.
    raw_output = json.dumps([block.model_dump() for block in response.content], default=str)
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None or tool_block.name != tool_name:
        raise PipelineStageError(
            f"expected a '{tool_name}' tool_use block, got "
            f"stop_reason={response.stop_reason!r} "
            f"content_types={[b.type for b in response.content]!r}"
        )

    data = tool_block.input
    missing = [
        f for f in profile.extraction_required_fields if f not in data or data[f] in (None, "")
    ]
    if missing:
        raise PipelineStageError(f"tool call missing required field(s): {missing}")

    return StageResult(
        success=True,
        data=data,
        raw_output=raw_output,
        error=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def extract_denial(db, denial: Denial, profile: CompanyProfile) -> StageResult:
    """
    Run extraction for one denial: call Claude (retrying once on a transient
    or malformed-response failure), write the extractions audit row --
    success or failure -- and a token_usage row on success, and return the
    result. Does not commit; the caller (pipeline.run) owns the transaction
    boundary so this can be committed together with the denial's status
    update.
    """
    client = get_client()
    try:
        result = call_with_retry(
            lambda: _run_once(client, denial, profile), description=f"extract[{denial.id}]"
        )
    except PipelineStageError as exc:
        # Audit trail for the failure itself: extracted_fields and
        # raw_model_output are both non-nullable, so we record the error in
        # place of data we never got rather than leaving no row at all.
        db.add(
            Extraction(
                denial_id=denial.id,
                extracted_fields={"error": True, "message": str(exc)},
                model_version=ANTHROPIC_MODEL,
                prompt_version=PROMPT_VERSION,
                raw_model_output=str(exc),
            )
        )
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
        stage="extraction",
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    db.add(
        Extraction(
            denial_id=denial.id,
            extracted_fields=result.data,
            model_version=ANTHROPIC_MODEL,
            prompt_version=PROMPT_VERSION,
            raw_model_output=result.raw_output,
        )
    )
    return result
