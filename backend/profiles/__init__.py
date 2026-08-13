"""
Company-profile registry: maps denials.source_company -> CompanyProfile.

To add a third client company:
  1. Create backend/profiles/<new_company_key>.py, following
     meridian_eyecare_partners.py / summit_dme_providers.py as
     templates: define EXTRACTION_TOOL (the forced tool-use schema for
     stage 1), EXTRACTION_SYSTEM_PROMPT, CLASSIFICATION_SYSTEM_PROMPT_INTRO
     + CATEGORY_GUIDE (stage 2), and APPEAL_GUIDANCE +
     APPEAL_SYSTEM_PROMPT_TEMPLATE (stage 3), then build a module-level
     `PROFILE = CompanyProfile(...)`.
  2. Register it in PROFILES below.
  3. Add synthetic denial data for it under backend/data/, with
     `source_company` matching the new profile's `key` exactly, and seed it
     (see db/seed.py -- pass the new JSON file's path).
  Nothing in pipeline/*.py needs to change -- extract.py, classify.py,
  draft_appeal.py, and run.py all resolve the profile from
  denial.source_company via get_profile() below and drive their tool
  schemas/prompts entirely off the resolved CompanyProfile.
"""

from __future__ import annotations

from .base import CompanyProfile
from .meridian_eyecare_partners import PROFILE as MERIDIAN_EYECARE_PARTNERS
from .summit_dme_providers import PROFILE as SUMMIT_DME_PROVIDERS

PROFILES: dict[str, CompanyProfile] = {
    MERIDIAN_EYECARE_PARTNERS.key: MERIDIAN_EYECARE_PARTNERS,
    SUMMIT_DME_PROVIDERS.key: SUMMIT_DME_PROVIDERS,
}


def get_profile(source_company: str) -> CompanyProfile:
    try:
        return PROFILES[source_company]
    except KeyError:
        raise ValueError(
            f"no CompanyProfile registered for source_company={source_company!r}. "
            f"Known profiles: {sorted(PROFILES)}"
        )


__all__ = ["CompanyProfile", "PROFILES", "get_profile"]
