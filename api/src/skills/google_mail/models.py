from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Optional

from pydantic import BaseModel, Field, StringConstraints, model_validator


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
