"""Add one independently editable agenda per meeting.

Revision ID: 0005
Revises: 0004

Downgrade drops ONLY meeting_agendas and its saved agenda/provenance data.
Existing meetings and earlier migration history are not modified.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meeting_agendas",
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("agenda", postgresql.JSONB(), nullable=False),
        sa.Column("ai_suggestion", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("ai_model", sa.String(200), nullable=True),
        sa.Column("ai_prompt_version", sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint("meeting_id"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.CheckConstraint("jsonb_typeof(agenda) = 'object'", name="ck_meeting_agendas_object"),
        sa.CheckConstraint(
            "(ai_suggestion IS NULL AND ai_model IS NULL AND ai_prompt_version IS NULL) OR "
            "(ai_suggestion IS NOT NULL AND ai_model IS NOT NULL AND ai_prompt_version IS NOT NULL "
            "AND jsonb_typeof(ai_suggestion) = 'object' "
            "AND length(trim(ai_model)) > 0 AND length(trim(ai_prompt_version)) > 0)",
            name="ck_meeting_agendas_provenance",
        ),
    )


def downgrade() -> None:
    op.drop_table("meeting_agendas")
