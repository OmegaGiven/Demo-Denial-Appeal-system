"""
CompanyProfile: the config-per-company abstraction that drives the pipeline.

Phase 2 built extract.py/classify.py/draft_appeal.py hardcoded for a single
company (Meridian Eye Care Partners). Phase 4 pulls everything that was
company-specific -- the extraction tool schema, the system prompts for all
three stages, and the appeal-drafting guidance -- out into a CompanyProfile,
keyed off denials.source_company, so the SAME pipeline code drives multiple
client companies' claim types.

What stays fixed across every profile (not part of this class, deliberately):
  - The six CLASSIFICATION_CATEGORIES in db/models.py. These are genuinely
    universal denial root-causes across healthcare claims (coding, missing
    info, medical necessity, timely filing, eligibility, duplicate) -- a new
    profile should not invent new categories, only adjust the CARC-code
    guide and appeal guidance text that helps the model apply the existing
    six to its own claim type.
  - The classification tool's JSON schema (category enum + confidence +
    reasoning) -- classify.py keeps this as one shared, generic tool
    definition. Only the system-prompt framing and CARC-code guide vary per
    profile.
  - The retry/token-accounting/DB-write plumbing in common.py and each
    stage's *.py -- none of that is company-specific.

What genuinely varies per profile, and is captured below:
  - The extraction tool schema (different structured fields per claim type,
    e.g. cpt_code vs. hcpcs_code, and profile-specific optional fields like
    a DME Letter-of-Medical-Necessity reference number).
  - Each stage's system-prompt text (company name/domain framing, and for
    classification, a category guide with claim-type-appropriate CARC/RARC
    examples).
  - Appeal-drafting guidance per category, and the appeal system prompt's
    template (which fields it instructs the model to cite, and what
    domain-specific documentation to reference, e.g. an LMN for DME
    missing_information denials).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompanyProfile:
    # Matches denials.source_company exactly -- this is the lookup key
    # profiles/__init__.py's get_profile() uses.
    key: str
    display_name: str

    # --- Stage 1: extraction (extract.py) ---
    # Full Anthropic tool schema (name/description/input_schema), forced via
    # tool_choice. `input_schema.required` is the single source of truth for
    # which fields extract.py checks are present post-call -- see
    # extraction_required_fields below, which just reads it back out.
    extraction_tool: dict
    extraction_system_prompt: str

    # --- Stage 2: classification (classify.py) ---
    # Company/domain framing sentence(s); the CATEGORY_GUIDE text (shared
    # structure, profile-specific CARC examples per category) is appended by
    # classification_system_prompt() below.
    classification_system_prompt_intro: str
    category_guide: str

    # --- Stage 3: appeal drafting (draft_appeal.py) ---
    # One instruction string per CLASSIFICATION_CATEGORIES key -- what a
    # *substantive* appeal needs to argue for this claim type + category.
    appeal_guidance: dict[str, str]
    # Must contain literal "{category}" and "{guidance}" format placeholders
    # -- appeal_system_prompt() below fills them in.
    appeal_system_prompt_template: str
    # Extracted-field keys (beyond claim_ref, which is always checked
    # against the denial row itself) that must literally appear in the
    # drafted letter for it to pass the grounding check, when the field was
    # present in extraction. Defaults to the physician NPI, which both
    # profiles extract.
    appeal_grounding_fields: tuple[str, ...] = ("physician_npi",)

    @property
    def extraction_tool_name(self) -> str:
        return self.extraction_tool["name"]

    @property
    def extraction_required_fields(self) -> tuple[str, ...]:
        return tuple(self.extraction_tool["input_schema"]["required"])

    def classification_system_prompt(self) -> str:
        return self.classification_system_prompt_intro + "\n\n" + self.category_guide

    def appeal_system_prompt(self, category: str) -> str:
        return self.appeal_system_prompt_template.format(
            category=category, guidance=self.appeal_guidance[category]
        )
