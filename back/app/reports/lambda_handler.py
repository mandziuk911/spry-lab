"""AWS Lambda entry point for queued and direct weekly-report commands."""

import json
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.reports.weekly import build_weekly_report

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def previous_iso_week(now: datetime | None = None) -> str:
    local_today = (now or datetime.now(ZoneInfo("Europe/Kyiv"))).astimezone(ZoneInfo("Europe/Kyiv")).date()
    year, week, _ = (local_today - timedelta(days=7)).isocalendar()
    return f"{year}-W{week:02d}"


def parse_command(event: dict) -> tuple[str, str]:
    transport = "direct"
    payload = event
    records = event.get("Records")
    if records:
        if len(records) != 1 or records[0].get("eventSource") != "aws:sqs":
            raise ValueError("report builder accepts exactly one SQS record")
        transport = "sqs"
        payload = json.loads(records[0]["body"])
    if not isinstance(payload, dict):
        raise ValueError("report command must be an object")
    source = payload.get("source", transport)
    if source not in {"schedule", "make", "sqs", "direct"}:
        raise ValueError("unsupported report trigger")
    week = payload.get("week") or previous_iso_week()
    # Validate and normalize the week before any database or S3 side effect.
    from app.reports.weekly import _week_start

    _week_start(week)
    return week, source


def handler(event, context):
    import boto3

    week, source = parse_command(event)
    logger.info(
        json.dumps(
            {
                "message": "report-builder triggered",
                "trigger": source,
                "transport": "sqs" if event.get("Records") else "direct",
                "week": week,
            },
            separators=(",", ":"),
        )
    )
    content = build_weekly_report(week)
    key = f"reports/{week}.csv"
    boto3.client("s3").put_object(
        Bucket=os.environ["REPORTS_BUCKET"],
        Key=key,
        Body=content,
        ContentType="text/csv; charset=utf-8",
    )
    return {"week": week, "key": key, "bytes": len(content)}
