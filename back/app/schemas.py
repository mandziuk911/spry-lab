from datetime import UTC, datetime
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


class MeetingCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    attendee_count: int = Field(strict=True, ge=0)

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def require_iso_string(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("Use a timezone-aware ISO 8601 string")
        return value

    @model_validator(mode="after")
    def ends_after_start(self) -> "MeetingCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("The meeting must end after it starts")
        return self


class MeetingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    attendee_count: int

    @field_serializer("starts_at", "ends_at")
    def utc_timestamp(self, value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
