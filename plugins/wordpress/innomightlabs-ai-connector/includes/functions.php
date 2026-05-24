<?php
/**
 * Public helper functions for the Innomight Labs AI Connector.
 *
 * @package InnomightLabsAIConnector
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Resolve the configured Innomight Labs widget API key.
 *
 * Resolution order matches WordPress connector credential priority:
 * environment variable, PHP constant, database option.
 *
 * @return string|null API key when configured.
 */
function innomight_ai_get_api_key(): ?string {
	$env = getenv( 'INNOMIGHT_API_KEY' );
	if ( is_string( $env ) && '' !== trim( $env ) ) {
		return trim( $env );
	}

	if ( defined( 'INNOMIGHT_API_KEY' ) && is_string( INNOMIGHT_API_KEY ) && '' !== trim( INNOMIGHT_API_KEY ) ) {
		return trim( INNOMIGHT_API_KEY );
	}

	$option = get_option( INNOMIGHT_AI_API_KEY_OPTION );
	if ( is_string( $option ) && '' !== trim( $option ) ) {
		return trim( $option );
	}

	return null;
}

/**
 * Identify where the API key is configured without exposing its value.
 *
 * @return string One of env, constant, database, or missing.
 */
function innomight_ai_get_api_key_source(): string {
	$env = getenv( 'INNOMIGHT_API_KEY' );
	if ( is_string( $env ) && '' !== trim( $env ) ) {
		return 'env';
	}

	if ( defined( 'INNOMIGHT_API_KEY' ) && is_string( INNOMIGHT_API_KEY ) && '' !== trim( INNOMIGHT_API_KEY ) ) {
		return 'constant';
	}

	$option = get_option( INNOMIGHT_AI_API_KEY_OPTION );
	if ( is_string( $option ) && '' !== trim( $option ) ) {
		return 'database';
	}

	return 'missing';
}

/**
 * Resolve the Innomight Labs backend base URL.
 *
 * @return string Base URL without a trailing slash.
 */
function innomight_ai_get_api_base_url(): string {
	$env = getenv( 'INNOMIGHT_API_BASE_URL' );
	if ( is_string( $env ) && '' !== trim( $env ) ) {
		return untrailingslashit( esc_url_raw( trim( $env ) ) );
	}

	if ( defined( 'INNOMIGHT_API_BASE_URL' ) && is_string( INNOMIGHT_API_BASE_URL ) && '' !== trim( INNOMIGHT_API_BASE_URL ) ) {
		return untrailingslashit( esc_url_raw( trim( INNOMIGHT_API_BASE_URL ) ) );
	}

	$option = get_option( INNOMIGHT_AI_API_BASE_URL_OPTION );
	if ( is_string( $option ) && '' !== trim( $option ) ) {
		return untrailingslashit( esc_url_raw( trim( $option ) ) );
	}

	return INNOMIGHT_AI_DEFAULT_API_BASE_URL;
}

/**
 * Identify where the base URL is configured.
 *
 * @return string One of env, constant, database, or default.
 */
function innomight_ai_get_api_base_url_source(): string {
	$env = getenv( 'INNOMIGHT_API_BASE_URL' );
	if ( is_string( $env ) && '' !== trim( $env ) ) {
		return 'env';
	}

	if ( defined( 'INNOMIGHT_API_BASE_URL' ) && is_string( INNOMIGHT_API_BASE_URL ) && '' !== trim( INNOMIGHT_API_BASE_URL ) ) {
		return 'constant';
	}

	$option = get_option( INNOMIGHT_AI_API_BASE_URL_OPTION );
	if ( is_string( $option ) && '' !== trim( $option ) ) {
		return 'database';
	}

	return 'default';
}

/**
 * Invoke the Innomight Labs backend with the configured widget API key.
 *
 * Other plugins can use this as the minimal integration surface.
 *
 * @param string $method HTTP method.
 * @param string $path Relative backend path, for example /widget/config.
 * @param array  $body JSON request body.
 * @param array  $args Additional request args. Supports headers, timeout, and visitor_token.
 * @return array|WP_Error Parsed JSON response, raw body wrapper, or error.
 */
function innomight_ai_request( string $method, string $path, array $body = array(), array $args = array() ) {
	$client = new Innomight_AI_Client();
	return $client->request( $method, $path, $body, $args );
}

/**
 * Fetch backend widget configuration for the configured API key.
 *
 * @return array|WP_Error Backend response.
 */
function innomight_ai_get_widget_config() {
	$client = new Innomight_AI_Client();
	return $client->get_widget_config();
}
