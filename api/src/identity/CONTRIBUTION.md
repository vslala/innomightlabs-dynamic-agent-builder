# Identity Contribution Guide

`identity/` owns a person who signs in: an immutable `user_id`, an email that can change, and the profile fields that go with them. It is the lowest layer of the account stack: `auth/` creates identities at sign-in, `accounts/` and `iam/` refer to them by `user_id`, and nothing here imports from those modules. Design: `docs/LLD-shared-accounts-and-iam.md`.

## Layout

```text
src/identity/
  __init__.py     re-exports Identity, IdentityStatus, IdentityRepository, EmailTaken, normalize_email
  models.py       Identity dataclass (item shape, pk/sk), IdentityStatus, normalize_email, email_index_key
  repository.py   IdentityRepository (the only reader/writer) and EmailTaken
```

## Conventions

- **Keys.** `Identity#{user_id}` / `Identity#Metadata` is the person. `Email#{normalized_email}` / `Email#Identity` is an index item holding `user_id`. Nothing else is keyed by email.
- **Email uniqueness is a transaction.** `create` writes the index item and the identity in one `transact_write_items`, both conditioned on `attribute_not_exists(pk)`. A cancelled transaction becomes `EmailTaken`. `change_email` moves the index entry and updates the identity in one transaction. Do not replace these with read-then-write.
- **`find_or_create` is race-safe**: on `EmailTaken` it re-reads and returns the winner. Sign-in callers use it, so concurrent first logins give one identity.
- **Never authorize by email.** Tokens carry `sub = user_id` (`auth/jwt_utils.py`). Email is for display and contact. `normalize_email` only lowercases and strips; Gmail dots and `+tags` stay distinct on purpose.
- **Updates go through `_set`**: a single `SET` with `attribute_exists(pk)`, always bumping `updated_at`. Add a field by adding a small named method that calls `_set`.
- **Status.** `IdentityStatus` is `active`, `inactive`, `pending_deletion`. `AuthMiddleware` returns 403 `ACCOUNT_INACTIVE` for anything but `active`.
- **`ttl`** is set only for dev-only local signups (`/auth/local/signup`); it is applied to both the identity and its index item.
- `last_account_id` is the account a request acts in when no `X-Account-Id` header is sent (read by `iam/dependencies.py`).

## How to add a field to Identity

1. Add it to the `Identity` dataclass with a default (`models.py`), and read it in `from_dynamo_item` with `item.get(...)` so old items still load.
2. Add a repository method that calls `_set(user_id, field=value)` if something needs to change it.
3. If it must appear in tokens, change `create_access_token` in `auth/jwt_utils.py`; keep tokens free of anything used for authorization other than `sub`.
4. Add a case to `tests/test_identity.py`.

## Testing

```bash
uv run pytest tests/test_identity.py -q
uv run ruff check src/identity && uv run mypy src/identity
```

Tests use the `dynamodb_table` fixture (moto `mock_aws`, from `tests/conftest.py`), which also seeds identities for `SEEDED_EMAILS` with ids from `tests/mock_data.user_id_for(email)`.

## Do / Don't

- Do key anything a person owns by `user_id`, never email.
- Do keep email-index writes inside the transactions above.
- Do keep this module free of imports from `auth`, `accounts`, `iam`.
- Don't add a second way to look up users; `get` and `find_by_email` are enough.
- Don't normalize emails beyond `normalize_email`; every caller must use that one function.
- Don't log or return `password_hash` / `password_salt`.
