from __future__ import annotations

import base64
from html.parser import HTMLParser
from typing import Any

import httpx
from pydantic import ValidationError

from src.config import settings
from src.crypto import decrypt, encrypt
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.google_mail.models import (
    GoogleMailBatchMessageRequest,
    GoogleMailCredentials,
    GoogleMailMessageRequest,
    GoogleMailSearchRequest,
)

GOOGLE_MAIL_PROVIDER_NAME = "GoogleMail"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_MESSAGES_API = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
MAX_READ_CHARACTERS = 20000
METADATA_HEADERS = ["Subject", "From", "To", "Cc", "Date"]


class GoogleMailError(Exception):
    pass


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _require_owner_email(context: dict[str, Any]) -> str:
    owner_email = str(context.get("owner_email", "")).strip()
    if not owner_email:
        raise ValueError("Missing skill runtime owner context")
    return owner_email


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }


def _json_headers(access_token: str) -> dict[str, str]:
    return {
        **_headers(access_token),
        "Content-Type": "application/json",
    }


def _credentials_from_provider_settings(provider_settings: ProviderSettings) -> GoogleMailCredentials:
    try:
        data = decrypt(provider_settings.encrypted_credentials)
        return GoogleMailCredentials.model_validate_json(data)
    except ValidationError as e:
        raise GoogleMailError(f"Invalid Google Mail credentials payload: {e}") from e
    except Exception as e:
        raise GoogleMailError("Invalid Google Mail credentials payload") from e


def _save_credentials(
    provider_settings: ProviderSettings,
    repo: ProviderSettingsRepository,
    credentials: GoogleMailCredentials,
) -> ProviderSettings:
    updated_settings = ProviderSettings(
        user_email=provider_settings.user_email,
        provider_name=provider_settings.provider_name,
        encrypted_credentials=encrypt(credentials.model_dump_json()),
        auth_type="oauth",
    )
    return repo.save(updated_settings)


async def _refresh_access_token(refresh_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    if not response.is_success:
        raise GoogleMailError(f"Google Mail token refresh failed: {response.text}")

    payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def _ensure_valid_google_mail_credentials(
    provider_settings: ProviderSettings,
    repo: ProviderSettingsRepository,
    refresh_buffer_seconds: int = 60,
) -> GoogleMailCredentials:
    credentials = _credentials_from_provider_settings(provider_settings)

    if not credentials.refresh_token:
        if not credentials.access_token:
            raise GoogleMailError("Google Mail credentials are missing access_token")
        return credentials

    if not credentials.is_expiring_soon(refresh_buffer_seconds=refresh_buffer_seconds):
        return credentials

    refreshed = await _refresh_access_token(credentials.refresh_token)
    updated_credentials = credentials.with_token_response(refreshed)
    _save_credentials(provider_settings, repo, updated_credentials)
    return updated_credentials


async def _get_access_token(context: dict[str, Any]) -> str:
    owner_email = _require_owner_email(context)
    repo = ProviderSettingsRepository()
    provider_settings = repo.find_by_provider(owner_email, GOOGLE_MAIL_PROVIDER_NAME)
    if not provider_settings:
        raise ValueError("Google Mail account is not connected for the agent owner")

    credentials = await _ensure_valid_google_mail_credentials(provider_settings, repo)
    return credentials.access_token


def _truncate_text(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_READ_CHARACTERS:
        return text, False
    return text[:MAX_READ_CHARACTERS], True


def _decode_base64url_text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    padded = value + ("=" * (-len(value) % 4))
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


def _extract_headers(payload: dict[str, Any]) -> dict[str, str]:
    headers = payload.get("headers")
    if not isinstance(headers, list):
        return {}

    extracted: dict[str, str] = {}
    for item in headers:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip().lower()
        value = str(item.get("value", "")).strip()
        if name:
            extracted[name] = value
    return extracted


def _extract_body_part(part: dict[str, Any], preferred_mime_type: str) -> str:
    mime_type = str(part.get("mimeType", "")).strip().lower()
    body = part.get("body") if isinstance(part.get("body"), dict) else {}
    data = body.get("data") if isinstance(body, dict) else None

    if data and mime_type == preferred_mime_type:
        text = _decode_base64url_text(data)
        if preferred_mime_type == "text/html":
            return _html_to_text(text)
        return text

    child_parts = part.get("parts")
    if isinstance(child_parts, list):
        for child in child_parts:
            if isinstance(child, dict):
                text = _extract_body_part(child, preferred_mime_type)
                if text:
                    return text

    return ""


def _extract_body(payload: dict[str, Any]) -> str:
    text = _extract_body_part(payload, "text/plain")
    if text:
        return text.strip()

    html_text = _extract_body_part(payload, "text/html")
    if html_text:
        return html_text.strip()

    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    fallback = _decode_base64url_text(body.get("data") if isinstance(body, dict) else None)
    return fallback.strip()


def _validate_message_request(arguments: dict[str, Any]) -> GoogleMailMessageRequest:
    try:
        return GoogleMailMessageRequest.model_validate(arguments)
    except ValidationError as e:
        raise ValueError(f"Invalid Google Mail action arguments: {e}") from e


def _validate_batch_message_request(arguments: dict[str, Any]) -> GoogleMailBatchMessageRequest:
    try:
        return GoogleMailBatchMessageRequest.model_validate(arguments)
    except ValidationError as e:
        raise ValueError(f"Invalid Google Mail batch action arguments: {e}") from e


def _validate_search_request(arguments: dict[str, Any]) -> GoogleMailSearchRequest:
    try:
        return GoogleMailSearchRequest.model_validate(arguments)
    except ValidationError as e:
        raise ValueError(f"Invalid Google Mail search arguments: {e}") from e


def _gmail_date(value: str) -> str:
    if not value:
        return ""
    parsed = value.replace("-", "/")
    parts = parsed.split("/")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("Gmail date filters must use YYYY-MM-DD or YYYY/MM/DD")
    year, month, day = (int(part) for part in parts)
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 9999):
        raise ValueError("Gmail date filters must use a valid YYYY-MM-DD or YYYY/MM/DD value")
    return f"{year:04d}/{month:02d}/{day:02d}"


def _quote_gmail_search_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _build_search_query(request: GoogleMailSearchRequest) -> str:
    terms: list[str] = []
    if request.query:
        terms.append(request.query)
    if request.start_date:
        terms.append(f"after:{_gmail_date(request.start_date)}")
    if request.end_date:
        terms.append(f"before:{_gmail_date(request.end_date)}")
    if request.newer_than:
        terms.append(f"newer_than:{request.newer_than}")
    if request.older_than:
        terms.append(f"older_than:{request.older_than}")
    if request.from_email:
        terms.append(f"from:{_quote_gmail_search_value(request.from_email)}")
    if request.to_email:
        terms.append(f"to:{_quote_gmail_search_value(request.to_email)}")
    if request.subject:
        terms.append(f"subject:{_quote_gmail_search_value(request.subject)}")
    if request.category:
        terms.append(f"category:{request.category}")
    if request.has_attachment:
        terms.append("has:attachment")
    if request.is_unread:
        terms.append("is:unread")
    return " ".join(terms)


def _format_search_result(item: dict[str, Any], index: int) -> str:
    payload = item.get("payload")
    headers = _extract_headers(payload if isinstance(payload, dict) else {})
    labels = item.get("labelIds") or []
    return (
        f"{index}. id={item.get('id', '')} | thread_id={item.get('threadId', '')} | "
        f"labels={labels} | subject={headers.get('subject', '')} | "
        f"from={headers.get('from', '')} | to={headers.get('to', '')} | "
        f"date={headers.get('date', '')} | snippet={str(item.get('snippet', '')).strip()}"
    )


async def _fetch_message_metadata(
    client: httpx.AsyncClient,
    *,
    message_id: str,
    access_token: str,
) -> dict[str, Any]:
    response = await client.get(
        f"{GMAIL_MESSAGES_API}/{message_id}",
        params={
            "format": "metadata",
            "metadataHeaders": METADATA_HEADERS,
        },
        headers=_headers(access_token),
    )
    if not response.is_success:
        raise RuntimeError(f"Gmail metadata request failed ({response.status_code}): {response.text[:400]}")
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def search(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    del config
    request = _validate_search_request(arguments)
    access_token = await _get_access_token(context)
    query = _build_search_query(request)

    params: dict[str, Any] = {
        "maxResults": request.page_size,
        "includeSpamTrash": request.include_spam_trash,
    }
    if query:
        params["q"] = query
    if request.page_token:
        params["pageToken"] = request.page_token
    if request.label_ids:
        params["labelIds"] = request.label_ids

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            GMAIL_MESSAGES_API,
            params=params,
            headers=_headers(access_token),
        )
        if not response.is_success:
            raise RuntimeError(f"Gmail search request failed ({response.status_code}): {response.text[:400]}")

        payload = response.json()
        raw_messages = payload.get("messages") if isinstance(payload, dict) else None
        messages = [item for item in raw_messages if isinstance(item, dict)] if isinstance(raw_messages, list) else []

        details: list[dict[str, Any]] = []
        for item in messages:
            message_id = str(item.get("id", "")).strip()
            if message_id:
                details.append(
                    await _fetch_message_metadata(
                        client,
                        message_id=message_id,
                        access_token=access_token,
                    )
                )

    if not details:
        return f"No Gmail messages found for query: {query or '(recent messages)'}"

    lines = [
        "Gmail search results:",
        f"query={query or '(recent messages)'}",
        f"result_count={len(details)}",
        f"next_page_token={payload.get('nextPageToken', '') if isinstance(payload, dict) else ''}",
    ]
    lines.extend(_format_search_result(item, index) for index, item in enumerate(details, start=1))
    return "\n".join(lines)


async def read(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    """Read a Gmail message and return a formatted plain-text representation.
    
        Validates the incoming message request, resolves an OAuth access token for
        the agent owner, and fetches the target Gmail message in `full` format from
        the Gmail messages API. The response payload is inspected for structured
        headers and message body content.
    
        The method extracts common headers such as subject, sender, recipients, cc,
        and date. It attempts to read the message body as plain text first, falls
        back to HTML converted into text, and finally falls back to the Gmail
        snippet if no body content is available. The extracted body is truncated to
        `MAX_READ_CHARACTERS`, and the returned output includes a truncation notice
        when applicable.
    
        Returns a human-readable multiline string containing message metadata and
        body content wrapped in `<body>` tags. If the Gmail API returns a non-dict
        payload, the method returns a simple error string instead.
        """    
    del config
    request = _validate_message_request(arguments)
    access_token = await _get_access_token(context)

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{GMAIL_MESSAGES_API}/{request.message_id}",
            params={"format": "full"},
            headers=_headers(access_token),
        )

    if not response.is_success:
        raise RuntimeError(f"Gmail message request failed ({response.status_code}): {response.text[:400]}")

    payload = response.json()
    if not isinstance(payload, dict):
        return "Invalid Gmail message response."

    message_payload = payload.get("payload")
    if not isinstance(message_payload, dict):
        message_payload = {}

    headers = _extract_headers(message_payload)
    body_text = _extract_body(message_payload) or str(payload.get("snippet", "")).strip()
    body_text, was_truncated = _truncate_text(body_text)

    lines = [
        "Gmail message:",
        f"id={payload.get('id', '')}",
        f"thread_id={payload.get('threadId', '')}",
        f"label_ids={payload.get('labelIds', [])}",
        f"subject={headers.get('subject', '')}",
        f"from={headers.get('from', '')}",
        f"to={headers.get('to', '')}",
        f"cc={headers.get('cc', '')}",
        f"date={headers.get('date', '')}",
        "",
        "<body>",
        body_text,
        "</body>",
    ]
    if was_truncated:
        lines.append(f"[truncated to {MAX_READ_CHARACTERS} characters]")

    return "\n".join(lines)


async def _post_message_action(
    *,
    message_id: str,
    access_token: str,
    action_path: str,
    failure_label: str,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{GMAIL_MESSAGES_API}/{message_id}/{action_path}",
            headers=_headers(access_token),
        )

    if not response.is_success:
        raise RuntimeError(f"{failure_label} failed ({response.status_code}): {response.text[:400]}")

    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _dedupe_preserving_order(values: list[str]) -> tuple[list[str], int]:
    seen: set[str] = set()
    deduped: list[str] = []
    duplicate_count = 0
    for value in values:
        if value in seen:
            duplicate_count += 1
            continue
        seen.add(value)
        deduped.append(value)
    return deduped, duplicate_count


def _chunks(values: list[str], chunk_size: int) -> list[list[str]]:
    return [values[index:index + chunk_size] for index in range(0, len(values), chunk_size)]


async def _batch_modify_messages(
    *,
    message_ids: list[str],
    access_token: str,
    add_label_ids: list[str] | None = None,
    remove_label_ids: list[str] | None = None,
    failure_label: str,
) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{GMAIL_MESSAGES_API}/batchModify",
            headers=_json_headers(access_token),
            json={
                "ids": message_ids,
                "addLabelIds": add_label_ids or [],
                "removeLabelIds": remove_label_ids or [],
            },
        )

    if not response.is_success:
        raise RuntimeError(f"{failure_label} failed ({response.status_code}): {response.text[:400]}")


async def _modify_message_labels(
    *,
    message_id: str,
    access_token: str,
    add_label_ids: list[str] | None = None,
    remove_label_ids: list[str] | None = None,
    failure_label: str,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{GMAIL_MESSAGES_API}/{message_id}/modify",
            headers=_json_headers(access_token),
            json={
                "addLabelIds": add_label_ids or [],
                "removeLabelIds": remove_label_ids or [],
            },
        )

    if not response.is_success:
        raise RuntimeError(f"{failure_label} failed ({response.status_code}): {response.text[:400]}")

    payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def delete(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    """Move a single Gmail message to trash.
    
        Validates the message request, resolves an access token from the runtime
        context, sends the Gmail trash action for the target message, and returns a
        confirmation string containing the message ID.
        """    
    del config
    request = _validate_message_request(arguments)
    access_token = await _get_access_token(context)
    await _post_message_action(
        message_id=request.message_id,
        access_token=access_token,
        action_path="trash",
        failure_label="Gmail trash request",
    )
    return f"Moved Gmail message to trash: [{request.message_id}]"


async def batch_delete(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    """Move multiple Gmail messages to trash in chunked batch requests.

    Validates the batch request, removes duplicate message IDs while preserving
    order, resolves an access token from the runtime context, and sends one or
    more Gmail batchModify requests that add the TRASH label and remove INBOX.
    Returns a summary including processed message count, batch count, and the
    number of duplicate IDs ignored.
    """    
    del config
    request = _validate_batch_message_request(arguments)
    message_ids, duplicate_count = _dedupe_preserving_order(request.message_ids)
    access_token = await _get_access_token(context)
    batches = _chunks(message_ids, request.chunk_size)

    for batch in batches:
        await _batch_modify_messages(
            message_ids=batch,
            access_token=access_token,
            add_label_ids=["TRASH"],
            remove_label_ids=["INBOX"],
            failure_label="Gmail batch trash request",
        )

    return (
        f"Moved {len(message_ids)} Gmail message(s) to trash in {len(batches)} batch request(s). "
        f"duplicate_ids_ignored={duplicate_count}"
    )


async def archive(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    del config
    request = _validate_message_request(arguments)
    access_token = await _get_access_token(context)
    await _modify_message_labels(
        message_id=request.message_id,
        access_token=access_token,
        remove_label_ids=["INBOX"],
        failure_label="Gmail archive request",
    )
    return f"Archived Gmail message: [{request.message_id}]"


async def mark_read(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    del config
    request = _validate_message_request(arguments)
    access_token = await _get_access_token(context)
    await _modify_message_labels(
        message_id=request.message_id,
        access_token=access_token,
        remove_label_ids=["UNREAD"],
        failure_label="Gmail mark read request",
    )
    return f"Marked Gmail message as read: [{request.message_id}]"


async def mark_unread(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    del config
    request = _validate_message_request(arguments)
    access_token = await _get_access_token(context)
    await _modify_message_labels(
        message_id=request.message_id,
        access_token=access_token,
        add_label_ids=["UNREAD"],
        failure_label="Gmail mark unread request",
    )
    return f"Marked Gmail message as unread: [{request.message_id}]"
