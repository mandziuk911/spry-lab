from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Meeting
from app.schemas import MeetingCreate
from app.services.errors import storage_operation


def list_meetings(db: Session) -> Sequence[Meeting]:
    with storage_operation(db):
        return db.scalars(select(Meeting).order_by(Meeting.starts_at, Meeting.id)).all()


def create_meeting(db: Session, data: MeetingCreate) -> Meeting:
    with storage_operation(db):
        meeting = Meeting(**data.model_dump())
        db.add(meeting)
        db.commit()  # INSERT RETURNING supplies the database-generated UUID; never retry POST.
        return meeting


def delete_meeting(db: Session, meeting_id: UUID) -> bool:
    with storage_operation(db):
        deleted_id = db.scalar(delete(Meeting).where(Meeting.id == meeting_id).returning(Meeting.id))
        db.commit()  # Never retry an uncertain commit.
        return deleted_id is not None
