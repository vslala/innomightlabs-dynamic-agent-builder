<?php
/**
 * Plugin Name:       Innomight AI Search
 * Plugin URI:        https://innomightlabs.com/downloads/plugins/wordpress-ai-search
 * Description:       Add an AI follow-up chat to your site's search results, answered by your Innomight Labs agent and streamed live.
 * Version:           1.0.0
 * Requires at least: 6.3
 * Requires PHP:      7.4
 * Author:            Innomight Labs
 * Author URI:        https://innomightlabs.com/
 * License:           GPL-2.0-or-later
 * License URI:       https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain:       innomight-ai-search
 * Domain Path:       /languages
 *
 * @package InnomightAISearch
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'INNOMIGHT_SEARCH_VERSION', '1.0.0' );
define( 'INNOMIGHT_SEARCH_FILE', __FILE__ );
define( 'INNOMIGHT_SEARCH_DIR', plugin_dir_path( __FILE__ ) );
define( 'INNOMIGHT_SEARCH_URL', plugin_dir_url( __FILE__ ) );

require_once INNOMIGHT_SEARCH_DIR . 'includes/class-innomight-search-settings.php';
require_once INNOMIGHT_SEARCH_DIR . 'includes/class-innomight-search-api.php';
require_once INNOMIGHT_SEARCH_DIR . 'includes/class-innomight-search-chat.php';
require_once INNOMIGHT_SEARCH_DIR . 'includes/class-innomight-search-ui.php';

Innomight_Search_Chat::init();
Innomight_Search_UI::init();
if ( is_admin() ) {
	Innomight_Search_Settings::init();
}
