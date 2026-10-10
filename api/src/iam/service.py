"""The only code that writes groups, policies, attachments and memberships. See
docs/LLD-shared-accounts-and-iam.md, "Changing permissions safely".

Each change is read, judged and written at one `authz_version`:

1. load the account's IAM state;
2. check the caller may make the change, and that anything it grants is within what they hold (the
   escalation guard);
3. commit, conditional on the version read in step 1, bumping it.

The account's owner is out of reach: nothing is attached to or detached from them, they can't be
removed, and their groups can't take anything away (see `AccountIam.effective_policies`). So the account
always has an admin, without a last-admin rule.
"""

import json
import logging
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import ValidationError

from .actions import ACCOUNT, ResourceRef
from .builtins import BUILTINS, OWNER_ACCESS
from .engine import evaluate
from .guard import ungrantable
from .models import (
    CUSTOM_PREFIX,
    MAX_POLICY_VERSIONS,
    AccountIam,
    Attachment,
    CustomPolicy,
    Group,
    PolicyVersion,
    PrincipalType,
    group_membership_items,
)
from .policy import PolicyDocument
from .repository import ConcurrentChange, IamRepository

log = logging.getLogger(__name__)

# IAM's limit for a managed policy document
MAX_POLICY_CHARS = 6144


class IamError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message, **extra})


def policy_problems(document: dict[str, Any]) -> list[str]:
    """Everything wrong with a policy document, for the editor to show; empty when it is valid."""
    if len(json.dumps(document)) > MAX_POLICY_CHARS:
        return [f"A policy can be at most {MAX_POLICY_CHARS} characters"]
    try:
        PolicyDocument.model_validate(document)
    except ValidationError as error:
        return [f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}" for issue in error.errors()]
    return []


def parse_policy(document: dict[str, Any]) -> PolicyDocument:
    problems = policy_problems(document)
    if problems:
        raise IamError(422, "INVALID_POLICY", "The policy is not valid", errors=problems)
    return PolicyDocument.model_validate(document)


def find_group(state: AccountIam, group_id: str) -> Group:
    group = state.groups.get(group_id)
    if group is None:
        raise IamError(404, "NOT_FOUND", "There is no such group")
    return group


def find_policy(state: AccountIam, policy: str) -> CustomPolicy:
    """A custom policy, named `custom:{policy_id}` or by its id."""
    custom = state.policies.get(policy.removeprefix(CUSTOM_PREFIX))
    if custom is None:
        raise IamError(404, "NOT_FOUND", "There is no such policy")
    return custom


def find_member(state: AccountIam, user_id: str) -> None:
    if user_id not in state.members:
        raise IamError(404, "NOT_FOUND", "There is no such member")


def _not_the_owner(state: AccountIam, principal_type: PrincipalType, principal_id: str) -> None:
    if principal_type == "member" and principal_id == state.owner_id:
        raise IamError(400, "ACCOUNT_OWNER",
                       "The account's owner is always its admin: policies aren't attached to or detached from them")


class IamService:
    def __init__(self, repository: Optional[IamRepository] = None) -> None:
        self.repository = repository or IamRepository()

    def state(self, account_id: str, caller: str) -> AccountIam:
        state = self.repository.load(account_id)
        if state is None or state.members.get(caller) != "active":
            raise IamError(403, "NOT_A_MEMBER", "You are not a member of this account")
        return state

    # Groups

    def create_group(self, account_id: str, caller: str, name: str, description: str = "") -> Group:
        state = self._allowed(account_id, caller, "iam:ManageGroups")
        self._unique_name(name, [group.name for group in state.groups.values()], "group")
        group = Group(name=name, description=description, created_by=caller)
        self._commit(state, put=[group.item(account_id)])
        return group

    def update_group(self, account_id: str, caller: str, group_id: str,
                     name: Optional[str] = None, description: Optional[str] = None) -> Group:
        state = self._allowed(account_id, caller, "iam:ManageGroups")
        group = find_group(state, group_id)
        if name is not None and name.casefold() != group.name.casefold():
            self._unique_name(name, [other.name for other in state.groups.values()], "group")
        changed = Group(name=group.name if name is None else name,
                        description=group.description if description is None else description,
                        created_by=group.created_by, group_id=group.group_id, created_at=group.created_at)
        self._commit(state, put=[changed.item(account_id)])
        return changed

    def delete_group(self, account_id: str, caller: str, group_id: str) -> None:
        """The group, its memberships and its attachments."""
        state = self._allowed(account_id, caller, "iam:ManageGroups")
        group = find_group(state, group_id)
        attachments = state.attachments_of("group", group_id)
        keys = [group.item(account_id), *(a.item(account_id) for a in attachments)]
        for user_id in state.members_of(group_id):
            keys += group_membership_items(account_id, group_id, user_id)
        self._commit(state, delete=keys)

    def add_to_group(self, account_id: str, caller: str, group_id: str, user_id: str) -> None:
        """Joining a group grants its policies, so the caller must hold them, as when attaching."""
        state = self._allowed(account_id, caller, "iam:ManageGroups")
        find_group(state, group_id)
        find_member(state, user_id)
        if (group_id, user_id) in state.group_members:
            return
        for attachment in state.attachments_of("group", group_id):
            named = state.resolve(attachment.policy)
            if named:
                self._within_grants(state, caller, named.document)
        self._commit(state, put=group_membership_items(account_id, group_id, user_id))

    def remove_from_group(self, account_id: str, caller: str, group_id: str, user_id: str) -> None:
        state = self._allowed(account_id, caller, "iam:ManageGroups")
        if (group_id, user_id) not in state.group_members:
            return
        self._commit(state, delete=group_membership_items(account_id, group_id, user_id))

    # Policies

    def create_policy(self, account_id: str, caller: str, name: str, document: dict[str, Any],
                      description: str = "") -> CustomPolicy:
        """Writing a policy grants nothing; attaching it is what the escalation guard judges."""
        state = self._allowed(account_id, caller, "iam:ManagePolicies")
        self._unique_name(name, [*BUILTINS, *(policy.name for policy in state.policies.values())], "policy")
        version = PolicyVersion(version=1, document=parse_policy(document), created_by=caller)
        policy = CustomPolicy(name=name, description=description, created_by=caller,
                              default_version=1, latest_version=1, versions={1: version})
        self._commit(state, put=[policy.item(account_id), version.item(account_id, policy.policy_id)])
        return policy

    def create_version(self, account_id: str, caller: str, policy_ref: str, document: dict[str, Any],
                       set_default: bool) -> CustomPolicy:
        """A new version; past five, the oldest that isn't the default is dropped."""
        state = self._allowed(account_id, caller, "iam:ManagePolicies")
        policy = find_policy(state, policy_ref)
        version = PolicyVersion(version=policy.latest_version + 1, document=parse_policy(document), created_by=caller)
        versions = {**policy.versions, version.version: version}
        dropped = []
        while len(versions) > MAX_POLICY_VERSIONS:
            oldest = min(number for number in versions if number != policy.default_version)
            dropped.append(versions.pop(oldest))
        changed = CustomPolicy(
            name=policy.name, description=policy.description, created_by=policy.created_by,
            default_version=version.version if set_default else policy.default_version,
            latest_version=version.version, versions=versions,
            policy_id=policy.policy_id, created_at=policy.created_at,
        )
        self._judge_policy_change(state, caller, policy, changed)
        self._commit(
            state,
            put=[changed.item(account_id), version.item(account_id, policy.policy_id)],
            delete=[old.item(account_id, policy.policy_id) for old in dropped],
        )
        return changed

    def set_default_version(self, account_id: str, caller: str, policy_ref: str, version: int) -> CustomPolicy:
        """How a policy is rolled back (or forward) to a version it still has."""
        state = self._allowed(account_id, caller, "iam:ManagePolicies")
        policy = find_policy(state, policy_ref)
        if version not in policy.versions:
            raise IamError(404, "NOT_FOUND", f"The policy has no version {version}")
        changed = CustomPolicy(
            name=policy.name, description=policy.description, created_by=policy.created_by,
            default_version=version, latest_version=policy.latest_version, versions=policy.versions,
            policy_id=policy.policy_id, created_at=policy.created_at,
        )
        self._judge_policy_change(state, caller, policy, changed)
        self._commit(state, put=[changed.item(account_id)])
        return changed

    def delete_policy(self, account_id: str, caller: str, policy_ref: str) -> None:
        state = self._allowed(account_id, caller, "iam:ManagePolicies")
        policy = find_policy(state, policy_ref)
        if any(attachment.policy == policy.ref for attachment in state.attachments.values()):
            raise IamError(409, "POLICY_ATTACHED", "Detach the policy everywhere before deleting it")
        self._commit(state, delete=[policy.item(account_id),
                                    *(version.item(account_id, policy.policy_id) for version in policy.versions.values())])

    # Attachments

    def attach(self, account_id: str, caller: str, principal_type: PrincipalType, principal_id: str,
               policy: str) -> Attachment:
        state = self._allowed(account_id, caller, "iam:AttachPolicies")
        self._principal(state, principal_type, principal_id)
        _not_the_owner(state, principal_type, principal_id)
        if policy == OWNER_ACCESS.name:
            raise IamError(400, "IMPLICIT_POLICY", "OwnerAccess applies to every member and can't be attached")
        named = state.resolve(policy)
        if named is None:
            raise IamError(404, "NOT_FOUND", f"There is no policy {policy}")
        attachment = Attachment(principal_type=principal_type, principal_id=principal_id, policy=policy,
                                attached_by=caller)
        if attachment.sk in state.attachments:
            return state.attachments[attachment.sk]
        self._within_grants(state, caller, named.document)
        self._commit(state, put=[attachment.item(account_id)])
        return attachment

    def detach(self, account_id: str, caller: str, principal_type: PrincipalType, principal_id: str,
               policy: str) -> None:
        state = self._allowed(account_id, caller, "iam:AttachPolicies")
        _not_the_owner(state, principal_type, principal_id)
        sk = Attachment(principal_type=principal_type, principal_id=principal_id, policy=policy, attached_by="").sk
        if sk not in state.attachments:
            return
        self._commit(state, delete=[state.attachments[sk].item(account_id)])

    # Members

    def remove_member(self, account_id: str, caller: str, user_id: str) -> None:
        """
        The membership, its group memberships and attachments; never the identity or its other accounts.
        Resources the member owns are transferred or deleted first (KAN-83).
        """
        state = self._allowed(account_id, caller, "iam:ManageMembers")
        find_member(state, user_id)
        if user_id == state.owner_id:
            raise IamError(409, "ACCOUNT_OWNER", "The account's owner can't be removed from it")
        attachments = state.attachments_of("member", user_id)
        groups = state.group_ids_of(user_id)
        keys = [{"pk": f"Account#{account_id}", "sk": f"Member#{user_id}"},
                *(attachment.item(account_id) for attachment in attachments)]
        for group_id in groups:
            keys += group_membership_items(account_id, group_id, user_id)
        self._commit(state, delete=keys)
        log.info("Removed member %s from account %s", user_id, account_id)

    # The rules

    def _allowed(self, account_id: str, caller: str, action: str) -> AccountIam:
        state = self.state(account_id, caller)
        decision = evaluate(caller, action, ResourceRef(ACCOUNT), state.policies_for(caller))
        if not decision.allowed:
            raise IamError(403, "ACCESS_DENIED", f"You are not allowed {action}", action=action,
                           reason=decision.reason)
        return state

    def _within_grants(self, state: AccountIam, caller: str, document: PolicyDocument) -> None:
        missing = ungrantable(state.policies_for(caller), document)
        if missing:
            raise IamError(403, "ESCALATION", "You can only grant permissions you hold yourself", missing=missing)

    def _judge_policy_change(self, state: AccountIam, caller: str, before: CustomPolicy,
                             after: CustomPolicy) -> None:
        """A change to an attached policy's default changes what everyone it's attached to may do."""
        if after.default_version == before.default_version:
            return
        if not any(attachment.policy == before.ref for attachment in state.attachments.values()):
            return
        self._within_grants(state, caller, after.document)

    def _commit(self, state: AccountIam, **change: Any) -> None:
        try:
            self.repository.commit(state, **change)
        except ConcurrentChange as error:
            raise IamError(409, "CONFLICT", "Permissions changed while saving; try again") from error

    @staticmethod
    def _unique_name(name: str, taken: list[str], kind: str) -> None:
        if name.casefold() in {other.casefold() for other in taken}:
            raise IamError(409, "NAME_TAKEN", f"There is already a {kind} named {name}")

    def _principal(self, state: AccountIam, principal_type: PrincipalType, principal_id: str) -> None:
        if principal_type == "group":
            find_group(state, principal_id)
        else:
            find_member(state, principal_id)
