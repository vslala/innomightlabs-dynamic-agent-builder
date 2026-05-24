<?php
/**
 * Plugin Name: Innomight Labs AI Connector
 * Description: Registers Innomight Labs as a WordPress AI Connector and exposes helpers for invoking the Innomight Labs API.
 * Version: 0.1.0
 * Requires at least: 7.0
 * Requires PHP: 7.4
 * Author: Innomight Labs
 * Text Domain: innomightlabs-ai-connector
 *
 * @package InnomightLabsAIConnector
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'INNOMIGHT_AI_CONNECTOR_VERSION', '0.1.0' );
define( 'INNOMIGHT_AI_CONNECTOR_FILE', __FILE__ );
define( 'INNOMIGHT_AI_CONNECTOR_DIR', plugin_dir_path( __FILE__ ) );
define( 'INNOMIGHT_AI_CONNECTOR_URL', plugin_dir_url( __FILE__ ) );
define( 'INNOMIGHT_AI_CONNECTOR_ID', 'innomight' );
define( 'INNOMIGHT_AI_API_KEY_OPTION', 'connectors_ai_innomight_api_key' );
define( 'INNOMIGHT_AI_API_BASE_URL_OPTION', 'innomight_ai_api_base_url' );
define( 'INNOMIGHT_AI_DEFAULT_API_BASE_URL', 'https://api.innomightlabs.com' );

require_once INNOMIGHT_AI_CONNECTOR_DIR . 'includes/functions.php';
require_once INNOMIGHT_AI_CONNECTOR_DIR . 'src/autoload.php';
require_once INNOMIGHT_AI_CONNECTOR_DIR . 'includes/class-innomight-ai-client.php';
require_once INNOMIGHT_AI_CONNECTOR_DIR . 'includes/class-innomight-ai-rest-controller.php';
require_once INNOMIGHT_AI_CONNECTOR_DIR . 'includes/class-innomight-ai-admin.php';
require_once INNOMIGHT_AI_CONNECTOR_DIR . 'includes/class-innomight-ai-connector.php';

Innomight_AI_Connector::init();
