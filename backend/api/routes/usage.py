"""Token/cost usage summary, optionally scoped to one source_company."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import cast, func
from sqlalchemy.orm import Session
from sqlalchemy.types import Date

from api.deps import get_db
from api.schemas import UsageByDay, UsageByStage, UsageResponse
from db.models import Denial, TokenUsage

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("", response_model=UsageResponse)
def get_usage(
    source_company: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> UsageResponse:
    base = db.query(TokenUsage)
    if source_company:
        # token_usage.denial_id is nullable (eval-harness calls aren't tied
        # to a denial), so scoping by company requires an inner join --
        # rows with no denial are correctly excluded from a company-scoped
        # view, since they don't belong to any company.
        base = base.join(Denial, Denial.id == TokenUsage.denial_id).filter(
            Denial.source_company == source_company
        )

    totals = base.with_entities(
        func.coalesce(func.sum(TokenUsage.input_tokens), 0),
        func.coalesce(func.sum(TokenUsage.output_tokens), 0),
        func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0),
        func.count(TokenUsage.id),
    ).one()
    total_input, total_output, total_cost, total_calls = totals

    stage_rows = (
        base.with_entities(
            TokenUsage.stage,
            func.coalesce(func.sum(TokenUsage.input_tokens), 0),
            func.coalesce(func.sum(TokenUsage.output_tokens), 0),
            func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0),
            func.count(TokenUsage.id),
        )
        .group_by(TokenUsage.stage)
        .order_by(TokenUsage.stage)
        .all()
    )
    by_stage = [
        UsageByStage(
            stage=stage,
            input_tokens=int(in_tok),
            output_tokens=int(out_tok),
            total_tokens=int(in_tok) + int(out_tok),
            estimated_cost_usd=float(cost),
            call_count=int(count),
        )
        for stage, in_tok, out_tok, cost, count in stage_rows
    ]

    day_col = cast(TokenUsage.created_at, Date)
    day_rows = (
        base.with_entities(
            day_col.label("day"),
            func.coalesce(func.sum(TokenUsage.input_tokens + TokenUsage.output_tokens), 0),
            func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0),
            func.count(TokenUsage.id),
        )
        .group_by(day_col)
        .order_by(day_col)
        .all()
    )
    by_day = [
        UsageByDay(
            day=day,
            total_tokens=int(tokens),
            estimated_cost_usd=float(cost),
            call_count=int(count),
        )
        for day, tokens, cost, count in day_rows
    ]

    return UsageResponse(
        source_company=source_company,
        total_input_tokens=int(total_input),
        total_output_tokens=int(total_output),
        total_tokens=int(total_input) + int(total_output),
        total_estimated_cost_usd=float(total_cost),
        total_calls=int(total_calls),
        by_stage=by_stage,
        by_day=by_day,
    )
