# A2A Contribution Guide

`a2a/` implements the Agent2Agent protocol for agents with Agent2Agent enabled (`is_agent2agent_enabled`): public agent cards and discovery, an OAuth client-credentials token endpoint, and invocation (JSON-RPC and HTTP+JSON) that runs the agent and records tasks. Callers authenticate with an agent API key's A2A secret, not a user session.

## Layout

```text
src/a2a/
  models.py      Protocol models (card, message, task, status, security schemes); A2ATask with to/from_dynamo_item
  repository.py  A2ATaskRepository
  auth.py        require_a2a_client(scopes): FastAPI dependency returning the AgentApiKey
  oauth.py       Token issue/validate (JWT), scopes, metadata, bearer challenge
  service.py     A2ADiscoveryService (cards, listing) and A2AInvocationService (send, stream, tasks)
  router.py      /a2a/* routes
```

## Conventions

- Tasks: `pk=A2A#Agent#{agent_id}`, `sk=Task#{task_id}`, optional `ttl`. Listing filters on `entity_type=A2ATask` and the client key id; results sorted by `created_at` in Python.
- Auth: the bearer is either an A2A access token (a JWT signed with `settings.jwt_secret`, scopes `A2A_SCOPE_MESSAGE` / `A2A_SCOPE_TASKS`) or the key's A2A secret (also accepted in `X-API-Key`). Never accept the public widget key. The key must be active, belong to the path's agent, and the agent must still be enabled, else 404. Declare scopes per route with `require_a2a_client({...})`.
- Requests act as the agent's owner (`owner_of(agent)`), with actor kind `ActorKind.A2A` and `actor_id=a2a:{key_id}`. Conversations are deterministic per client key and context id (`_conversation_id`).
- Protocol field names are camelCase aliases in `models.py`; keep Python names snake_case and use the alias.
- Settings: `a2a_supported_protocols`, `a2a_primary_protocol`, `a2a_oauth_access_token_ttl_seconds` in `config/settings.py`.
- Text from agents (name, description) is sanitised with `_sanitize_text` before going into public cards.

## Add an A2A operation

1. Add request/response models to `models.py` with aliases from the spec.
2. Add the method to `A2AInvocationService` (state transitions saved through `task_repository`).
3. Add the route in `router.py` with the narrowest scope dependency (`A2A_MESSAGE_CLIENT` or `A2A_TASK_CLIENT`); for JSON-RPC also add the method to the dispatch in the `/a2a/agents/{agent_id}` handler, returning `_jsonrpc_error` on bad params.
4. Test in `tests/test_a2a_invocation.py`.

## Testing

```bash
uv run pytest tests/test_a2a_*.py -q
uv run ruff check src/a2a && uv run mypy src/a2a
```

Fixtures: `dynamodb_table`, `test_client`; stub the agent architecture so no LLM is called. `test_a2a_agent_card_validator.py` checks cards against the spec shape; run it after any card change.

## Do / Don't

- Do keep authentication in `auth.py` and authorisation of scopes in the route dependency.
- Do return the same 404 for disabled, missing and foreign agents.
- Don't put credentials in task records, logs or cards.
- Don't add a protocol binding "for later"; `A2AStringList`-style helpers stay with what the cards declare.
