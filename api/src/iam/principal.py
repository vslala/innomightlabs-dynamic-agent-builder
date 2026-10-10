"""The caller of one request as the engine sees it, and how it is loaded. See
docs/LLD-shared-accounts-and-iam.md, "Enforcement in routes" and "Account context and switching".
"""

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Optional

from ..config import settings
from ..db import get_dynamodb_resource
from .actions import ACCOUNT, ResourceRef, describe_action_for
from .engine import Decision, NamedPolicy, evaluate
from .repository import IamRepository
from .service import IamError


@dataclass(frozen=True)
class Principal:
    user_id: str
    account_id: str
    authz_version: int
    group_ids: frozenset[str]
    policies: tuple[NamedPolicy, ...]

    def can(self, action: str, resource: ResourceRef = ResourceRef(ACCOUNT)) -> Decision:
        # Shares (KAN-78) are consulted here once they exist
        return evaluate(self.user_id, action, resource, self.policies)

    def require(self, action: str, resource: ResourceRef = ResourceRef(ACCOUNT)) -> None:
        decision = self.can(action, resource)
        if decision.allowed:
            return
        # Don't reveal that a resource exists to someone who can't even see it
        if resource.id and not self.can(describe_action_for(resource.type), resource).allowed:
            raise IamError(404, "NOT_FOUND", f"{resource.type} not found")
        raise IamError(403, "ACCESS_DENIED", f"You are not allowed {action}", action=action, reason=decision.reason)


class PrincipalCache:
    """A small LRU. It is right across replicas because every request reads the account's current
    `authz_version` first, and an entry for an older version is never hit again."""

    def __init__(self, size: int) -> None:
        self.size = size
        self._entries: OrderedDict[tuple[str, str, int], Principal] = OrderedDict()
        self._lock = Lock()

    def get(self, key: tuple[str, str, int]) -> Optional[Principal]:
        with self._lock:
            principal = self._entries.get(key)
            if principal is not None:
                self._entries.move_to_end(key)
            return principal

    def put(self, principal: Principal) -> None:
        with self._lock:
            self._entries[(principal.account_id, principal.user_id, principal.authz_version)] = principal
            while len(self._entries) > self.size:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


principal_cache = PrincipalCache(settings.authz_cache_size)


def load_principal(user_id: str, account_id: str) -> Principal:
    """Two reads on every request (the account's version and the membership); the rest from the cache."""
    dynamodb = get_dynamodb_resource()
    table = settings.dynamodb_table
    response = dynamodb.batch_get_item(RequestItems={table: {"Keys": [
        {"pk": f"Account#{account_id}", "sk": "Account#Metadata"},
        {"pk": f"Account#{account_id}", "sk": f"Member#{user_id}"},
    ]}})
    items = {item["sk"]: item for item in response["Responses"].get(table, [])}
    account, member = items.get("Account#Metadata"), items.get(f"Member#{user_id}")
    if account is None or member is None or member.get("status", "active") != "active":
        raise IamError(403, "NOT_A_MEMBER", "You are not a member of this account")
    version = int(account.get("authz_version", 1))

    cached = principal_cache.get((account_id, user_id, version))
    if cached is not None:
        return cached
    state = IamRepository().load(account_id)
    if state is None:
        raise IamError(403, "NOT_A_MEMBER", "You are not a member of this account")
    principal = Principal(user_id=user_id, account_id=account_id, authz_version=state.authz_version,
                          group_ids=state.group_ids_of(user_id), policies=state.policies_for(user_id))
    principal_cache.put(principal)
    return principal
