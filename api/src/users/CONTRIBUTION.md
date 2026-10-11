# Users Module

Owns `DELETE /users/me`, the start of account deletion. Person records themselves live in `src/identity/`; this module only orchestrates the delete.

## Layout

```text
src/users/
  __init__.py   exports users_router
  router.py     DELETE /users/me and DeleteAccountResponse
```

## Conventions

- The route reads `request.state.user_id` and `user_email`, set by the auth middleware, and returns 401 without them. It does not use `get_principal`: deletion is about the person, not an account role.
- Order matters and is deliberate: (1) `IdentityRepository().mark_inactive(user_id)` blocks re-login and is the only step that fails the request (500); (2) the active Stripe subscription is cancelled, and a failure there is logged and skipped; (3) the `account-deletion-handler` Lambda is invoked asynchronously (`InvocationType="Event"`) to cascade-delete data. A failed invoke is logged only, because the user is already inactive and the cascade can be rerun.
- Config: `settings.account_deletion_lambda_name` (`ACCOUNT_DELETION_LAMBDA_NAME`), default `{environment}-account-deletion-handler`. The Lambda lives in `lambdas/`; see `scripts/DELETE_USER_ACCOUNT_README.md`.
- The subscription lookup is by email (`SubscriptionRepository.get_active_for_user`).

## Testing

There is no `tests/test_users_*.py`. A change here needs one: use `test_client`, `auth_headers`, moto, and patch `StripeService` and `boto3.client`.

```bash
uv run pytest tests/test_users_*.py -q
uv run ruff check src/users && uv run mypy src/users
```

## Do / Don't

- Do keep new deletion steps best-effort after `mark_inactive`, so a user is never left half-deleted and still able to log in.
- Do put data cleanup in the Lambda, not in this request.
- Don't delete data inline here; it can be large and must survive a request timeout.
- Don't log credentials or the Lambda payload beyond the email already logged.
