# API Keys Module

Owns the public widget key (`pk_live_...`) of an agent: its allowed origins, the `allow_guests` flag, usage counters, and the optional A2A client secret attached to a key. The key is embedded in web pages, so it identifies an agent and gates origins but is not a secret. `widget/` and `embed/` read keys through `ApiKeyRepository`; the secret keys of the `/v1` API live in `public_api/`, not here.

## Layout

```text
src/apikeys/
  __init__.py      re-exports models and ApiKeyRepository
  models.py        AgentApiKey (item + key shape), request/response models, key and A2A secret generation
  repository.py    ApiKeyRepository: DynamoDB access, A2A secret lookup items
  router.py        /agents/{agent_id}/api-keys CRUD and POST .../{key_id}/a2a-secret
```

## Conventions

- **Split.** Router -> repository -> model. There is no service layer: the router builds or mutates `AgentApiKey` and calls `save`. `PATCH` applies only fields that are not `None`.
- **Keys.** `pk = Agent#{agent_id}`, `sk = ApiKey#{key_id}` (a key lives in its agent's partition, so deleting an agent can sweep them with `delete_all_by_agent`). Lookup by public key uses GSI `gsi2`: `gsi2_pk = ApiKey#{public_key}`, `gsi2_sk = Agent#{agent_id}`. The key shape lives in the model's `pk`/`sk`/`gsi2_*` properties; `find_by_id` repeats the strings, so change both together.
- **A2A secret.** Only the SHA-256 is stored (`a2a_secret_hash`), plus a lookup item `pk = A2ASecret#{hash}`, `sk = A2ASecret#Metadata`. Issuing again rotates: the new lookup item is written first, the old one deleted. `find_by_a2a_secret` re-checks the hash on the key because a stale lookup item can outlive a rotation. The plaintext is returned once.
- **Access.** Routes use `agent_with("apikeys:...")` from `src/agents/access.py`: `ListKeys` (list/get), `CreateKey` (create, update, issue A2A secret), `RevokeKey` (delete). Actions are declared in `src/iam/actions.py`. `created_by` stores `principal.user_id` for audit only; the key acts as the agent's owner.
- **Errors.** Plain `HTTPException(404, "API key not found")`. Delete is idempotent and returns 204.
- **Origins.** `AgentApiKey.is_origin_allowed`: an empty list allows all; a request with no `Origin` is refused once a list is set. The check itself runs in `widget/middleware.py`.
- **`ApiKeyResponse`** must never carry `a2a_secret_hash`. New fields go in `to_dynamo_item`, `from_dynamo_item` (with a default for old items), and `to_response`.

## How to add a key setting

Example: `allow_guests`.

1. Add the field to `AgentApiKey`, `CreateApiKeyRequest`, `UpdateApiKeyRequest` and `ApiKeyResponse` in `models.py`.
2. Map it in `to_dynamo_item` / `from_dynamo_item` (`item.get(..., default)`) and `to_response`.
3. Apply it in `create_api_key` and `update_api_key` in `router.py`.
4. If the widget needs it, read it from `request.state.api_key` in `widget/` or add it to `EmbedBootstrap` in `embed/router.py`. The SPA key form and `spa/embed` types must follow.
5. Add a case to `tests/test_apikeys.py`.

## Testing

```bash
uv run pytest tests/test_apikeys.py -q
uv run ruff check src/apikeys && uv run mypy src/apikeys
```

Tests use the `dynamodb_table` fixture (moto) and `test_client` / `auth_headers` for router calls. Related: `tests/test_embed_router.py` and the widget tests create keys through this router.

## Do / Don't

- Do keep the repository to single-item reads/writes; add a method per access pattern, listed in the class docstring.
- Do hash anything secret before storing it, and return plaintext once.
- Don't treat the public key as a credential: it is visible in page source.
- Don't add a service layer or a generic "key" base class shared with `public_api/keys.py`; the two have different secrets and lifecycles.
- Don't scan for keys: use `pk` or `gsi2`.
