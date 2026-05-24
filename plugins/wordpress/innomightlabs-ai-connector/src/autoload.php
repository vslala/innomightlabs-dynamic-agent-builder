<?php
/**
 * PSR-4 style autoloader for the Innomight Labs AI provider classes.
 *
 * @package InnomightLabsAIConnector
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

spl_autoload_register(
	static function ( string $class ): void {
		$prefix   = 'InnomightLabs\\AiConnector\\';
		$base_dir = __DIR__ . '/';
		$len      = strlen( $prefix );

		if ( 0 !== strncmp( $class, $prefix, $len ) ) {
			return;
		}

		$relative_class = substr( $class, $len );
		$file           = $base_dir . str_replace( '\\', '/', $relative_class ) . '.php';

		if ( file_exists( $file ) ) {
			require $file;
		}
	}
);
