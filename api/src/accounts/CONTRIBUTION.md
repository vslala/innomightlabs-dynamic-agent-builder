# Accounts Contribution Guide

`accounts/` owns shared accounts and memberships: an account owns resources, billing and quotas; a membership links an identity to an account. What a member may do is not stored here, it comes from `iam/` policies. It also defines `Owner` and `member_partition`, the objects other modules use to key data by account. Design: `docs/LLD-shared-accounts-and-iam.md`.

## Layout

```text
src/accounts/
  __init__.py     public surface: Account, Member, AccountService, Owner, accounts_router, personal_account_id
  models.py       Account and Member dataclasses (item shapes), request/response models, personal_account_id
  owner.py        Owner (account_id, user_id, email) and member_partition(): the keys other modules build on
  repository.py   AccountRepository: account/member reads, create transaction, memberships by person
  service.py      AccountService: create_account, ensure_personal_account, list_accounts
  router.py       /accounts: list, create, switch the active account
```

## Conventions

- **Keys.** `Account#{aid}` / `Account#Metadata` (carries `owner_id` and `authz_version`); `Account#{aid}` / `Member#{uid}` for a membership, with GSI `gsi2`: `Identity#{uid}` / `Membership#{aid}` ("every account of a person"); `Identity#{uid}` / `OwnedAccountCount` counts accounts a person created. Group links share the `Member#` prefix (`Member#{uid}#Group#{gid}`), so `members()` filters out sks containing `#Group#`.
- **Shared vs private data.** An account's shared resources live under `Account#{aid}`; a member's private ones under `Account#{aid}#Member#{uid}` (`owner.member_partition`). Use `Owner.account_pk` / `Owner.member_pk` instead of formatting these strings.
- **Owner.** The creator is `owner_id`, always an admin and never removable (enforced in `iam/models.py` and `IamService.remove_member`). No role is stored on a membership.
- **Personal account.** `personal_account_id(user_id)` is a uuid5 of the user id, so racing or retried sign-ins create exactly one. `ensure_personal_account` runs at every sign-in (`auth/router.py`) and only creates one if the person has no memberships.
- **Atomic create.** `AccountRepository.create` writes account, owner membership and the owned-count increment in one transaction; a cancelled transaction raises `AccountExists`.
- **Writes of permissions are not here.** Groups, policies, attachments and member removal belong to `iam.service`, the only writer of permissions (each write bumps `authz_version`). This repository only reads attachments (`member_policies`) for the access summary.
- **Router.** Takes the caller from `request.state.identity` (set by `AuthMiddleware`); switching accounts calls `iam.principal.load_principal` first, which refuses accounts the caller isn't an active member of (`IamError`, 403 `NOT_A_MEMBER`).
- Member `email` and `name` are copies of the identity's, kept for member lists.

## How to add an account-level endpoint

1. Request/response models in `models.py`.
2. Logic in `AccountService`, I/O in `AccountRepository` (paginate with `_query`).
3. Route in `router.py`, as `list_accounts` does; for permission-gated routes use `Depends(get_principal)` and `principal.require("account:Update")` (see `agent_marketplace/router.py`). The router is already registered in `main.py`.
4. If it changes permissions, put it in `iam/service.py` instead.

## Testing

```bash
uv run pytest tests/test_accounts.py tests/test_account_context.py tests/test_account_settings_access.py -q
uv run ruff check src/accounts && uv run mypy src/accounts
```

`dynamodb_table` (moto) seeds a personal account per seeded user; `tests/mock_data.py` has `account_for`, `owner_for`, `owner_ids`.

## Do / Don't

- Do use `Owner` and `member_partition` for new account-scoped data.
- Do keep multi-item invariants in transactions, as `create` does.
- Don't import `iam.service` here; `models.py` imports only `iam.builtins` for the admin policy name.
- Don't store a role or permission on `Member`.
- Don't add account-level logic to routers; keep it in `AccountService`.
