import logging
from typing import Optional

import boto3

from src.config import settings

log = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, body: str, reply_to: Optional[str] = None) -> None:
    if not settings.ses_from_email:
        log.info("SES_FROM_EMAIL not configured; skipping email to %s", to_email)
        return

    client = boto3.client("ses", region_name=settings.aws_region)
    message = {
        "Subject": {"Data": subject, "Charset": "UTF-8"},
        "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
    }

    params = {
        "Source": settings.ses_from_email,
        "Destination": {"ToAddresses": [to_email]},
        "Message": message,
    }

    reply_to_address = reply_to or settings.ses_reply_to_email
    if reply_to_address:
        params["ReplyToAddresses"] = [reply_to_address]

    try:
        client.send_email(**params)
    except Exception as exc:
        log.warning("Failed to send email to %s: %s", to_email, exc)
