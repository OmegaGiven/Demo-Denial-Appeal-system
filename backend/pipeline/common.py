"""
Shared infrastructure for the extraction -> classification -> appeal-drafting
pipeline: the Anthropic client, model/pricing config, a stage-call retry
wrapper, and the token_usage audit-row writer.
"""

from __future__ import annotations

import logging
import os
import random
import time
import uuid
from decimal import Decimal
from typing import Callable, TypeVar

import anthropic
from dotenv import load_dotenv

from db.models import TokenUsage

load_dotenv()

logger = logging.getLogger("pipeline")

# ---------------------------------------------------------------------------
# Model choice
# ---------------------------------------------------------------------------
#
# claude-sonnet-5 for all three stages (extraction, classification, appeal
# drafting).
#
# Why: extraction and classification are forced tool-use calls against a
# fixed schema/enum -- bounded, well-specified tasks, not open-ended
# reasoning. Appeal drafting is a template-shaped professional letter
# grounded entirely in facts the model is handed (extracted fields +
# classification), not free composition. None of the three stages need
# Opus-tier judgment. Sonnet 5 is priced at $3.00 / $15.00 per MTok
# input/output (list; an introductory $2.00 / $10.00 rate is also active
# through 2026-08-31) versus Opus 5's $5.00 / $25.00 -- meaningfully
# cheaper per call for tasks this bounded, which matters at 48 denials x 3
# stages = 144 calls. If a future eval run (Phase 3, against
# eval_labeled.json) shows classification accuracy or appeal quality
# regressing, the fix is a one-line model swap for the affected stage(s)
# below -- nothing else in the pipeline is architected around a specific
# model.
ANTHROPIC_MODEL = "claude-sonnet-5"

PROMPT_VERSION = "v1"

# $ per 1,000,000 tokens, list (non-introductory) pricing as of 2026-08 --
# see platform.claude.com/docs/en/pricing. We cost every call at the stable
# list price rather than any time-limited introductory rate so that
# `estimated_cost_usd` in the token_usage table has a fixed, auditable
# meaning regardless of when the pipeline happens to run.
PRICING_PER_MILLION_TOKENS = {
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "claude-opus-5": {"input": 5.00, "output": 25.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Compute a real $ estimate for a call, in USD, rounded to 6 decimal
    places (matches the token_usage.estimated_cost_usd Numeric(10, 6) column)."""
    rates = PRICING_PER_MILLION_TOKENS[model]
    cost = (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates["output"]
    return Decimal(str(cost)).quantize(Decimal("0.000001"))


_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    """Lazily construct a single shared Anthropic client for the process."""
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Checked the process environment "
                "and backend/.env (loaded via python-dotenv)."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def record_token_usage(
    db,
    *,
    denial_id: uuid.UUID,
    stage: str,
    input_tokens: int,
    output_tokens: int,
    model: str = ANTHROPIC_MODEL,
) -> TokenUsage:
    """Write (but do not commit) a token_usage audit row for one API call."""
    row = TokenUsage(
        denial_id=denial_id,
        stage=stage,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimate_cost_usd(model, input_tokens, output_tokens),
    )
    db.add(row)
    return row


# ---------------------------------------------------------------------------
# Retry-once-on-transient-error wrapper
# ---------------------------------------------------------------------------

# Covers rate limits, network failures, and 5xx/overloaded responses -- the
# Anthropic SDK error classes documented in shared/error-codes.md as
# retryable. Anything else (bad request, auth, permission, not found,
# malformed schema) is a real problem with the request itself and retrying
# it verbatim just spends money for the same failure.
_RETRYABLE_HTTP_EXCEPTIONS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,  # covers every >=500, including 529 overloaded
)

T = TypeVar("T")


class PipelineStageError(Exception):
    """Raised by a stage's own response validation (missing/malformed
    structured output) -- distinct from the SDK's HTTP-level exceptions, but
    handled by the same retry-once wrapper below."""


def call_with_retry(fn: Callable[[], T], *, description: str, max_attempts: int = 2) -> T:
    """
    Call `fn()`, retrying once (max_attempts=2 total tries by default) on:
      - transient Anthropic API errors (rate limit, network, 5xx/overloaded)
      - PipelineStageError raised by the caller's own response validation
        (e.g. the forced tool_use block was missing or a required field
        wasn't populated)

    Backs off briefly with jitter between attempts. Raises PipelineStageError
    wrapping the last failure once the retry budget is exhausted, so callers
    have one exception type to catch regardless of which failure mode fired.

    Note this is an *outer*, stage-level retry. The Anthropic SDK already
    retries connection errors and 429/5xx internally within a single
    `.create()` call (default max_retries=2) -- this wrapper additionally
    covers the response-shape failures a successful HTTP call can still
    produce, which the SDK has no way to know about.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except _RETRYABLE_HTTP_EXCEPTIONS as exc:
            last_exc = exc
            if attempt < max_attempts:
                delay = (1.5 * attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "%s: transient API error on attempt %d/%d (%s); retrying in %.1fs",
                    description, attempt, max_attempts, exc, delay,
                )
                time.sleep(delay)
        except PipelineStageError as exc:
            last_exc = exc
            if attempt < max_attempts:
                logger.warning(
                    "%s: invalid response on attempt %d/%d (%s); retrying",
                    description, attempt, max_attempts, exc,
                )

    assert last_exc is not None
    raise PipelineStageError(
        f"{description} failed after {max_attempts} attempt(s): {last_exc}"
    ) from last_exc
