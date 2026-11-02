# Social connectors Contribution Guide

`connectors/social/` owns the social accounts an InnomightLabs account has connected, so agents and automations can post
to them. It sits beside `connectors/mcp/`: both connect the person to an outside account through us, and like every
connection they belong to the account (admins connect and disconnect with `settings:Manage`; any member lists them).
Design: [docs/LLD-social-cross-posting.md](../../../../docs/LLD-social-cross-posting.md), and for Meta's networks
[docs/LLD-meta-social-networks.md](../../../../docs/LLD-meta-social-networks.md). It connects, lists and disconnects
accounts, publishes to them, and reads back a network's own recent posts where the network allows it.

## Layout

```text
src/connectors/social/
  models.py       SocialAccount (DynamoDB item + response), SocialAccountStatus, external_key (uniqueness guard)
  repository.py   SocialAccountRepository: list/get, connect (new or refresh), delete (account + guard in one transaction)
  connect.py      SocialOAuthState, authorize_url_for, complete_social_oauth (the "social" completer)
  router.py       /connectors/social/* (router); the OAuth callback and the post-image route (public_router)
  publisher.py    SocialPublisher: plan, renew tokens (`fresh`), publish each target once
  renditions.py   A post's images once per network; stored behind a sealed, expiring URL for networks that fetch them
  meta_callbacks.py  Meta's deauthorize and data-deletion callbacks (public, checked by signed_request)
  networks/
    base.py       SocialNetwork protocol, ConnectedProfile, ConnectError, NetworkLimits
    __init__.py   NETWORKS, network_for, enabled_networks, networks_of_app
    linkedin.py, linkedin_pages.py, facebook_pages.py, instagram.py, threads.py   One strategy per network
    meta.py       What Meta's networks share: Graph error classification (`graph_call`, `graph_error`), the container wait
    facebook_login.py  The Facebook sign-in Facebook Pages and Instagram share (one app, one grant)
```

## Conventions

- **Networks are plug-ins.** Everything that varies by network lives in `networks/<key>.py` behind `SocialNetwork`.
  Nothing outside `networks/` names a network: not the routes, the completer, the SPA, nor the deploy scripts.
- Keys: `pk=Account#{account_id}`, `sk=SocialAccount#{id}`, plus `sk=SocialAccountExternal#{network}#{external_id}` which
  guards one identity to one account. Connecting an identity that is already connected updates it (new token, status
  `active`), so reconnecting never duplicates. Delete removes both items in one transaction.
- A network that names who granted access (`ConnectedProfile.grant_id`, Meta's app-scoped user id) also gets
  `pk=SocialGrant#{network}#{grant_id}`, `sk=Account#{account_id}#{social_account_id}`, written and deleted in the same
  transactions. `for_grant` finds a grant's accounts across InnomightLabs accounts: Meta's callbacks and disconnect
  (which revokes only when no account of the grant is left, on any network of the same app) use it.
- **Images.** The publisher prepares each network's images once (`Renditions.for_network`). A network whose
  `limits.public_media` is set (Threads, Instagram) gets each image's `url`: a copy in the media bucket, tagged
  `retention=social-rendition` (deleted after 2 days), served by `GET /connectors/social/media/{token}.jpg`. Meta
  can't reach localhost: set `SOCIAL_MEDIA_BASE_URL` to a tunnel to try them locally.
- **Tokens that expire** renew in `fresh_credentials` (Threads); the publisher saves the new one with
  `update_credentials` before using it. Return None when nothing needs renewing.
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
   `description` (one line the dashboard shows under the name: what the agent will post as), `shares_grant` (true when one sign-in connects several accounts on one token, so disconnecting one keeps the grant for the others), `limits` (`NetworkLimits`), `configured`, `authorize_url`, `complete`, `fresh_credentials`, `publish`, `revoke`, and `reads_posts` with `recent_posts` (False, and a `REJECTED` PublishError, when the network can't read the account's posts). A network that names who granted access sets `ConnectedProfile.grant_id`. `publish` raises `PublishError` with a kind: use `TRANSIENT` only when nothing can have been created, and `UNCERTAIN` for any final create call that timed out or returned 5xx (it is never retried). Take an optional `transport` so tests can answer its endpoints.
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
