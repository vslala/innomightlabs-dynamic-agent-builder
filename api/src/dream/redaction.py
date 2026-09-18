"""Secret detection for transcript and memory-action safety gates."""

from __future__ import annotations

import re


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b", re.IGNORECASE)),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("assignment", re.compile(r"(?i)\b(?:api[_\- ]?key|secret|password|passwd|token|credential)\b\s*[:=]\s*\S+")),
)


def redact(text: str) -> tuple[str, list[str]]:
    """Replace detected secrets and return the matching pattern names in declaration order."""
    matches: list[str] = []
    redacted = text
    for name, pattern in SECRET_PATTERNS:
        redacted, count = pattern.subn(f"[REDACTED:{name}]", redacted)
        if count:
            matches.append(name)
    return redacted, matches


def is_safe(text: str) -> bool:
    """Return whether text contains none of the secrets prohibited from durable memory."""
    return not any(pattern.search(text) for _, pattern in SECRET_PATTERNS)
