from __future__ import annotations

import base64
import json
from typing import Any

from src.skills.agent2agent_client.models import AgentRef


def encode_agent_ref(ref: AgentRef) -> str:
    payload = json.dumps(
        ref.model_dump(mode="json", exclude_none=True),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_agent_ref(value: str) -> AgentRef:
    padded = value + ("=" * (-len(value) % 4))
    try:
        payload: Any = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception as exc:
        raise ValueError("Invalid agent_ref") from exc
    return AgentRef.model_validate(payload)
