=== Innomight Labs AI Connector ===
Contributors: innomightlabs
Requires at least: 7.0
Requires PHP: 7.4
Stable tag: 0.1.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Registers Innomight Labs as a WordPress AI Connector and exposes helpers for invoking the Innomight Labs backend with a widget API key.

== Description ==

This plugin registers an `innomight` connector for WordPress 7.0. Configure your Innomight Labs widget API key once through Settings -> Connectors, then other plugin code can invoke the backend through the public `innomight_ai_request()` helper.

== Configuration ==

API key resolution order:

1. `INNOMIGHT_API_KEY` environment variable.
2. `INNOMIGHT_API_KEY` PHP constant.
3. `connectors_ai_innomight_api_key` database option managed by WordPress Connectors.

Backend base URL resolution order:

1. `INNOMIGHT_API_BASE_URL` environment variable.
2. `INNOMIGHT_API_BASE_URL` PHP constant.
3. `innomight_ai_api_base_url` WordPress option.
4. `https://api.innomightlabs.com`.

== Developer Usage ==

```php
$response = innomight_ai_request( 'GET', '/widget/config' );

if ( is_wp_error( $response ) ) {
	return;
}
```

== Changelog ==

= 0.1.0 =
* Initial connector registration and backend invocation helpers.
