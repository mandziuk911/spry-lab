"""Function URL handler. Authenticate, bound, parse, validate, suggest. Never save."""

import base64
import binascii
import json
import logging
import re
import time
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.ai.agenda import (
    PROMPT_VERSION,
    AgendaParseError,
    ParserThrottled,
    ParserUnavailable,
    cost_usd,
    model_id,
    parse_agenda,
)
from app.ai.auth import verify_cognito_token

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
MAX_BODY_BYTES = 65_536


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=10_000)
    today: date
    tz: str = Field(min_length=1, max_length=64)

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value):
        if not value.strip():
            raise ValueError("Text cannot be blank")
        return value

    @field_validator("today", mode="before")
    @classmethod
    def iso_date_only(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("today must be YYYY-MM-DD")
        return value

    @field_validator("tz")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("tz must be an IANA time zone") from exc
        return value


def response(status: int, body: dict | None = None) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": json.dumps(body or {}, ensure_ascii=False),
    }


def log_failure(user: str, started: float, error: Exception) -> None:
    usage = getattr(error, "usage", {"input_tokens": 0, "output_tokens": 0})
    log.info(
        json.dumps(
            {
                "event": "agenda_parse_failed",
                "user": user,
                "model": model_id(),
                "prompt_version": PROMPT_VERSION,
                **usage,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "cost_usd": cost_usd(usage),
                "note": "usage known from completed calls only; timed-out calls may still be billed",
            }
        )
    )


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "POST")
    if method == "OPTIONS":
        return response(204)
    headers = {key.lower(): value for key, value in (event.get("headers") or {}).items()}
    try:
        user = verify_cognito_token(headers.get("authorization", ""))
    except HTTPException as exc:
        result = response(
            401 if exc.status_code == 401 else 502,
            {
                "error": "Unauthorized" if exc.status_code == 401 else "Authentication service unavailable",
            },
        )
        if exc.status_code == 401:
            result["headers"]["www-authenticate"] = "Bearer"
        return result
    if method != "POST":
        return response(405, {"error": "Use POST"})
    try:
        raw = event.get("body", "")
        if not isinstance(raw, str):
            return response(422, {"error": "Expected a JSON body"})
        if len(raw) > MAX_BODY_BYTES * 2:
            return response(413, {"error": "Text is too long"})
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
            return response(413, {"error": "Text is too long"})
        document = json.loads(raw)
        if (
            isinstance(document, dict)
            and isinstance(document.get("text"), str)
            and len(document["text"]) > 10_000
        ):
            return response(413, {"error": "Text exceeds 10000 characters"})
        request = ParseRequest.model_validate(document)
    except (ValueError, TypeError, ValidationError, binascii.Error):
        return response(422, {"error": "Provide text, today (YYYY-MM-DD), and an IANA time zone"})
    started = time.monotonic()
    try:
        agenda, usage = parse_agenda(request.text, request.today, request.tz)
    except ParserThrottled as exc:
        log_failure(user["sub"], started, exc)
        result = response(429, {"error": "Parser is busy; try again later"})
        result["headers"]["retry-after"] = "10"
        return result
    except ParserUnavailable as exc:
        log_failure(user["sub"], started, exc)
        return response(502, {"error": "Model service unavailable; enter the agenda manually"})
    except AgendaParseError as exc:
        log_failure(user["sub"], started, exc)
        return response(422, {"error": "No valid meeting agenda found; enter it manually"})
    except ValueError:
        return response(502, {"error": "Parser configuration unavailable"})
    log.info(
        json.dumps(
            {
                "event": "agenda_parsed",
                "user": user["sub"],
                "model": model_id(),
                "prompt_version": PROMPT_VERSION,
                **usage,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "cost_usd": cost_usd(usage),
            }
        )
    )
    return response(
        200, {"agenda": agenda.model_dump(mode="json"), "model": model_id(), "prompt_version": PROMPT_VERSION}
    )
