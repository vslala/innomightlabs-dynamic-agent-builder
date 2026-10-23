<?php
/**
 * Innomight Labs Public API client: /v1/agents/{agent_id}/…
 *
 * @package InnomightAISearch
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class Innomight_Search_API {
	public static function base_url(): string {
		$url = defined( 'INNOMIGHT_SEARCH_API_URL' ) ? INNOMIGHT_SEARCH_API_URL : Innomight_Search_Settings::get( 'api_url' );
		return Innomight_Search_Settings::sanitize_api_url( $url );
	}

	/** @return array<string, string> */
	public static function headers(): array {
		return array(
			'Authorization' => 'Bearer ' . (string) Innomight_Search_Settings::secret(),
			'Accept'        => 'application/json',
			'Content-Type'  => 'application/json',
			'User-Agent'    => 'InnomightAISearch/' . INNOMIGHT_SEARCH_VERSION . '; ' . home_url(),
		);
	}

	public static function agent_url( string $path = '' ): string {
		return self::base_url() . '/v1/agents/' . rawurlencode( (string) Innomight_Search_Settings::agent_id() ) . $path;
	}

	/** Verify the secret key against the agent. @return array|WP_Error */
	public static function ping() {
		if ( null === Innomight_Search_Settings::secret() || null === Innomight_Search_Settings::agent_id() ) {
			return new WP_Error( 'innomight_search_unconfigured', __( 'Enter the agent ID and secret key first.', 'innomight-ai-search' ) );
		}
		$response = wp_remote_get( self::agent_url(), array( 'timeout' => 15, 'headers' => self::headers() ) );
		if ( is_wp_error( $response ) ) {
			return $response;
		}
		$code = (int) wp_remote_retrieve_response_code( $response );
		if ( 200 !== $code ) {
			/* translators: %d: HTTP status code. */
			return new WP_Error( 'innomight_search_rejected', sprintf( __( 'The backend answered HTTP %d for this key and agent.', 'innomight-ai-search' ), $code ) );
		}
		return (array) json_decode( wp_remote_retrieve_body( $response ), true );
	}

	/** Start a conversation for one visitor. @return string|WP_Error The conversation id. */
	public static function create_conversation( string $end_user, string $title, string $context ) {
		$response = wp_remote_post(
			self::agent_url( '/conversations' ),
			array(
				'timeout' => 20,
				'headers' => self::headers(),
				'body'    => wp_json_encode( array( 'title' => $title, 'end_user_id' => $end_user, 'context' => $context ) ),
			)
		);
		$code = is_wp_error( $response ) ? 0 : (int) wp_remote_retrieve_response_code( $response );
		$data = is_wp_error( $response ) ? array() : (array) json_decode( wp_remote_retrieve_body( $response ), true );
		$id   = Innomight_Search_Chat::clean_id( $data['conversation_id'] ?? '', 8, 128 );
		if ( 201 !== $code || '' === $id ) {
			do_action( 'innomight_search_error', 'create_conversation', $code );
			return new WP_Error( 'innomight_search_failed', 'The assistant is temporarily unavailable. Please try again later.', array( 'status' => 502 ) );
		}
		return $id;
	}
}
