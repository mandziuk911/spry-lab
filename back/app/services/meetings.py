from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agenda_schemas import AgendaSave
from app.models import Meeting, MeetingAgenda
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


def get_agenda(db: Session, meeting_id: UUID) -> tuple[bool, dict | None]:
    with storage_operation(db):
        if db.get(Meeting, meeting_id) is None:
            return False, None
        saved = db.get(MeetingAgenda, meeting_id)
        if saved is None:
            return True, None
        return True, {
            **saved.agenda,
            "ai_suggestion": saved.ai_suggestion,
            "ai_model": saved.ai_model,
            "ai_prompt_version": saved.ai_prompt_version,
        }


def save_agenda(db: Session, meeting_id: UUID, data: AgendaSave) -> dict | None:
    with storage_operation(db):
        # Lock the parent against concurrent deletion until the upsert commits.
        if db.scalar(select(Meeting.id).where(Meeting.id == meeting_id).with_for_update()) is None:
            return None
        payload = data.model_dump(mode="json")
        provenance = {key: payload[key] for key in ("ai_suggestion", "ai_model", "ai_prompt_version")}
        agenda = {key: value for key, value in payload.items() if key not in provenance}
        values = {"agenda": agenda, **provenance}
        statement = insert(MeetingAgenda).values(meeting_id=meeting_id, **values)
        db.execute(statement.on_conflict_do_update(index_elements=[MeetingAgenda.meeting_id], set_=values))
        db.commit()  # Never retry an uncertain commit.
        return payload


def delete_meeting(db: Session, meeting_id: UUID) -> bool:
    with storage_operation(db):
        deleted_id = db.scalar(delete(Meeting).where(Meeting.id == meeting_id).returning(Meeting.id))
        db.commit()  # Never retry an uncertain commit.
        return deleted_id is not None
