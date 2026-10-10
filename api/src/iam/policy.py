"""The policy document: IAM's shape, a smaller grammar. See docs/LLD-shared-accounts-and-iam.md.

    {"Version": "2026-10-10",
     "Statement": [{"Sid": "...", "Effect": "Allow" | "Deny", "Action": "agents:*" | [...],
                    "Resource": "*" | "agent/*" | "agent/{id}" | [...], "Condition": {...}}]}

Parsing validates: unknown actions, malformed resources and any condition other than the owner one are
rejected with a message the IAM portal can show. Action patterns are expanded against the catalog when a
document is parsed, so a stored `agents:*` picks up actions added later.
"""

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from .actions import ACCOUNT, RESOURCE_TYPES, ResourceRef, expand

VERSION = "2026-10-10"

OWNER_KEY = "iml:ResourceOwner"
PRINCIPAL_ID = "${iml:PrincipalId}"
# The only condition in v1: the resource belongs to the caller
OWNER_CONDITION = {"StringEquals": {OWNER_KEY: PRINCIPAL_ID}}

_ACTION_PATTERN = re.compile(r"^(\*|[A-Za-z*]+:[A-Za-z*]+)$")
_RESOURCE_PATTERN = re.compile(r"^(?P<type>[a-z][a-z-]*)/(?P<id>\*|[A-Za-z0-9_-]+)$")


def _as_list(value: Any) -> Any:
    return [value] if isinstance(value, str) else value


class Statement(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    sid: Optional[str] = Field(default=None, alias="Sid", max_length=128)
    effect: Literal["Allow", "Deny"] = Field(alias="Effect")
    actions: list[str] = Field(alias="Action", min_length=1)
    resources: list[str] = Field(alias="Resource", min_length=1)
    condition: Optional[dict[str, dict[str, str]]] = Field(default=None, alias="Condition")

    _expanded: frozenset[str] = PrivateAttr(default=frozenset())

    @field_validator("actions", "resources", mode="before")
    @classmethod
    def _one_or_many(cls, value: Any) -> Any:
        return _as_list(value)

    @field_validator("actions")
    @classmethod
    def _known_actions(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            if not _ACTION_PATTERN.match(pattern):
                raise ValueError(f"'{pattern}' is not an action: use service:Verb, with * as a wildcard")
            if not expand(pattern):
                raise ValueError(f"'{pattern}' matches no action")
        return patterns

    @field_validator("resources")
    @classmethod
    def _known_resources(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            if pattern == "*":
                continue
            match = _RESOURCE_PATTERN.match(pattern)
            if not match:
                raise ValueError(f"'{pattern}' is not a resource: use *, type/* or type/id")
            if match["type"] not in RESOURCE_TYPES:
                raise ValueError(f"'{match['type']}' is not a resource type ({', '.join(sorted(RESOURCE_TYPES))})")
        return patterns

    @field_validator("condition")
    @classmethod
    def _owner_condition_only(cls, condition: Optional[dict[str, dict[str, str]]]) -> Optional[dict[str, dict[str, str]]]:
        if condition is not None and condition != OWNER_CONDITION:
            raise ValueError(
                f'The only supported condition is {{"StringEquals": {{"{OWNER_KEY}": "{PRINCIPAL_ID}"}}}}'
            )
        return condition

    def model_post_init(self, __context: Any) -> None:
        self._expanded = frozenset().union(*(expand(pattern) for pattern in self.actions))

    @property
    def expanded_actions(self) -> frozenset[str]:
        """Every concrete action the statement's patterns name."""
        return self._expanded

    def matches(self, action: str, resource: ResourceRef, principal_id: str) -> bool:
        if action not in self._expanded:
            return False
        if not any(_resource_matches(pattern, resource) for pattern in self.resources):
            return False
        # A resource without an owner, such as `*` or the account, never satisfies the owner condition
        return self.condition is None or (resource.owner_id is not None and resource.owner_id == principal_id)


def _resource_matches(pattern: str, resource: ResourceRef) -> bool:
    if pattern == "*":
        return True
    if resource.type == ACCOUNT:
        return False
    pattern_type, pattern_id = pattern.split("/", 1)
    # `agent/*` covers every agent, and agent actions that name none (Create, List)
    return pattern_type == resource.type and (pattern_id == "*" or pattern_id == resource.id)


class PolicyDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    version: Literal["2026-10-10"] = Field(alias="Version")
    statements: list[Statement] = Field(alias="Statement", min_length=1)

    @field_validator("statements", mode="before")
    @classmethod
    def _one_or_many(cls, value: Any) -> Any:
        return [value] if isinstance(value, dict) else value

    def to_json(self) -> dict[str, Any]:
        """The document as written, for storing and showing."""
        return self.model_dump(by_alias=True, exclude_none=True)
