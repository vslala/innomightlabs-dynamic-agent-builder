from __future__ import annotations

from typing import Any

from src.email import EmailService
from src.form_validation import parse_email_list


async def send(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del context

    subject = str(arguments.get("subject") or "").strip()
    body = str(arguments.get("body") or "").strip()
    if not subject:
        raise ValueError("Missing email subject")
    if not body:
        raise ValueError("Missing email body")

    recipients = parse_email_list(str(config.get("to") or ""))
    if not recipients:
        raise ValueError("Send Email skill is missing configured recipients")

    email_service = EmailService()
    recipient_results = []
    for email in recipients:
        sent = await email_service.send_agent_response_email(
            to_email=email,
            subject=subject,
            body_html=body,
        )
        recipient_results.append({"email": email, "sent": sent})

    succeeded = sum(1 for item in recipient_results if item["sent"])
    failed = len(recipient_results) - succeeded
    return {
        "sent": succeeded > 0,
        "total": len(recipient_results),
        "succeeded": succeeded,
        "failed": failed,
        "recipients": recipient_results,
    }
