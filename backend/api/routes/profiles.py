"""Lists registered company profiles -- backs the frontend's profile switcher
-- and (Phase 8) exposes full profile detail for the /profiles side-by-side
comparison page: extraction fields, the shared category taxonomy, and a
readable excerpt of appeal guidance per category."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import (
    AppealGuidanceExcerpt,
    ExtractionFieldOut,
    ProfileDetailOut,
    ProfileOut,
)
from db.models import CLASSIFICATION_CATEGORIES
from profiles import PROFILES, CompanyProfile, get_profile

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def _excerpt(text: str, max_len: int = 220) -> str:
    """Collapse whitespace and cut to a readable excerpt -- appeal_guidance
    strings are already a couple of sentences, this just keeps the API
    response (and the frontend card) from dumping the full paragraph."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_len:
        return collapsed
    cut = collapsed[:max_len].rsplit(" ", 1)[0]
    return cut + "…"


def _to_detail(profile: CompanyProfile) -> ProfileDetailOut:
    properties = profile.extraction_tool["input_schema"]["properties"]
    required = set(profile.extraction_tool["input_schema"].get("required", []))
    extraction_fields = [
        ExtractionFieldOut(
            name=name,
            type=spec.get("type", "string"),
            description=spec.get("description", ""),
            required=name in required,
        )
        for name, spec in properties.items()
    ]
    appeal_guidance = [
        AppealGuidanceExcerpt(category=category, excerpt=_excerpt(text))
        for category, text in profile.appeal_guidance.items()
    ]
    return ProfileDetailOut(
        key=profile.key,
        display_name=profile.display_name,
        extraction_fields=extraction_fields,
        # Deliberately the same list object's contents on every profile --
        # these six categories are universal across profiles, not
        # profile-specific. See profiles/base.py's module docstring.
        category_taxonomy=list(CLASSIFICATION_CATEGORIES),
        appeal_guidance=appeal_guidance,
    )


@router.get("", response_model=list[ProfileOut])
def list_profiles() -> list[ProfileOut]:
    return [
        ProfileOut(key=profile.key, display_name=profile.display_name)
        for profile in PROFILES.values()
    ]


@router.get("/{key}", response_model=ProfileDetailOut)
def get_profile_detail(key: str) -> ProfileDetailOut:
    try:
        profile = get_profile(key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_detail(profile)
