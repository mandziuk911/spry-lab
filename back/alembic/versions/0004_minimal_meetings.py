"""Keep meetings/UUIDs, replace participant relationships with attendee counts.

Revision ID: 0004
Revises: 0003

IRREVERSIBLE: participant identities, associations, users, ownership and legacy
meeting metadata are deleted. Counts cannot reconstruct those records. Restore
a pre-upgrade backup to return to 0003; downgrade refuses before any mutation,
even on an empty database (deleted users/participants cannot be detected).
Review and back up valuable databases before executing this migration.
Invalid legacy durations abort the transactional upgrade rather than silently
changing meeting times or deleting meetings.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("attendee_count", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE meetings SET attendee_count = "
        "(SELECT count(*) FROM meeting_participants WHERE meeting_id = meetings.id)"
    )
    op.alter_column("meetings", "attendee_count", nullable=False)
    # Validate before removing legacy data. PostgreSQL DDL is transactional.
    op.create_check_constraint("ck_meetings_attendee_count", "meetings", "attendee_count >= 0")
    op.create_check_constraint("ck_meetings_duration", "meetings", "ends_at > starts_at")
    op.drop_table("meeting_participants")
    op.drop_table("participants")
    op.drop_index("ix_meetings_owner_id", table_name="meetings")
    op.drop_constraint("meetings_owner_id_fkey", "meetings", type_="foreignkey")
    for column in ("owner_id", "description", "call_link", "place", "created_at", "updated_at"):
        op.drop_column("meetings", column)
    op.drop_table("users")


def downgrade() -> None:
    raise RuntimeError(
        "0004 is irreversible: deleted identities, associations and meeting metadata "
        "cannot be restored from attendee counts. Restore a pre-upgrade backup. "
        "No downgrade changes have been made."
    )
