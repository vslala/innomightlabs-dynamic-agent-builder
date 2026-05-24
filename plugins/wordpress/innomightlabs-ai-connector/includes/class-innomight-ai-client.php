<?php
/**
 * Innomight Labs backend HTTP client.
 *
 * @package InnomightLabsAIConnector
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Minimal WordPress HTTP API wrapper for the Innomight Labs backend.
 */
final class Innomight_AI_Client {
	/**
	 * Backend base URL.
	 *
	 * @var string
	 */
	private string $base_url;

	/**
	 * Constructor.
	 *
	 * @param string|null $base_url Optional backend base URL.
	 */
	public function __construct( ?string $base_url = null ) {
		$this->base_url = untrailingslashit( $base_url ?: innomight_ai_get_api_base_url() );
	}

	/**
	 * Check backend health.
	 *
	 * @return array|WP_Error Backend response.
	 */
	public function health() {
		return $this->request(
			'GET',
			'/health',
			array(),
			array(
				'requires_api_key' => false,
				'timeout'          => 10,
			)
		);
	}

	/**
	 * Fetch widget configuration for the configured widget API key.
	 *
	 * @return array|WP_Error Backend response.
	 */
	public function get_widget_config() {
		return $this->request( 'GET', '/widget/config' );
	}

	/**
	 * Send a request to the Innomight Labs backend.
	 *
	 * @param string $method HTTP method.
	 * @param string $path Relative backend path.
	 * @param array  $body JSON body.
	 * @param array  $args Request args.
	 * @return array|WP_Error Parsed response.
	 */
	public function request( string $method, string $path, array $body = array(), array $args = array() ) {
		$method           = strtoupper( $method );
		$requires_api_key = array_key_exists( 'requires_api_key', $args ) ? (bool) $args['requires_api_key'] : true;
		$api_key          = innomight_ai_get_api_key();

		if ( $requires_api_key && null === $api_key ) {
			return new WP_Error(
				'innomight_missing_api_key',
				__( 'Innomight Labs API key is not configured.', 'innomightlabs-ai-connector' )
			);
		}

		$path = '/' . ltrim( $path, '/' );
		if ( false !== strpos( $path, '://' ) ) {
			return new WP_Error(
				'innomight_invalid_path',
				__( 'Innomight Labs request path must be relative.', 'innomightlabs-ai-connector' )
			);
		}

		$headers = array(
			'Accept'     => 'application/json',
			'Origin'     => home_url(),
			'User-Agent' => $this->user_agent(),
		);

		if ( null !== $api_key ) {
			$headers['X-API-Key'] = $api_key;
		}

		if ( ! empty( $args['visitor_token'] ) && is_string( $args['visitor_token'] ) ) {
			$headers['Authorization'] = 'Bearer ' . trim( $args['visitor_token'] );
		}

		if ( 'GET' !== $method ) {
			$headers['Content-Type'] = 'application/json';
		}

		if ( ! empty( $args['headers'] ) && is_array( $args['headers'] ) ) {
			$headers = array_merge( $headers, $args['headers'] );
		}

		$request_args = array(
			'method'  => $method,
			'timeout' => isset( $args['timeout'] ) ? absint( $args['timeout'] ) : 30,
			'headers' => $headers,
		);

		if ( 'GET' !== $method ) {
			$request_args['body'] = wp_json_encode( $body );
		}

		$response = wp_remote_request( $this->base_url . $path, $request_args );
		if ( is_wp_error( $response ) ) {
			return $response;
		}

		return $this->parse_response( $response );
	}

	/**
	 * Parse a WordPress HTTP API response.
	 *
	 * @param array $response HTTP response.
	 * @return array|WP_Error Parsed response.
	 */
	private function parse_response( array $response ) {
		$status       = wp_remote_retrieve_response_code( $response );
		$content_type = wp_remote_retrieve_header( $response, 'content-type' );
		$raw_body     = wp_remote_retrieve_body( $response );

		$data = null;
		if ( '' !== trim( $raw_body ) && ( ! is_string( $content_type ) || false !== strpos( $content_type, 'json' ) ) ) {
			$data = json_decode( $raw_body, true );
		}

		if ( $status < 200 || $status >= 300 ) {
			return new WP_Error(
				'innomight_api_error',
				$this->error_message( $data, $status ),
				array(
					'status' => $status,
				)
			);
		}

		if ( is_array( $data ) ) {
			return $data;
		}

		return array(
			'status' => $status,
			'body'   => $raw_body,
		);
	}

	/**
	 * Extract a useful error message without leaking credentials.
	 *
	 * @param mixed $data Parsed response data.
	 * @param int   $status HTTP status code.
	 * @return string Error message.
	 */
	private function error_message( $data, int $status ): string {
		if ( is_array( $data ) ) {
			if ( isset( $data['detail'] ) && is_string( $data['detail'] ) ) {
				return sanitize_text_field( $data['detail'] );
			}

			if ( isset( $data['error']['message'] ) && is_string( $data['error']['message'] ) ) {
				return sanitize_text_field( $data['error']['message'] );
			}
		}

		return sprintf(
			/* translators: %d: HTTP status code. */
			__( 'Innomight Labs API request failed with HTTP status %d.', 'innomightlabs-ai-connector' ),
			$status
		);
	}

	/**
	 * Build plugin user agent.
	 *
	 * @return string User agent.
	 */
	private function user_agent(): string {
		return sprintf(
			'InnomightAIConnector/%s; WordPress/%s; %s',
			INNOMIGHT_AI_CONNECTOR_VERSION,
			get_bloginfo( 'version' ),
			home_url()
		);
	}
}
