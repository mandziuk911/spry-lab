"""S3 event consumer that emails reports without touching the database."""

import json
import logging
import os
from email.message import EmailMessage
from urllib.parse import unquote_plus

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    records = event.get("Records", [])
    if not records:
        raise ValueError("S3 notification contains no records")
    validated = []
    for record in records:
        if record.get("eventSource") != "aws:s3":
            raise ValueError("mailer accepts S3 notifications only")
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        if (
            bucket != os.environ["REPORTS_BUCKET"]
            or not key.startswith("reports/")
            or not key.endswith(".csv")
        ):
            raise ValueError("notification is outside the report prefix")
        validated.append((bucket, key))
    import boto3

    s3 = boto3.client("s3")
    ses = boto3.client("sesv2")
    results = []
    for bucket, key in validated:
        logger.info(
            json.dumps(
                {"message": "report-mailer triggered", "trigger": "s3", "key": key}, separators=(",", ":")
            )
        )
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        name = key.rsplit("/", 1)[-1]
        message = EmailMessage()
        message["Subject"] = f"Spry weekly meetings report — {name.removesuffix('.csv')}"
        message["From"] = os.environ["REPORT_EMAIL"]
        message["To"] = os.environ["REPORT_EMAIL"]
        message.set_content("Your weekly Spry meetings report is attached as a CSV file.")
        message.add_attachment(body, maintype="text", subtype="csv", filename=name)
        response = ses.send_email(
            FromEmailAddress=os.environ["REPORT_EMAIL"],
            Destination={"ToAddresses": [os.environ["REPORT_EMAIL"]]},
            Content={"Raw": {"Data": message.as_bytes()}},
        )
        results.append({"key": key, "message_id": response.get("MessageId")})
    return {"sent": len(results)}
