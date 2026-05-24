# Innomight AI Connector Plugin LLD

Date: 2026-05-23

## Goal

Ship a small WordPress plugin that makes Innomight Labs available as an AI Connector in WordPress 7.0, lets a site admin configure credentials once, and exposes a fluent WordPress-side experience on top of the existing Innomight backend at `/Users/vslala/src/code/projects/innomightlabs/innomightlabs-prod/api`.

The fastest useful launch is not a full AI feature suite. It is:

1. A WordPress 7.0 Connector registration for `innomight`.
2. A credential resolver that follows WordPress connector precedence: environment variable, PHP constant, database option.
3. A thin backend client using the existing widget API contracts.
4. A small authenticated REST proxy for connection testing, chat setup, and streaming-compatible admin UI.
5. A simple, polished admin page that points users to Settings -> Connectors and can run a connection test.

Provider adapter support for the WordPress AI Client should be a phase-2 task unless another plugin already needs to call Innomight through `wp_ai_client_prompt()` on day one.

## Research Summary

Primary source findings:

- WordPress 7.0 introduced the Connectors API as metadata, discovery, credential management, and admin UI infrastructure for external services, initially focused on AI providers. Source: https://make.wordpress.org/core/2026/03/18/introducing-the-connectors-api-in-wordpress-7-0/
- A connector is registered on `wp_connectors_init` with metadata such as `name`, `description`, `logo_url`, `type`, `authentication`, and optional `plugin.file`. The Settings -> Connectors screen renders these fields. Source: https://make.wordpress.org/core/2026/03/18/introducing-the-connectors-api-in-wordpress-7-0/
- API key connectors use this lookup priority: environment variable, PHP constant, then database setting. Database keys are masked in UI but not encrypted yet. Source: https://make.wordpress.org/core/2026/03/18/introducing-the-connectors-api-in-wordpress-7-0/
- Connector IDs must be lowercase alphanumeric, underscore, or hyphen. Hyphens are allowed, but generated setting names normalize hyphens to underscores. Source: https://make.wordpress.org/core/2026/03/18/introducing-the-connectors-api-in-wordpress-7-0/
- AI providers registered with the PHP AI Client default registry can be auto-discovered as connectors, so a mature provider adapter can reduce manual connector code later. Source: https://make.wordpress.org/core/2026/03/18/introducing-the-connectors-api-in-wordpress-7-0/
- The WordPress AI Client provides `wp_ai_client_prompt()` and support checks such as `is_supported_for_text_generation()`. It is useful for provider-agnostic plugins, but provider implementation adds more surface area than needed for the first Innomight launch. Source: https://raw.githubusercontent.com/WordPress/wp-ai-client/trunk/README.md
- The lower-level PHP AI Client is a Composer package and not itself a WordPress plugin. It offers provider-agnostic prompt APIs and lifecycle events. Source: https://raw.githubusercontent.com/WordPress/php-ai-client/trunk/README.md

Local backend findings:

- `/api/src/apikeys/router.py` manages agent-scoped API keys under `/agents/{agent_id}/api-keys`. API keys are public integration keys with format `pk_live_{32 hex chars}` and are intended for widget authentication.
- `/api/src/apikeys/models.py` stores API keys with `agent_id`, `allowed_origins`, `is_active`, `created_by`, and request counters. Empty `allowed_origins` means allow all origins.
- `/api/src/widget/middleware.py` validates widget requests with the `X-API-Key` header, resolves the target `agent_id`, checks request `Origin` against the key allowlist, and increments usage.
- `/api/src/widget/router.py` exposes the existing runtime surface: `GET /widget/config`, Google visitor auth, `POST /widget/conversations`, `GET /widget/conversations`, `POST /widget/conversations/{conversation_id}/messages`, and `GET /widget/conversations/{conversation_id}/messages`.
- Widget message sending returns Server-Sent Events and runs the selected agent architecture through `architecture.handle_message(...)`.
- `/api/src/skills/wordpress_search` already lets Innomight agents search a configured WordPress site through the standard WP REST API. The plugin can make this easier to configure later instead of duplicating search logic.

VS Code plugin findings:

- `/plugins/ide/vscode/innomightlabs-code-assist/src/config/extensionConfigService.ts` stores the backend base URL and API key, with the API key in VS Code secret storage.
- `/plugins/ide/vscode/innomightlabs-code-assist/src/auth/authService.ts` performs Google login through `/widget/auth/google`, stores the visitor JWT and refresh token, and refreshes sessions through `/widget/auth/refresh`.
- `/plugins/ide/vscode/innomightlabs-code-assist/src/integrations/widget/widgetApiClient.ts` is the best client-contract reference: it calls `/widget/config`, `/widget/conversations`, and `/widget/conversations/{id}/messages`, then parses SSE events and extracts `AGENT_RESPONSE_TO_USER` content.
- The WordPress plugin should reuse these contracts but make setup more fluent for WordPress admins: one connector credential, automatic site-origin guidance, clearer health checks, and an admin chat tester that hides OAuth/session mechanics where possible.

## Product Scope

### Version 0.1: Speed Launch

The first plugin version should do four things well:

- Register an `innomight` connector for the Innomight AI service.
- Let admins configure the Innomight widget/API key through the connector screen or deployment config.
- Call the existing Innomight backend widget endpoints with WordPress-native HTTP functions.
- Provide a test endpoint/page so a site owner can verify the connection without writing code.

### Explicit Non-Goals for 0.1

- Do not store long-term memory in WordPress.
- Do not implement embeddings or vector search in the plugin.
- Do not build a polished chat widget yet.
- Do not sync all content by default.
- Do not depend on Composer unless the first implementation truly needs it.
- Do not block launch on a full WordPress AI Client provider adapter.
- Do not create a parallel backend API contract unless the current widget contract blocks a required WordPress UX.

## Proposed Repository Structure

The current plugin directory is empty. Start with a conventional, low-dependency WordPress plugin layout:

```text
innomightlabs-ai-connector/
|-- innomightlabs-ai-connector.php
|-- assets/
|   `-- logo.svg
|-- docs/
|   `-- innomight-ai-connector-lld.md
|-- includes/
|   |-- class-innomight-ai-connector.php
|   |-- class-innomight-ai-client.php
|   |-- class-innomight-ai-rest-controller.php
|   `-- functions.php
|-- readme.txt
`-- tests/
    `-- bootstrap.php
```

Avoid Composer and autoloading in 0.1 unless testing infrastructure already requires it. Four required PHP files are faster to inspect, package, and debug for WordPress users.

## Connector Design

Use connector ID `innomight`. It is short, valid, and maps cleanly to:

- Environment variable: `INNOMIGHT_API_KEY`
- PHP constant: `INNOMIGHT_API_KEY`
- Database setting: `connectors_ai_innomight_api_key`

In 0.1 this value should be the existing backend's agent API key, e.g. `pk_live_...`, created from `/agents/{agent_id}/api-keys`. Keep the generic `INNOMIGHT_API_KEY` name so the connector remains stable if the backend later adds a WordPress-specific key type.

Register during `wp_connectors_init`.

Important implementation detail: do not use `type => 'ai_provider'` until the plugin also registers an Innomight provider with the WordPress AI Client registry. WordPress core validates saved API keys for `ai_provider` connectors by calling the AI Client provider registry. Without a real AI Client provider adapter, the Settings -> Connectors UI rejects valid Innomight widget API keys before saving them. Use a service connector type for the 0.1 credential connector, then promote it to `ai_provider` with the phase-2 provider adapter.

```php
add_action(
	'wp_connectors_init',
	static function ( WP_Connector_Registry $registry ): void {
		$registry->register(
			'innomight',
			array(
				'name'           => __( 'Innomight Labs', 'innomightlabs-ai-connector' ),
				'description'    => __( 'Long-term memory AI agent API for WordPress sites.', 'innomightlabs-ai-connector' ),
				'logo_url'       => plugins_url( 'assets/logo.svg', INNOMIGHT_AI_CONNECTOR_FILE ),
				'type'           => 'ai_service',
				'authentication' => array(
					'method'          => 'api_key',
					'credentials_url' => 'https://innomightlabs.com/dashboard/api-keys',
					'setting_name'    => 'connectors_ai_innomight_api_key',
					'env_var_name'    => 'INNOMIGHT_API_KEY',
					'constant_name'   => 'INNOMIGHT_API_KEY',
				),
				'plugin'         => array(
					'file' => plugin_basename( INNOMIGHT_AI_CONNECTOR_FILE ),
				),
			)
		);
	}
);
```

Implementation note: guard connector registration with `class_exists( 'WP_Connector_Registry' )` only if this callback can run on pre-7.0 sites. The plugin header should still set `Requires at least: 7.0`.

## Credential Resolver

Add one resolver function and use it everywhere:

```php
function innomight_ai_get_api_key(): ?string {
	$env = getenv( 'INNOMIGHT_API_KEY' );
	if ( is_string( $env ) && '' !== $env ) {
		return $env;
	}

	if ( defined( 'INNOMIGHT_API_KEY' ) && '' !== INNOMIGHT_API_KEY ) {
		return INNOMIGHT_API_KEY;
	}

	$option = get_option( 'connectors_ai_innomight_api_key' );
	return is_string( $option ) && '' !== $option ? $option : null;
}
```

Do not log the API key. Error messages should say the key is missing or invalid without echoing the value.

## Backend Client

Create `Innomight_AI_Client` as a small wrapper around `wp_remote_request()` for the existing FastAPI backend.

Initial endpoints:

- `GET /health`: validate the configured backend base URL is reachable.
- `GET /widget/config`: validate the configured `X-API-Key` and discover `agent_id`, `agent_name`, welcome message, and theme.
- `POST /widget/conversations`: create a conversation. For admin-side testing, this requires a visitor JWT with the current backend contract.
- `POST /widget/conversations/{conversation_id}/messages`: send a message and parse the SSE response.
- Later: add backend endpoints for WordPress content sync if the existing `wordpress_search` skill is not enough.

Client behavior:

- Use `wp_remote_get()`, `wp_remote_post()`, and `wp_remote_request()`.
- Use a default timeout of 30 seconds for chat and 10 seconds for health.
- Include a plugin user agent, e.g. `InnomightAIConnector/0.1.0; WordPress/<version>`.
- Send `X-API-Key: <connector key>` to widget endpoints, matching the VS Code plugin and backend middleware.
- Send `Authorization: Bearer <visitor JWT>` only for endpoints that currently require visitor auth.
- Return `WP_Error` on missing key, missing base URL, network failure, invalid JSON, SSE parse failure, or non-2xx status.
- Treat 401/403 as setup errors and surface an admin-readable message about key validity or allowed origins.
- Include `Origin: home_url()` when useful for local validation against `allowed_origins`.

The plugin needs a backend base URL setting because connector credentials only store the key. Keep this in a normal WordPress option, not in the connector credential:

```php
const INNOMIGHT_AI_DEFAULT_API_BASE_URL = 'https://api.innomightlabs.com';
const INNOMIGHT_AI_API_BASE_URL_OPTION = 'innomight_ai_api_base_url';
```

Allow `INNOMIGHT_API_BASE_URL` as an environment variable or PHP constant for staging/UAT.

Example shape:

```php
final class Innomight_AI_Client {
	private string $base_url;

	public function __construct( ?string $base_url = null ) {
		$base_url = $base_url ?: innomight_ai_get_api_base_url();
		$this->base_url = untrailingslashit( $base_url );
	}

	public function get_widget_config() {
		return $this->request(
			'GET',
			'/widget/config'
		);
	}

	public function create_conversation( string $title, string $visitor_token ) {
		return $this->request(
			'POST',
			'/widget/conversations',
			array( 'title' => $title ),
			$visitor_token
		);
	}

	private function request( string $method, string $path, array $body = array(), ?string $visitor_token = null ) {
		$api_key = innomight_ai_get_api_key();
		if ( null === $api_key ) {
			return new WP_Error( 'innomight_missing_api_key', __( 'Innomight API key is not configured.', 'innomightlabs-ai-connector' ) );
		}

		$headers = array(
			'Accept'       => 'application/json',
			'Content-Type' => 'application/json',
			'X-API-Key'   => $api_key,
			'Origin'      => home_url(),
		);

		if ( null !== $visitor_token ) {
			$headers['Authorization'] = 'Bearer ' . $visitor_token;
		}

		$response = wp_remote_request(
			$this->base_url . $path,
			array(
				'method'  => $method,
				'timeout' => 30,
				'headers' => $headers,
				'body'    => 'GET' === $method ? null : wp_json_encode( $body ),
			)
		);

		if ( is_wp_error( $response ) ) {
			return $response;
		}

		$status = wp_remote_retrieve_response_code( $response );
		$data   = json_decode( wp_remote_retrieve_body( $response ), true );

		if ( $status < 200 || $status >= 300 ) {
			return new WP_Error(
				'innomight_api_error',
				is_array( $data ) && isset( $data['error']['message'] ) ? sanitize_text_field( $data['error']['message'] ) : __( 'Innomight API request failed.', 'innomightlabs-ai-connector' ),
				array( 'status' => $status )
			);
		}

		return is_array( $data ) ? $data : array();
	}
}
```

## REST API

Add `Innomight_AI_REST_Controller` with namespace `innomight/v1`.

Routes for 0.1:

- `GET /wp-json/innomight/v1/connection`: returns whether the key is configured and whether the backend health/config checks pass.
- `POST /wp-json/innomight/v1/chat`: sends a message to Innomight and returns the response.
- `GET /wp-json/innomight/v1/oauth/callback`: optional admin callback target for the existing backend Google OAuth flow if 0.1 uses real visitor sessions.

Permissions:

- Use `current_user_can( 'manage_options' )` for both endpoints in 0.1.
- Do not expose arbitrary prompt execution to public visitors in the first release.
- Validate and sanitize the `message` parameter.
- Cap request message size, e.g. 8,000 characters.

## Admin UI

For speed, build a PHP-rendered admin page under Settings -> Innomight AI, with small progressive-enhancement JavaScript for connection tests and chat testing.

It should show:

- Connector registration status.
- API key source: environment variable, PHP constant, database, or missing. Do not show the key.
- Backend base URL source: environment variable, PHP constant, database option, or default.
- Link to Settings -> Connectors.
- Link to the Innomight dashboard page for creating an agent API key.
- A connection test button that calls `/health` and `/widget/config`.
- A compact chat tester once auth/session handling is decided.

Avoid a React build for 0.1. The page should still feel fluent: one setup checklist, inline status, no raw JSON, clear next action, and no separate custom credentials form duplicating Settings -> Connectors.

## WordPress Visitor/Auth Strategy

The VS Code plugin uses Google OAuth through `/widget/auth/google` and stores the returned visitor JWT. WordPress needs a smoother version of that flow.

Recommended 0.1 approach:

- Use connector key only for `GET /widget/config` and setup validation.
- For admin chat testing, initially add a "Sign in to test chat" button that opens the existing `/widget/auth/google` flow with a redirect back to a WordPress admin callback route.
- Store the visitor token in user meta for the current admin user, not in a global option.
- Store refresh token in user meta only if required, and provide a clear disconnect action.
- Keep public visitor chat out of 0.1 unless the backend already has the desired site visitor auth behavior.

More fluent phase-1.1 improvement:

- Add a backend endpoint for trusted WordPress admin test sessions, e.g. `POST /widget/admin-session`, authenticated by `X-API-Key`, that returns a short-lived visitor token for a synthetic visitor like `wordpress-admin:{site_url}:{user_id}`.
- This avoids forcing a WordPress admin through Google OAuth just to test the agent.
- Scope the endpoint to active API keys and origin allowlist, and keep expiration short.

## Backend Changes To Consider

The plugin can launch against the current backend, but these small backend additions would make it much more fluent:

- `GET /widget/connection`: combines `/health` and `/widget/config`, returns key status, agent summary, origin allowlist status, and actionable setup errors.
- `POST /widget/admin-session`: creates a short-lived admin/test visitor JWT for the configured agent.
- `POST /widget/conversations/{conversation_id}/messages:json`: non-streaming response for simple PHP admin tests and WordPress REST proxy usage.
- Better config response: return the actual agent display name instead of API key name when possible.
- Optional WordPress integration metadata on API keys: intended site URL, plugin version, and integration name.

These are not required for the connector registration itself, but they reduce plugin code and make setup feel first-party.

## WordPress AI Client Provider Adapter

Phase 2 should implement Innomight as a provider for the WordPress/PHP AI Client if ecosystem compatibility becomes important.

Expected work:

- Study the current provider interfaces in the exact WordPress 7.0 / PHP AI Client version.
- Implement a provider class that maps text generation requests to a model-like backend endpoint. Do not map generic AI Client calls directly to `/widget/conversations/{id}/messages` unless conversation/session semantics are intentionally part of the provider behavior.
- Register the provider with `AiClient::defaultRegistry()` on `init`.
- Provide provider metadata so Connectors can auto-discover the provider.
- Ensure credentials are wired through the same connector setting.

Defer this until the SaaS API has a stable provider-compatible contract. A memory-agent response endpoint is not always the same abstraction as generic text generation.

## Launch Sequence

### Day 1

- Create plugin header, constants, includes, and activation compatibility check.
- Register the connector.
- Add credential resolver.
- Add client class with `health()` and `get_widget_config()`.
- Add REST `connection` endpoint.
- Add a very small admin page.

### Day 2

- Add REST chat test endpoint, either backed by existing Google visitor session or by the proposed backend admin-session endpoint.
- Add admin connection test.
- Add basic WordPress Coding Standards pass if project tooling is available.
- Package as a zip and test on a clean WordPress 7.0 install.

### Day 3

- Add readme, screenshots, and installation instructions.
- Test these credential modes:
  - `INNOMIGHT_API_KEY` environment variable.
  - `define( 'INNOMIGHT_API_KEY', '...' );`
  - Settings -> Connectors database option.
- Test bad key, missing key, backend 500, timeout, invalid JSON, and successful response.
- Tag `0.1.0`.

## Test Plan

Manual tests are acceptable for the first pass because WordPress 7.0 APIs are new and the repo is empty, but add automated tests as soon as a WordPress test harness exists.

Manual matrix:

- Plugin activates on WordPress 7.0.
- Plugin refuses or degrades clearly on pre-7.0.
- Settings -> Connectors shows Innomight Labs card.
- API key source priority is env var, constant, then database option.
- Connection endpoint requires admin capability.
- Chat endpoint requires admin capability.
- Missing key returns `WP_Error`-backed REST error.
- Non-2xx SaaS response maps to a clear REST error.
- API key never appears in HTML, REST output, logs, or exceptions.

Automated unit targets:

- `innomight_ai_get_api_key()` precedence.
- Client response parsing.
- Client error mapping.
- REST permission callbacks.
- REST parameter validation.

## Security Notes

- Database-stored connector API keys are not encrypted in WordPress 7.0; recommend environment variables or constants for production sites.
- Any plugin on the same site may be able to access site-level connector credentials, so Innomight API keys should be scoped per tenant/site and revocable from the SaaS dashboard.
- Do not allow unauthenticated public chat in 0.1. Public chat requires rate limiting, abuse prevention, origin/site binding, and SaaS-side usage limits.
- Do not sync private posts, drafts, customer data, orders, or user metadata until an explicit admin consent and filtering design exists.

## Open API Decisions

The plugin should use the existing backend endpoints first:

```text
GET  https://api.innomightlabs.com/health
GET  https://api.innomightlabs.com/widget/config
GET  https://api.innomightlabs.com/widget/auth/google
POST https://api.innomightlabs.com/widget/auth/refresh
POST https://api.innomightlabs.com/widget/conversations
POST https://api.innomightlabs.com/widget/conversations/{conversation_id}/messages
```

If the backend adds WordPress-specific convenience endpoints, keep the WordPress client isolated so only `Innomight_AI_Client` and the REST controller change.

For a stronger WordPress AI Client provider adapter later, the SaaS should expose a model-like endpoint with request/response fields close to:

```json
{
  "messages": [
    { "role": "user", "content": "..." }
  ],
  "temperature": 0.2,
  "max_tokens": 1024,
  "metadata": {
    "source": "wordpress",
    "site_url": "https://example.com"
  }
}
```

## Recommendation

Build version 0.1 as a thin connector plugin first. It will be easier to launch, easier to debug, and still aligns with WordPress 7.0's standard connector model. After credentials and the SaaS call path work reliably on real WordPress sites, add the AI Client provider adapter and content sync workflows.
