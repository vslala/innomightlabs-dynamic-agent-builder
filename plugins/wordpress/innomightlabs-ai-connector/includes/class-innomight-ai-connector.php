<?php
/**
 * Connector registration.
 *
 * @package InnomightLabsAIConnector
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Main plugin coordinator.
 */
final class Innomight_AI_Connector {
	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public static function init(): void {
		add_action( 'init', array( self::class, 'register_ai_provider' ), 5 );
		add_action( 'wp_connectors_init', array( self::class, 'register_connector' ) );
		add_action( 'rest_api_init', array( 'Innomight_AI_REST_Controller', 'register_routes' ) );
		add_action( 'admin_menu', array( 'Innomight_AI_Admin', 'register_menu' ) );
		add_action( 'admin_init', array( 'Innomight_AI_Admin', 'register_settings' ) );
		add_filter( 'wpai_preferred_text_models', array( self::class, 'prepend_wpai_preferred_model' ) );
		add_filter( 'wpai_preferred_image_models', array( self::class, 'prepend_wpai_preferred_model' ) );
		add_filter( 'ai_experiments_preferred_models_for_text_generation', array( self::class, 'prepend_wpai_preferred_model' ) );
		add_filter( 'ai_experiments_preferred_image_models', array( self::class, 'prepend_wpai_preferred_model' ) );
	}

	/**
	 * Register the Innomight Labs provider with the WordPress AI Client registry.
	 *
	 * This allows WordPress AI plugins that rely on the AI Client infrastructure
	 * to discover and use Innomight Labs as a supported provider.
	 *
	 * The provider is only registered when both the WordPress AI Client classes
	 * and the Innomight Labs provider class are available. The method also checks
	 * whether the provider has already been registered, preventing duplicate
	 * entries and avoiding unnecessary re-registration work.
	 *
	 * @return void
	 */
	public static function register_ai_provider(): void {
		if ( ! class_exists( 'WordPress\\AiClient\\AiClient' ) || ! class_exists( 'InnomightLabs\\AiConnector\\Provider\\InnomightProvider' ) ) {
			return;
		}

		$registry = \WordPress\AiClient\AiClient::defaultRegistry();
		if ( $registry->hasProvider( 'InnomightLabs\\AiConnector\\Provider\\InnomightProvider' ) || $registry->hasProvider( INNOMIGHT_AI_CONNECTOR_ID ) ) {
			return;
		}

		$registry->registerProvider( 'InnomightLabs\\AiConnector\\Provider\\InnomightProvider' );
	}

	/**
	 * Register Innomight Labs with the WordPress Connectors API.
	 *
	 * @param WP_Connector_Registry $registry Connector registry.
	 * @return void
	 */
	public static function register_connector( WP_Connector_Registry $registry ): void {
		if ( $registry->is_registered( INNOMIGHT_AI_CONNECTOR_ID ) ) {
			return;
		}

		$registry->register(
			INNOMIGHT_AI_CONNECTOR_ID,
			array(
				'name'           => __( 'Innomight Labs', 'innomightlabs-ai-connector' ),
				'description'    => __( 'Connect WordPress to your Innomight Labs AI agent backend.', 'innomightlabs-ai-connector' ),
				'logo_url'       => INNOMIGHT_AI_CONNECTOR_URL . 'assets/logo.svg',
				'type'           => 'ai_provider',
				'authentication' => array(
					'method'          => 'api_key',
					'credentials_url' => 'https://innomightlabs.com/dashboard/api-keys',
					'setting_name'    => INNOMIGHT_AI_API_KEY_OPTION,
					'env_var_name'    => 'INNOMIGHT_API_KEY',
					'constant_name'   => 'INNOMIGHT_API_KEY',
				),
				'plugin'         => array(
					'file' => plugin_basename( INNOMIGHT_AI_CONNECTOR_FILE ),
				),
			)
		);
	}

	/**
	 * Add Innomight Labs to the WordPress AI plugin's preferred model list.
	 *
	 * @param array<int, array{string, string}> $models Preferred provider/model pairs.
	 * @return array<int, array{string, string}> Updated preferred provider/model pairs.
	 */
	public static function prepend_wpai_preferred_model( array $models ): array {
		$innomight_model = array(
			INNOMIGHT_AI_CONNECTOR_ID,
			\InnomightLabs\AiConnector\Metadata\InnomightModelMetadataDirectory::MODEL_ID,
		);

		$models = array_values(
			array_filter(
				$models,
				static function ( $model ) use ( $innomight_model ): bool {
					return ! is_array( $model ) || $model !== $innomight_model;
				}
			)
		);

		array_unshift( $models, $innomight_model );
		return $models;
	}
}
