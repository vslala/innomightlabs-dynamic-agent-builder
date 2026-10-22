# Social connectors Contribution Guide

`connectors/social/` owns the social accounts an InnomightLabs account has connected, so agents and automations can post
to them. It sits beside `connectors/mcp/`: both connect the person to an outside account through us, and like every
connection they belong to the account (admins connect and disconnect with `settings:Manage`; any member lists them).
Design: [docs/LLD-social-cross-posting.md](../../../../docs/LLD-social-cross-posting.md). Posting is not built yet; today
this package connects, lists and disconnects accounts.

## Layout

```text
src/connectors/social/
  models.py       SocialAccount (DynamoDB item + response), SocialAccountStatus, external_key (uniqueness guard)
  repository.py   SocialAccountRepository: list/get, connect (new or refresh), delete (account + guard in one transaction)
  connect.py      SocialOAuthState, authorize_url_for, complete_social_oauth (the "social" completer)
  router.py       /connectors/social/* (router) and the OAuth callback (public_router)
  networks/
    base.py       SocialNetwork protocol, ConnectedProfile, ConnectError
    __init__.py   NETWORKS, network_for, enabled_networks
    linkedin.py   One strategy per network
```

## Conventions

- **Networks are plug-ins.** Everything that varies by network lives in `networks/<key>.py` behind `SocialNetwork`.
  Nothing outside `networks/` names a network: not the routes, the completer, the SPA, nor the deploy scripts.
- Keys: `pk=Account#{account_id}`, `sk=SocialAccount#{id}`, plus `sk=SocialAccountExternal#{network}#{external_id}` which
  guards one identity to one account. Connecting an identity that is already connected updates it (new token, status
  `active`), so reconnecting never duplicates. Delete removes both items in one transaction.
- Credentials are Fernet-encrypted JSON (`encrypted_credentials`); their shape is the strategy's own. Responses never
  carry them, and nothing logs them.
- The connect flow is the shared handoff (`src/auth/oauth_handoff.py`): the public callback stores nothing and sends the
  code and sealed state to the SPA, which completes it signed in through `POST /connectors/oauth/complete` (flow
  `"social"`). The state carries the user, account, network and PKCE verifier.
- Status shown is `SocialAccount.effective_status`: a token past `token_expires_at` needs reconnecting whatever was stored.
- One callback for every network: `settings.social_oauth_redirect_uri`
  (`{API_BASE_URL}/connectors/social/oauth/callback`); register that with each network's app.

## Add a network

1. Write `networks/<key>.py` implementing `SocialNetwork` (copy `linkedin.py`): `key`, `display_name`, `icon`, `app`,
   `description` (one line the dashboard shows under the name: what the agent will post as), `shares_grant` (true when one sign-in connects several accounts on one token, so disconnecting one keeps the grant for the others), `limits` (`NetworkLimits`), `configured`, `authorize_url`, `complete`, `publish`, `revoke`. `publish` raises `PublishError` with a kind: use `TRANSIENT` only when nothing can have been created, and `UNCERTAIN` for any final create call that timed out or returned 5xx (it is never retried). Take an optional `transport` so tests can answer its endpoints.
2. Add it to `NETWORKS` in `networks/__init__.py`.
3. Add a brand mark `spa/src/assets/connectors/<icon>.svg|png` (and a row in that folder's README).
4. Set `SOCIAL_<APP>_CLIENT_ID` and `SOCIAL_<APP>_CLIENT_SECRET`, where `<APP>` is the strategy's `app` upper-cased
   (`linked_in` -> `SOCIAL_LINKED_IN_...`). `settings.py` and the deploy scripts pick them up by name; the network is
   offered once its client id is set.
5. Add `tests/test_connectors_social_<key>.py` for what is specific to it. `tests/test_connectors_social_network_contract.py`
   already runs every network through the same checks (including that its icon exists).

## Testing

```bash
uv run pytest tests/test_connectors_social.py tests/test_connectors_social_network_contract.py -q
uv run ruff check src/connectors/social && uv run mypy src/connectors/social
```

Tests answer the network with `httpx.MockTransport` (see `FakeLinkedIn`) and swap `networks.NETWORKS` with
`monkeypatch.setattr`; they set `settings.social_apps` rather than environment variables.
