<?php
/**
 * REST API surface for local connector checks.
 *
 * @package InnomightLabsAIConnector
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Admin-only REST endpoints.
 */
final class Innomight_AI_REST_Controller {
	/**
	 * REST namespace.
	 */
	private const NAMESPACE = 'innomight/v1';

	/**
	 * Register routes.
	 *
	 * @return void
	 */
	public static function register_routes(): void {
		register_rest_route(
			self::NAMESPACE,
			'/connection',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => array( self::class, 'get_connection' ),
				'permission_callback' => array( self::class, 'can_manage_options' ),
			)
		);
	}

	/**
	 * Permission check.
	 *
	 * @return bool Whether the current user can manage connector settings.
	 */
	public static function can_manage_options(): bool {
		return current_user_can( 'manage_options' );
	}

	/**
	 * Return connector/backend connection status.
	 *
	 * @return WP_REST_Response
	 */
	public static function get_connection(): WP_REST_Response {
		$client        = new Innomight_AI_Client();
		$health        = $client->health();
		$widget_config = $client->get_widget_config();

		return rest_ensure_response(
			array(
				'api_key'       => array(
					'configured' => null !== innomight_ai_get_api_key(),
					'source'     => innomight_ai_get_api_key_source(),
				),
				'api_base_url'  => array(
					'value'  => innomight_ai_get_api_base_url(),
					'source' => innomight_ai_get_api_base_url_source(),
				),
				'health'        => self::normalize_result( $health ),
				'widget_config' => self::normalize_result( $widget_config ),
			)
		);
	}

	/**
	 * Normalize client result for REST output.
	 *
	 * @param array|WP_Error $result Client result.
	 * @return array Normalized result.
	 */
	private static function normalize_result( $result ): array {
		if ( is_wp_error( $result ) ) {
			return array(
				'ok'      => false,
				'code'    => $result->get_error_code(),
				'message' => $result->get_error_message(),
				'data'    => $result->get_error_data(),
			);
		}

		return array(
			'ok'   => true,
			'data' => $result,
		);
	}
}
