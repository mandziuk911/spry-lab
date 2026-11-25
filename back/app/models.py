import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_meetings_duration"),
        CheckConstraint("attendee_count >= 0", name="ck_meetings_attendee_count"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attendee_count: Mapped[int] = mapped_column(Integer)


class MeetingAgenda(Base):
    __tablename__ = "meeting_agendas"
    __table_args__ = (
        CheckConstraint("jsonb_typeof(agenda) = 'object'", name="ck_meeting_agendas_object"),
        CheckConstraint(
            "(ai_suggestion IS NULL AND ai_model IS NULL AND ai_prompt_version IS NULL) OR "
            "(ai_suggestion IS NOT NULL AND ai_model IS NOT NULL AND ai_prompt_version IS NOT NULL "
            "AND jsonb_typeof(ai_suggestion) = 'object' "
            "AND length(trim(ai_model)) > 0 AND length(trim(ai_prompt_version)) > 0)",
            name="ck_meeting_agendas_provenance",
        ),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    agenda: Mapped[dict] = mapped_column(JSONB)
    ai_suggestion: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    ai_model: Mapped[str | None] = mapped_column(String(200))
    ai_prompt_version: Mapped[str | None] = mapped_column(String(200))
