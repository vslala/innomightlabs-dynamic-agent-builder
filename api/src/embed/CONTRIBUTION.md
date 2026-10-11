# Embed Module

Serves `GET /embed/{public_key}`, the HTML shell the `embed.js` loader puts in an iframe on a customer's page. The shell comes from the API, not the CDN, so each key gets its own `frame-ancestors` policy built from its allowed origins, and the app's `/widget/*` calls are same-origin. The app itself (`app.js`, `app.css`) is built in `spa/embed/` and served from `settings.widget_cdn_url`. Design: `docs/LLD-public-api-and-embeddable-widget.md` (Part 2).

## Layout

```text
src/embed/
  __init__.py   exports embed_router
  router.py     EmbedBootstrap, embed_csp, render_shell, the unavailable page, the route
```

## Conventions

- **No auth, no IAM.** The route is public. It looks up the key (`ApiKeyRepository.find_by_public_key`) and the agent (`AgentRepository.get`) and answers with a neutral 404 page (`_unavailable`) for an unknown or inactive key or missing agent, without saying which.
- **Bootstrap.** Everything the iframe app needs before its first request is inlined as JSON in `<script id="innomight-bootstrap">`. Trusted settings such as `allow_guests` belong here, never in the URL fragment, which the host page controls. The JSON has `<` escaped so it cannot close the tag; names are passed through `html.escape`.
- **CSP.** `embed_csp` is the single place the policy is built. An empty `allowed_origins` becomes `frame-ancestors *`. Scripts and styles are limited to the CDN; `connect-src 'self'`.
- **Headers.** `_COMMON_HEADERS` (`no-store`, `nosniff`, referrer policy) go on every response.
- **Settings.** `widget_cdn_url` and `api_base_url` come from `src/config/settings.py` (`WIDGET_CDN_URL`).

## How to add a bootstrap field

1. Add it to `EmbedBootstrap` with a default so the SPA tolerates older shells.
2. Fill it in `embed_shell` from the key or agent.
3. Read it in `spa/embed` (see `spa/embed/AGENTS.md`).
4. Extend `tests/test_embed_router.py`; its `_bootstrap(page)` helper parses the JSON.

## Testing

```bash
uv run pytest tests/test_embed_router.py -q
uv run ruff check src/embed && uv run mypy src/embed
```

The tests use `test_client` and `auth_headers`, and create agents and keys through the real routers.

## Do / Don't

- Do put only data safe for any visitor into the bootstrap; it is visible in page source.
- Do change CSP in `embed_csp` and test the resulting header.
- Don't render the shell with a template engine or add inline scripts; the CSP forbids them.
- Don't differentiate "no such key" from "disabled key" in the response.
