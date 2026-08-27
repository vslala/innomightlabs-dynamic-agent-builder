from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from uuid import uuid4


OUTPUT_TTL_MINUTES = 30


@dataclass
class StoredOutput:
    output_id: str
    owner_email: str
    installed_skill_id: str
    content: str
    created_at: datetime
    expires_at: datetime


_OUTPUTS: dict[str, StoredOutput] = {}


def store_output(*, owner_email: str, installed_skill_id: str, content: str) -> StoredOutput:
    prune_expired()
    now = datetime.now(timezone.utc)
    output = StoredOutput(
        output_id=f"awsout_{uuid4().hex}",
        owner_email=owner_email,
        installed_skill_id=installed_skill_id,
        content=content,
        created_at=now,
        expires_at=now + timedelta(minutes=OUTPUT_TTL_MINUTES),
    )
    _OUTPUTS[output.output_id] = output
    return output


def read_page(
    *,
    output_id: str,
    owner_email: str,
    installed_skill_id: str,
    page: int,
    page_size_chars: int,
) -> dict[str, object]:
    prune_expired()
    output = _OUTPUTS.get(output_id)
    if not output or output.owner_email != owner_email or output.installed_skill_id != installed_skill_id:
        raise ValueError("Output not found")

    total_pages = max(1, ceil(len(output.content) / page_size_chars))
    if page > total_pages:
        raise ValueError(f"Output page {page} is out of range. Total pages: {total_pages}")

    start = (page - 1) * page_size_chars
    end = start + page_size_chars
    has_next = page < total_pages
    return {
        "ok": True,
        "output_id": output.output_id,
        "page": page,
        "page_size_chars": page_size_chars,
        "total_pages": total_pages,
        "content": output.content[start:end],
        "has_next": has_next,
        "next_page": page + 1 if has_next else None,
        "expires_at": output.expires_at.isoformat(),
    }


def prune_expired() -> None:
    now = datetime.now(timezone.utc)
    expired = [output_id for output_id, output in _OUTPUTS.items() if output.expires_at <= now]
    for output_id in expired:
        _OUTPUTS.pop(output_id, None)
