import csv
import email
import io
import json
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Meeting
from app.reports import lambda_handler, mailer, weekly


def meeting(title, start, duration, attendees=1):
    return SimpleNamespace(
        id=uuid4(),
        title=title,
        starts_at=datetime.fromisoformat(start).replace(tzinfo=UTC),
        ends_at=datetime.fromisoformat(start)
        .replace(tzinfo=UTC)
        .replace(hour=datetime.fromisoformat(start).hour + duration),
        attendee_count=attendees,
    )


class FakeScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self, statement):
        return FakeScalars(self.rows)


class SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, *args):
        return False


def parse_report(content):
    return list(csv.reader(io.StringIO(content.decode("utf-8"))))


def test_weekly_csv_current_previous_and_longest(monkeypatch):
    rows = [
        meeting("Previous", "2026-09-29T10:00:00", 1, 2),
        meeting("Short", "2026-10-05T10:00:00", 1, 3),
        meeting("Long", "2026-10-06T10:00:00", 3, 5),
    ]
    monkeypatch.setattr(weekly, "SessionLocal", SessionFactory(FakeSession(rows)))
    report = parse_report(weekly.build_weekly_report("2026-W41"))
    assert report[1] == ["summary", "week", "2026-W41", "", "", "", "", ""]
    assert report[2][1:4] == ["meetings", "2", "1"]
    assert report[3][1:4] == ["duration_hours", "4.00", "3.00"]
    assert report[4][2] == "2026-W40"
    assert report[5][2] == "1"
    assert [row[4] for row in report[7:]] == ["Long", "Short"]
    assert report[7][7] == "5"


def test_weekly_report_queries_only_the_dedicated_postgres_schema(isolated_db):
    Base.metadata.create_all(isolated_db)
    factory = sessionmaker(bind=isolated_db, expire_on_commit=False)
    with factory() as session:
        session.add_all(
            [
                Meeting(
                    title="Previous",
                    starts_at=datetime(2026, 9, 28, 9, tzinfo=UTC),
                    ends_at=datetime(2026, 9, 28, 10, tzinfo=UTC),
                    attendee_count=2,
                ),
                Meeting(
                    title="Current",
                    starts_at=datetime(2026, 10, 5, 9, tzinfo=UTC),
                    ends_at=datetime(2026, 10, 5, 11, tzinfo=UTC),
                    attendee_count=4,
                ),
                Meeting(
                    title="Next week",
                    starts_at=datetime(2026, 10, 12, 9, tzinfo=UTC),
                    ends_at=datetime(2026, 10, 12, 12, tzinfo=UTC),
                    attendee_count=8,
                ),
            ]
        )
        session.commit()
        report = parse_report(weekly.build_weekly_report("2026-W41", session))
    assert report[2][2:4] == ["1", "0"]
    assert report[3][2:4] == ["2.00", "1.00"]
    assert [row[4] for row in report[7:]] == ["Current"]


def test_week_validation_rejects_invalid_format_and_week():
    for value in ("2026-41", "2026-W00", "2021-W53", "../2026-W41"):
        with pytest.raises(ValueError):
            weekly.build_weekly_report(value, FakeSession([]))


def test_weekly_report_handles_iso_year_boundary(monkeypatch):
    monkeypatch.setattr(weekly, "SessionLocal", SessionFactory(FakeSession([])))
    report = parse_report(weekly.build_weekly_report("2021-W01"))
    assert report[4][2] == "2020-W53"
    assert report[2][2:] == ["0", "0", "", "", "", ""]


def test_builder_handles_sqs_and_logs_origin(monkeypatch, caplog):
    monkeypatch.setenv("REPORTS_BUCKET", "spry-reports-test")
    put = Mock()
    monkeypatch.setitem(
        sys.modules, "boto3", SimpleNamespace(client=lambda service: SimpleNamespace(put_object=put))
    )
    monkeypatch.setattr(lambda_handler, "build_weekly_report", Mock(return_value=b"a,b\n"))
    event = {
        "Records": [
            {"eventSource": "aws:sqs", "body": json.dumps({"week": "2026-W41", "source": "schedule"})}
        ]
    }
    with caplog.at_level("INFO"):
        result = lambda_handler.handler(event, None)
    assert any(
        '"trigger":"schedule"' in record.message and '"transport":"sqs"' in record.message
        for record in caplog.records
    )
    assert result == {"week": "2026-W41", "key": "reports/2026-W41.csv", "bytes": 4}
    assert put.call_args.kwargs["Bucket"] == "spry-reports-test"
    assert put.call_args.kwargs["Key"] == "reports/2026-W41.csv"


def test_builder_rejects_bad_sqs_before_upload(monkeypatch):
    put = Mock()
    monkeypatch.setitem(
        sys.modules, "boto3", SimpleNamespace(client=lambda service: SimpleNamespace(put_object=put))
    )
    with pytest.raises(ValueError):
        lambda_handler.handler({"Records": [{"eventSource": "aws:sqs", "body": '{"week":"2026-W99"}'}]}, None)
    put.assert_not_called()


def test_mailer_sends_csv_as_raw_mime_and_never_uploads(monkeypatch, caplog):
    monkeypatch.setenv("REPORTS_BUCKET", "spry-reports-test")
    monkeypatch.setenv("REPORT_EMAIL", "student@example.edu")
    get = Mock(return_value={"Body": SimpleNamespace(read=lambda: b"heading\n")})
    send = Mock(return_value={"MessageId": "message-1"})
    clients = {"s3": SimpleNamespace(get_object=get), "sesv2": SimpleNamespace(send_email=send)}
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda name: clients[name]))
    event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {"bucket": {"name": "spry-reports-test"}, "object": {"key": "reports%2F2026-W41.csv"}},
            }
        ]
    }
    with caplog.at_level("INFO"):
        assert mailer.handler(event, None) == {"sent": 1}
    assert any('"trigger":"s3"' in record.message for record in caplog.records)
    raw = email.message_from_bytes(send.call_args.kwargs["Content"]["Raw"]["Data"])
    assert raw["To"] == "student@example.edu"
    attachment = next(part for part in raw.walk() if part.get_filename())
    assert attachment.get_filename() == "2026-W41.csv"
    assert attachment.get_payload(decode=True) == b"heading\n"
    get.assert_called_once_with(Bucket="spry-reports-test", Key="reports/2026-W41.csv")


def test_mailer_rejects_wrong_bucket_or_prefix(monkeypatch):
    monkeypatch.setenv("REPORTS_BUCKET", "spry-reports-test")
    with pytest.raises(ValueError):
        mailer.handler(
            {
                "Records": [
                    {
                        "eventSource": "aws:s3",
                        "s3": {"bucket": {"name": "other"}, "object": {"key": "reports/a.csv"}},
                    }
                ]
            },
            None,
        )
