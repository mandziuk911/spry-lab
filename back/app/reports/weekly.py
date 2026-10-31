"""Build deterministic weekly meeting CSV reports."""

import csv
import io
import re
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Meeting

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


def _week_start(week: str) -> datetime:
    match = _WEEK_RE.fullmatch(week)
    if not match:
        raise ValueError("week must use ISO format YYYY-Www")
    try:
        monday = date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)
    except ValueError as exc:
        raise ValueError("week is not a valid ISO week") from exc
    return datetime.combine(monday, datetime.min.time(), tzinfo=UTC)


def _hours(meetings: list[Meeting]) -> float:
    return sum((meeting.ends_at - meeting.starts_at).total_seconds() for meeting in meetings) / 3600


def build_weekly_report(week: str, session: "Session | None" = None) -> bytes:
    """Return a UTF-8 CSV for one ISO week and the preceding week.

    A session can be supplied for deterministic tests/callers; otherwise this
    function owns and closes a short-lived SQLAlchemy session.
    """
    start = _week_start(week)
    end = start + timedelta(days=7)
    previous_start = start - timedelta(days=7)

    def query(db: "Session") -> bytes:
        rows = list(
            db.scalars(
                select(Meeting)
                .where(Meeting.starts_at >= previous_start, Meeting.starts_at < end)
                .order_by(Meeting.starts_at, Meeting.id)
            ).all()
        )
        previous = [meeting for meeting in rows if previous_start <= meeting.starts_at < start]
        current = [meeting for meeting in rows if start <= meeting.starts_at < end]
        current_hours = _hours(current)
        previous_hours = _hours(previous)

        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(
            [
                "section",
                "metric",
                "value",
                "change",
                "title",
                "starts_at_utc",
                "duration_hours",
                "attendee_count",
            ]
        )
        writer.writerow(["summary", "week", week, "", "", "", "", ""])
        writer.writerow(["summary", "meetings", len(current), len(current) - len(previous), "", "", "", ""])
        writer.writerow(
            [
                "summary",
                "duration_hours",
                f"{current_hours:.2f}",
                f"{current_hours - previous_hours:.2f}",
                "",
                "",
                "",
                "",
            ]
        )
        previous_iso = previous_start.date().isocalendar()
        writer.writerow(
            [
                "previous_week",
                "week",
                f"{previous_iso.year}-W{previous_iso.week:02d}",
                "",
                "",
                "",
                "",
                "",
            ]
        )
        writer.writerow(["previous_week", "meetings", len(previous), "", "", "", "", ""])
        writer.writerow(["previous_week", "duration_hours", f"{previous_hours:.2f}", "", "", "", "", ""])
        longest = sorted(
            current,
            key=lambda meeting: (
                -(meeting.ends_at - meeting.starts_at).total_seconds(),
                meeting.starts_at,
                str(meeting.id),
            ),
        )[:5]
        for meeting in longest:
            duration = (meeting.ends_at - meeting.starts_at).total_seconds() / 3600
            writer.writerow(
                [
                    "longest_meeting",
                    "",
                    "",
                    "",
                    meeting.title,
                    meeting.starts_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    f"{duration:.2f}",
                    meeting.attendee_count,
                ]
            )
        return output.getvalue().encode("utf-8")

    if session is not None:
        return query(session)
    with SessionLocal() as db:
        return query(db)
