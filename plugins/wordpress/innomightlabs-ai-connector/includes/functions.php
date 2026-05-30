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
 * Resolve the current WordPress post ID for AI Client requests.
 *
 * The WordPress AI plugin invokes abilities through REST requests, where the
 * edited post is commonly only visible in the admin referer.
 *
 * @return int Post ID, or 0 when unavailable.
 */
function innomight_ai_get_current_post_id(): int {
	foreach ( array( 'post_id', 'post_ID', 'post', 'id' ) as $key ) {
		if ( isset( $_REQUEST[ $key ] ) ) { // phpcs:ignore WordPress.Security.NonceVerification.Recommended
			$post_id = absint( wp_unslash( $_REQUEST[ $key ] ) ); // phpcs:ignore WordPress.Security.NonceVerification.Recommended
			if ( $post_id > 0 ) {
				return $post_id;
			}
		}
	}

	$referers = array();
	if ( isset( $_SERVER['HTTP_REFERER'] ) && is_string( $_SERVER['HTTP_REFERER'] ) ) {
		$referers[] = wp_unslash( $_SERVER['HTTP_REFERER'] );
	}
	if ( isset( $_REQUEST['_wp_http_referer'] ) ) { // phpcs:ignore WordPress.Security.NonceVerification.Recommended
		$referers[] = wp_unslash( $_REQUEST['_wp_http_referer'] ); // phpcs:ignore WordPress.Security.NonceVerification.Recommended
	}

	foreach ( $referers as $referer ) {
		$query = wp_parse_url( esc_url_raw( $referer ), PHP_URL_QUERY );
		if ( ! is_string( $query ) || '' === $query ) {
			continue;
		}

		$params = array();
		wp_parse_str( $query, $params );
		if ( isset( $params['post'] ) ) {
			$post_id = absint( $params['post'] );
			if ( $post_id > 0 ) {
				return $post_id;
			}
		}
	}

	$post_id = get_the_ID();
	return $post_id ? absint( $post_id ) : 0;
}

/**
 * Build context sent to the Innomight Labs backend for WordPress AI requests.
 *
 * @return array<string, mixed> Request context.
 */
function innomight_ai_get_wordpress_context(): array {
	$context = array(
		'source'    => 'wordpress_ai_client',
		'site_url'  => home_url(),
		'site_name' => get_bloginfo( 'name' ),
	);

	$post_id = innomight_ai_get_current_post_id();
	if ( $post_id > 0 ) {
		$context['post_id'] = (string) $post_id;

		$post = get_post( $post_id );
		if ( $post instanceof WP_Post ) {
			$context['post_type']  = $post->post_type;
			$context['post_title'] = get_the_title( $post );
			$context['post_url']   = get_permalink( $post );
		}
	}

	return $context;
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

/**
 * Generate an image through the configured Innomight Labs agent.
 *
 * @param string $prompt Image prompt.
 * @param array  $context Optional request context.
 * @param array  $options Optional image options.
 * @return array|WP_Error Backend response.
 */
function innomight_ai_generate_image( string $prompt, array $context = array(), array $options = array() ) {
	$client = new Innomight_AI_Client();
	return $client->generate_image( $prompt, $context, $options );
}

/**
 * Generate an image through the configured Innomight Labs agent using SSE.
 *
 * @param string $prompt Image prompt.
 * @param array  $context Optional request context.
 * @param array  $options Optional image options.
 * @return array|WP_Error Backend response.
 */
function innomight_ai_generate_image_stream( string $prompt, array $context = array(), array $options = array() ) {
	$client = new Innomight_AI_Client();
	return $client->generate_image_stream( $prompt, $context, $options );
}
