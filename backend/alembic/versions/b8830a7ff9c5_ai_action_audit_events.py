"""add ai_action to audit_event_type enum

Extends the existing `audit_event_type` Postgres enum (created by
c96f0c026d93) with a third value, "ai_action", so the pipeline itself
(backend/pipeline/run.py) can log its own successful actions -- extraction,
classification, appeal drafting -- into the same `corrections` table as
human corrections and appeal-review decisions. This lets the Audit History
timeline tell the whole story in order: AI extracted -> AI classified -> AI
drafted -> human corrected -> human approved, not just the human half of it.

No new columns needed -- ai_action events reuse field_corrected (the
pipeline stage key)/old_value (always "")/new_value (a short summary)/
corrected_by (always "AI") exactly as they already exist; see
db/models.py's AuditEvent docstring for the full field mapping.

Revision ID: b8830a7ff9c5
Revises: c96f0c026d93
Create Date: 2026-08-13 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8830a7ff9c5'
down_revision: Union[str, Sequence[str], None] = 'c96f0c026d93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres allows ADD VALUE inside a transaction block as long as the
    # new value isn't *used* in that same transaction (which it isn't here
    # -- this migration only extends the enum, it doesn't insert any rows).
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'ai_action'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums -- removing one requires
    # recreating the type from scratch (create new type, ALTER TABLE ...
    # TYPE, drop old type, rename), which is more disruptive than this
    # migration's forward change justifies. Consistent with this repo's
    # existing tradeoff on irreversible-in-practice migrations (see
    # c96f0c026d93's downgrade note on backfilled appeal_review rows not
    # being recoverable): downgrading here deletes the ai_action rows so
    # the data is consistent with a codebase that no longer writes them,
    # but leaves 'ai_action' as a valid (unused) enum value in the type.
    op.execute("DELETE FROM corrections WHERE event_type = 'ai_action'")
