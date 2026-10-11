# IAM Contribution Guide

`iam/` decides who may do what inside one account, modelled on AWS IAM: an action catalog, policy documents, built-in and custom policies attached to members and groups, per-resource shares, and an escalation guard. Routes ask a `Principal` (`require`/`can`); the engine answers. Design and rationale: `docs/LLD-shared-accounts-and-iam.md`.

## Layout

```text
src/iam/
  __init__.py       re-exports the pure engine: CATALOG, evaluate, PolicyDocument, ResourceRef, ...
  actions.py        the action catalog (`_service(...)` lines), ResourceRef, expand(), describe/share action lookups
  policy.py         policy document grammar (Statement, PolicyDocument) and its validation
  builtins.py       OwnerAccess, MemberAccess, AdministratorAccess, ViewOnlyAccess
  engine.py         evaluate(): explicit Deny > Allow/share > implicit deny. Pure, no I/O
  guard.py          ungrantable(): you can only grant what you hold. Pure
  models.py         stored items (Group, CustomPolicy, PolicyVersion, Attachment) and AccountIam state
  repository.py     IamRepository: load an account's IAM state, commit() with authz_version check
  service.py        IamService: groups, policies, attachments, member removal; IamError
  shares.py         ResourceShare items, ShareRepository, ShareService, presets, RESOLVERS
  principal.py      Principal (can/require), LRU PrincipalCache, load_principal()
  dependencies.py   get_principal / get_owner FastAPI dependencies, X-Account-Id
  router.py         /iam API (capabilities, members, groups, policies, attachments, effective policies)
  shares_router.py  /{agents|knowledge-bases|automations|kits}/{id}/shares routes
  invitations/      token lifecycle, delivery, membership acceptance (own CONTRIBUTION.md)
  schemas.py        request/response models for the two routers
```

## Conventions

- **Pure core, I/O at the edges.** `actions`, `policy`, `builtins`, `engine`, `guard` use only the stdlib and pydantic and are tested with tables. I/O lives in `repository`, `shares`, `principal`.
- **Keys** (all in the account partition `Account#{aid}`; see `models.py`): `Group#{gid}`, `GroupMember#{gid}#{uid}` and `Member#{uid}#Group#{gid}` (both halves written together), `Policy#{pid}` and `Policy#{pid}#v{n}` (max 5 versions, document stored as JSON text), `Attachment#{member|group}#{id}#{policy}` (policy is a built-in name or `custom:{pid}`), `Share#{type}#{rid}#{member|group}#{id}` with GSI `gsi2` `Account#{aid}#Grantee#...` for "shared with me". Shares use their own sk prefix so listing a resource type never returns them.
- **Every permission write goes through `IamRepository.commit`**, which bumps `Account.authz_version` in the same transaction, conditional on the version that was read. A lost race raises `ConcurrentChange`, which `IamService.commit` turns into `IamError` 409 `CONFLICT`. A transaction holds at most 99 changed items.
- **Cache.** `load_principal` reads two items per request (account version, membership) and uses `principal_cache` keyed by `(account, user, authz_version)`. Because versions only go up, stale entries are never hit. Tests must clear it (the `mock_aws_context` fixture does).
- **Decision order**: any matching Deny refuses; else an Allow or a share permits; else refused. `OwnerAccess` (`Condition: iml:ResourceOwner = ${iml:PrincipalId}`) is implicit for everyone, which is what keeps resources private. The account owner always holds AdministratorAccess and no Deny applies to them (`AccountIam.effective_policies`). Admins hold no `Get/Update/...` contents actions on others' resources.
- **Errors.** Raise `IamError(status, code, message, **extra)` (an `HTTPException`): `NOT_A_MEMBER` 403, `ACCESS_DENIED` 403, `NOT_FOUND` 404, `ESCALATION` 403, `CONFLICT` 409, `NAME_TAKEN` 409, `ACCOUNT_OWNER` 409. `Principal.require` returns 404 instead of 403 when the caller couldn't even `Describe` the resource.
- **UI capabilities.** `GET /iam/capabilities` returns `can_list_members` and `can_invite` from the authenticated account principal's decisions for `iam:ListMembers` and `iam:Invite`. These flags are presentation affordances, not authorization for future writes. The phased scope is in `docs/LLD-account-invitations.md`; token delivery and acceptance are implemented in `invitations/`, while permission presets remain deferred. Conditional invitation writes use the same version-checked commit boundary.
- **Routes.** Reads in `router.py` call `principal.require(action)` then load state; writes are judged again in `IamService._allowed` against the state they change, and `_within_grants` applies the guard.
- **Using it from another module**: `principal: Principal = Depends(get_principal)` and `principal.require("agents:Create", ResourceRef("agent"))` (see `agent_marketplace/router.py`); `owner: Owner = Depends(get_owner)` for keys. `get_principal` resolves `X-Account-Id`, else the identity's `last_account_id`, else the oldest active membership.

## How to add an IAM action

1. Add a `_service(...)` line (or verbs) to `CATALOG` in `actions.py`. Verbs that read or change inside a resource go in `contents=`; `Create/List/Describe/Delete/Transfer/Share` are `_OWNED` metadata. Account-wide services use `ACCOUNT`.
2. Wildcards (`agents:*`) pick it up automatically; check `builtins.py` still gives each built-in what it should.
3. If it is shareable, add it to the right `PRESETS` tuple in `shares.py` (never `Delete`, `Transfer`, `Share`).
4. Call it from the route: `principal.require("agents:Chat", ResourceRef("agent", id, owner_id))`. `evaluate` raises `ValueError` if the action doesn't apply to that resource type.
5. Add a row to `tests/test_iam_engine.py`.

To make a new resource type shareable: add its `_OWNED` service, a `PRESETS` entry in `shares.py`, and a collection in `shares_router.COLLECTIONS`. Then register a resolver from the resource's own `access.py`: `RESOLVERS["agent"] = _resolve` in `agents/access.py` is the model; `kit`, `knowledge-base` and `automation` do the same in `blueprints/`, `knowledge/` and `automations/`.

## Testing

```bash
uv run pytest tests/test_iam_*.py tests/test_accounts.py -q
uv run ruff check src/iam && uv run mypy src/iam
```

`test_iam_engine.py` and `test_iam_guard.py` need no AWS. `test_iam_service.py` and `test_iam_shares.py` use the `dynamodb_table` fixture (moto).

## Do / Don't

- Do keep the engine and guard pure; pass data in.
- Do commit permission changes only via `IamRepository.commit`.
- Do return 404, not 403, for what the caller can't see.
- Don't check a role or email in a route; ask `principal.require`.
- Don't add policy conditions beyond the owner one without updating `policy.py` validation and the LLD.
- Don't cache a `Principal` anywhere but `principal_cache`.
- Don't write groups, policies or attachments from `accounts/`.
