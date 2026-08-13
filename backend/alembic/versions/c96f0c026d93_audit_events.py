"""extend corrections into a unified audit-event log

Adds event_type ("correction" | "appeal_review") and appeal_id to the
existing `corrections` table so it can hold both human field-corrections
(unchanged) and permanent appeal approve/reject/sent review-decision
records, queryable together as one chronological compliance audit trail.

Also backfills appeal_review events for any appeals rows that already have
a reviewer/reviewed_at set (from testing prior to this migration). This can
only recover the CURRENT state on each appeals row -- if an appeal was
reviewed more than once before this migration existed, only the latest
decision survived to backfill from. Any earlier, overwritten review is not
recoverable; only audit events created from this migration forward are
guaranteed immutable.

Revision ID: c96f0c026d93
Revises: 601e7aa74c38
Create Date: 2026-08-13 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c96f0c026d93'
down_revision: Union[str, Sequence[str], None] = '601e7aa74c38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

audit_event_type = sa.Enum("correction", "appeal_review", name="audit_event_type")


def upgrade() -> None:
    bind = op.get_bind()
    audit_event_type.create(bind, checkfirst=True)

    op.add_column(
        "corrections",
        sa.Column(
            "event_type",
            audit_event_type,
            nullable=False,
            server_default="correction",
        ),
    )
    op.add_column(
        "corrections",
        sa.Column("appeal_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_corrections_appeal_id",
        "corrections",
        "appeals",
        ["appeal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_corrections_appeal_id", "corrections", ["appeal_id"], unique=False)
    op.create_index("ix_corrections_event_type", "corrections", ["event_type"], unique=False)

    # Backfill: represent existing appeal review decisions already recorded
    # on appeals.reviewer/reviewed_at as appeal_review audit events, so
    # pre-existing review actions show up in the unified timeline too.
    op.execute(
        """
        INSERT INTO corrections
            (denial_id, appeal_id, event_type, field_corrected, old_value, new_value,
             corrected_by, corrected_at, notes)
        SELECT
            denial_id,
            id,
            'appeal_review',
            'appeal.status',
            'draft',
            status,
            reviewer,
            reviewed_at,
            'Backfilled at migration time from the appeals row''s current state -- '
            'represents only the most recent review decision on record for this '
            'appeal; any earlier, overwritten review decision (if one occurred '
            'before this audit-event log existed) is not recoverable.'
        FROM appeals
        WHERE reviewer IS NOT NULL AND reviewed_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM corrections WHERE event_type = 'appeal_review'")
    op.drop_index("ix_corrections_event_type", table_name="corrections")
    op.drop_index("ix_corrections_appeal_id", table_name="corrections")
    op.drop_constraint("fk_corrections_appeal_id", "corrections", type_="foreignkey")
    op.drop_column("corrections", "appeal_id")
    op.drop_column("corrections", "event_type")
    audit_event_type.drop(op.get_bind(), checkfirst=True)
