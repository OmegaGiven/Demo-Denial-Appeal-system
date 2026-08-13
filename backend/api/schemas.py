"""Pydantic request/response models for the API.

Kept separate from db/models.py (the SQLAlchemy ORM layer) on purpose --
these describe the wire contract with the frontend, not the DB schema, and
the two are allowed to diverge (e.g. list vs. detail views, computed
booleans like `has_classification`).
"""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Denials
# ---------------------------------------------------------------------------


class DenialListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_company: str
    status: str
    payer: str
    claim_ref: str
    received_at: datetime.datetime
    has_classification: bool
    has_appeal: bool


class DenialListResponse(BaseModel):
    items: list[DenialListItem]
    total: int
    page: int
    page_size: int


class ExtractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    extracted_fields: dict
    model_version: str
    prompt_version: str
    raw_model_output: str
    created_at: datetime.datetime


class ClassificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    confidence: float
    model_version: str
    created_at: datetime.datetime


class AppealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    draft_text: str
    status: str
    reviewer: str | None
    reviewed_at: datetime.datetime | None
    created_at: datetime.datetime


class AuditEventOut(BaseModel):
    """One row of the unified, immutable audit-event log: a human correction
    to an AI-produced field, an appeal approve/reject/sent review decision,
    or a successful AI pipeline action (see `event_type`). All three shapes
    reuse the same field_corrected/old_value/new_value/corrected_by columns:
      - event_type="appeal_review": field_corrected is always "appeal.status",
        old_value/new_value are the previous/new appeal status, corrected_by
        is the reviewer, and appeal_id identifies which Appeal row it was
        about.
      - event_type="ai_action": field_corrected is the pipeline stage key
        ("extraction" | "classification" | "appeal_drafting"), old_value is
        always "", new_value is a short summary of what the AI produced, and
        corrected_by is always the literal string "AI" -- the frontend badges
        these events as system-originated based on that value."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    appeal_id: int | None
    field_corrected: str
    old_value: str
    new_value: str
    corrected_by: str
    corrected_at: datetime.datetime
    notes: str | None


# Back-compat alias -- CorrectionOut used to be the only shape this table produced.
CorrectionOut = AuditEventOut


class DenialDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_company: str
    status: str
    payer: str
    claim_ref: str
    received_at: datetime.datetime
    created_at: datetime.datetime
    raw_text: str
    extraction: ExtractionOut | None
    classification: ClassificationOut | None
    appeal: AppealOut | None
    audit_events: list[AuditEventOut]


class ProcessResponse(BaseModel):
    denial_id: uuid.UUID
    status: str


class DenialCreateRequest(BaseModel):
    """Manual create-a-denial request, e.g. pasting in a real denial letter
    live for a demo. `payer`/`claim_ref` are DB-required columns but
    deliberately optional here (auto-generated placeholders if omitted) so
    the flow is fast to use live -- `status` is not settable; every
    manually-created denial starts at "new" so the existing "Process with
    AI" button on the detail view has something to do."""

    source_company: str = Field(min_length=1, description="Must match a registered CompanyProfile key")
    raw_text: str = Field(min_length=1)
    payer: str | None = None
    claim_ref: str | None = None
    received_at: datetime.datetime | None = None


class AppealStatusUpdateRequest(BaseModel):
    status: str = Field(description="One of: approved, rejected, sent")
    reviewer: str = Field(min_length=1)


class CorrectionCreateRequest(BaseModel):
    field_corrected: str = Field(min_length=1)
    old_value: str
    new_value: str
    corrected_by: str = Field(min_length=1)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Eval
# ---------------------------------------------------------------------------


class EvalRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_at: datetime.datetime
    accuracy_score: float | None
    git_commit: str | None
    details: dict | None


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


class ProfileOut(BaseModel):
    key: str
    display_name: str


class ExtractionFieldOut(BaseModel):
    """One field from a profile's extraction_tool schema, shaped for display
    -- not the raw Anthropic tool-use JSON schema."""

    name: str
    type: str
    description: str
    required: bool


class AppealGuidanceExcerpt(BaseModel):
    """A short, readable excerpt of a profile's per-category appeal
    guidance -- not the full appeal system prompt."""

    category: str
    excerpt: str


class ProfileDetailOut(BaseModel):
    """Full profile detail for the Phase 8 side-by-side company comparison
    (/profiles). `category_taxonomy` is intentionally identical across every
    profile -- it's the shared, non-duplicated part of the pipeline -- while
    `extraction_fields` and `appeal_guidance` are what genuinely differ per
    company."""

    key: str
    display_name: str
    extraction_fields: list[ExtractionFieldOut]
    category_taxonomy: list[str]
    appeal_guidance: list[AppealGuidanceExcerpt]


# ---------------------------------------------------------------------------
# Demo tools (Phase 8) -- explicitly demo-scoped, not a production data-
# management feature. See api/routes/demo.py.
# ---------------------------------------------------------------------------


class DemoResetOut(BaseModel):
    denial_id: uuid.UUID
    source_company: str
    claim_ref: str
    status: str


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------


class UsageByStage(BaseModel):
    stage: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    call_count: int


class UsageByDay(BaseModel):
    day: datetime.date
    total_tokens: int
    estimated_cost_usd: float
    call_count: int


class UsageResponse(BaseModel):
    source_company: str | None
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_estimated_cost_usd: float
    total_calls: int
    by_stage: list[UsageByStage]
    by_day: list[UsageByDay]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class ConfidenceBucket(BaseModel):
    label: str = Field(description="Human-readable bucket range, e.g. '0.70-0.85'")
    min_confidence: float
    max_confidence: float
    count: int


class ConfidenceDistributionResponse(BaseModel):
    source_company: str | None
    total_classified: int = Field(description="Denials with a classification counted (one per denial, most recent)")
    buckets: list[ConfidenceBucket]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    database: str
