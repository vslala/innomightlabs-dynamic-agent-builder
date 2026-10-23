<?php
/**
 * Remove the plugin's data when it is deleted from the Plugins screen.
 *
 * @package InnomightAISearch
 */

if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {
	exit;
}

/** Delete this plugin's options and hourly-limit counters for the current site. */
function innomight_search_uninstall_site(): void {
	global $wpdb;
	delete_option( 'innomight_search' );
	delete_option( 'innomight_search_secret' );
	// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
	$wpdb->query( $wpdb->prepare( "DELETE FROM {$wpdb->options} WHERE option_name LIKE %s", $wpdb->esc_like( 'innomight_search_quota_' ) . '%' ) );
	wp_unschedule_hook( 'innomight_search_quota_cleanup' );
}

if ( is_multisite() ) {
	foreach ( get_sites( array( 'fields' => 'ids', 'number' => 0 ) ) as $innomight_site_id ) {
		switch_to_blog( (int) $innomight_site_id );
		innomight_search_uninstall_site();
		restore_current_blog();
	}
} else {
	innomight_search_uninstall_site();
}
