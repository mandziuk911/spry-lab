"""Authoritative agenda validation shared by persistence and AI parsing."""

from datetime import date
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

NonemptyText = Annotated[str, Field(min_length=1, max_length=1000)]
Owner = Annotated[str, Field(max_length=200)]


class AgendaItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic: NonemptyText
    owner: Owner | None = None
    minutes: Annotated[int, Field(strict=True, ge=1, le=480)] | None = None


class ActionItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task: NonemptyText
    owner: Owner | None = None
    due: date | None = None

    @field_validator("due", mode="before")
    @classmethod
    def require_date_string(cls, value: object) -> object:
        if value is not None and (not isinstance(value, str) or len(value) != 10):
            raise ValueError("Use an ISO 8601 date (YYYY-MM-DD)")
        return value


class ParsedAgenda(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Annotated[str, Field(max_length=200)] | None = None
    starts_at: AwareDatetime | None = None
    duration_minutes: Annotated[int, Field(strict=True, ge=1, le=600)] | None = None
    items: list[AgendaItem] = Field(max_length=100)
    action_items: list[ActionItem] = Field(max_length=100)
    language: NonemptyText

    @field_validator("starts_at", mode="before")
    @classmethod
    def require_offset_string(cls, value: object) -> object:
        if value is not None and not isinstance(value, str):
            raise ValueError("Use a timezone-aware ISO 8601 string")
        return value


class AgendaSave(ParsedAgenda):
    ai_suggestion: ParsedAgenda | None = None
    ai_model: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    ai_prompt_version: Annotated[str, Field(min_length=1, max_length=200)] | None = None

    @model_validator(mode="after")
    def require_complete_provenance(self) -> "AgendaSave":
        values = (self.ai_suggestion, self.ai_model, self.ai_prompt_version)
        if any(value is not None for value in values) and not all(value is not None for value in values):
            raise ValueError("AI suggestion, model and prompt version must be supplied together")
        return self
