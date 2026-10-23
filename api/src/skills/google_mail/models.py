from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import HeaderParser
from typing import Annotated, Any, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator, model_validator


class GoogleMailCredentials(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=1))
    scope: str = ""
    token_type: str = "Bearer"

    def is_expiring_soon(self, refresh_buffer_seconds: int = 60) -> bool:
        now = datetime.now(timezone.utc)
        return (self.expires_at - now).total_seconds() <= refresh_buffer_seconds

    def with_token_response(self, tokens: dict[str, Any]) -> "GoogleMailCredentials":
        access_token = str(tokens.get("access_token") or self.access_token).strip()
        if not access_token:
            raise ValueError("Google Mail token response missing access_token")

        expires_in = int(tokens.get("expires_in") or 3600)
        return GoogleMailCredentials(
            access_token=access_token,
            refresh_token=tokens.get("refresh_token") or self.refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            scope=tokens.get("scope") or self.scope,
            token_type=tokens.get("token_type") or self.token_type or "Bearer",
        )


class GoogleMailMessageRequest(BaseModel):
    message_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class GoogleMailBatchMessageRequest(BaseModel):
    message_ids: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]]
    chunk_size: int = 1000

    @model_validator(mode="after")
    def validate_batch(self) -> "GoogleMailBatchMessageRequest":
        if not self.message_ids:
            raise ValueError("message_ids must contain at least one Gmail message id")
        self.chunk_size = max(1, min(1000, int(self.chunk_size or 1000)))
        return self


class GoogleMailComposeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: list[str] = Field(default_factory=list, max_length=100)
    cc: list[str] = Field(default_factory=list, max_length=100)
    bcc: list[str] = Field(default_factory=list, max_length=100)
    subject: str = Field(max_length=998)
    body: str = Field(max_length=1_000_000)
    html_body: str | None = Field(default=None, max_length=1_000_000)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("subject must not contain control characters")
        return value

    @field_validator("to", "cc", "bcc")
    @classmethod
    def validate_recipients(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip() or len(value) > 998 or any(
                ord(char) < 32 or ord(char) == 127 for char in value
            ):
                raise ValueError("invalid recipient")
            header = HeaderParser(policy=policy.default).parsestr(f"To: {value}\n\n")["To"]
            if header.defects or len(header.addresses) != 1 or any(
                group.display_name is not None for group in header.groups
            ):
                raise ValueError("each recipient must be a single mailbox")
            address = header.addresses[0]
            # Unicode display names are supported, but SMTPUTF8 mailboxes are not.
            if not address.username or not address.addr_spec.isascii() or not re.fullmatch(
                r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+",
                address.domain,
            ):
                raise ValueError("recipient must have a valid ASCII mailbox and domain")
        return values

    @model_validator(mode="after")
    def require_recipient(self) -> "GoogleMailComposeRequest":
        if not (self.to or self.cc or self.bcc):
            raise ValueError("at least one recipient is required")
        return self


class GoogleMailUpdateDraftRequest(GoogleMailComposeRequest):
    draft_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,200}$")]


class GoogleMailSendRequest(GoogleMailComposeRequest):
    confirmed: StrictBool

    @field_validator("confirmed")
    @classmethod
    def require_confirmation(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("sending requires confirmed: true after user approval")
        return value


class GoogleMailSendDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,200}$")]
    confirmed: StrictBool

    @field_validator("confirmed")
    @classmethod
    def require_confirmation(cls, value: bool) -> bool:
        return GoogleMailSendRequest.require_confirmation(value)


class GoogleMailSearchRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True)] = ""
    page_size: int = 10
    recent_20: bool = False
    page_token: Annotated[str, StringConstraints(strip_whitespace=True)] = ""
    start_date: Annotated[str, StringConstraints(strip_whitespace=True)] = ""
    end_date: Annotated[str, StringConstraints(strip_whitespace=True)] = ""
    newer_than: Annotated[str, StringConstraints(strip_whitespace=True)] = ""
    older_than: Annotated[str, StringConstraints(strip_whitespace=True)] = ""
    from_email: Annotated[str, StringConstraints(strip_whitespace=True)] = ""
    to_email: Annotated[str, StringConstraints(strip_whitespace=True)] = ""
    subject: Annotated[str, StringConstraints(strip_whitespace=True)] = ""
    label_ids: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = Field(default_factory=list)
    category: Annotated[str, StringConstraints(strip_whitespace=True)] = ""
    has_attachment: bool = False
    is_unread: bool = False
    include_spam_trash: bool = False

    @model_validator(mode="after")
    def normalize_page_size(self) -> "GoogleMailSearchRequest":
        if self.recent_20:
            self.page_size = 20
        self.page_size = max(1, min(50, int(self.page_size or 10)))
        return self
