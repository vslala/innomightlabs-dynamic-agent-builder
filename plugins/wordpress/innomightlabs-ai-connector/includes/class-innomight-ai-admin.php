<?php
/**
 * Admin screen.
 *
 * @package InnomightLabsAIConnector
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Minimal admin settings page.
 */
final class Innomight_AI_Admin {
	/**
	 * Register settings page.
	 *
	 * @return void
	 */
	public static function register_menu(): void {
		add_options_page(
			__( 'Innomight Labs AI', 'innomightlabs-ai-connector' ),
			__( 'Innomight Labs AI', 'innomightlabs-ai-connector' ),
			'manage_options',
			'innomightlabs-ai-connector',
			array( self::class, 'render_page' )
		);
	}

	/**
	 * Register plugin settings.
	 *
	 * @return void
	 */
	public static function register_settings(): void {
		register_setting(
			'innomight_ai_connector',
			INNOMIGHT_AI_API_BASE_URL_OPTION,
			array(
				'type'              => 'string',
				'sanitize_callback' => array( self::class, 'sanitize_base_url' ),
				'default'           => INNOMIGHT_AI_DEFAULT_API_BASE_URL,
			)
		);
	}

	/**
	 * Sanitize base URL.
	 *
	 * @param string $value Raw setting value.
	 * @return string Sanitized URL.
	 */
	public static function sanitize_base_url( $value ): string {
		$value = is_string( $value ) ? trim( $value ) : '';
		if ( '' === $value ) {
			return INNOMIGHT_AI_DEFAULT_API_BASE_URL;
		}

		return untrailingslashit( esc_url_raw( $value ) );
	}

	/**
	 * Render admin page.
	 *
	 * @return void
	 */
	public static function render_page(): void {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}

		$run_test = isset( $_GET['innomight_test_connection'] ) && check_admin_referer( 'innomight_test_connection' );
		?>
		<div class="wrap">
			<h1><?php esc_html_e( 'Innomight Labs AI Connector', 'innomightlabs-ai-connector' ); ?></h1>

			<p>
				<?php esc_html_e( 'Configure the Innomight Labs widget API key in Settings -> Connectors, then use this page to verify that WordPress can reach the backend.', 'innomightlabs-ai-connector' ); ?>
			</p>

			<table class="widefat striped" style="max-width: 760px;">
				<tbody>
					<tr>
						<th scope="row"><?php esc_html_e( 'Connector ID', 'innomightlabs-ai-connector' ); ?></th>
						<td><code><?php echo esc_html( INNOMIGHT_AI_CONNECTOR_ID ); ?></code></td>
					</tr>
					<tr>
						<th scope="row"><?php esc_html_e( 'API key source', 'innomightlabs-ai-connector' ); ?></th>
						<td><?php echo esc_html( innomight_ai_get_api_key_source() ); ?></td>
					</tr>
					<tr>
						<th scope="row"><?php esc_html_e( 'Backend base URL source', 'innomightlabs-ai-connector' ); ?></th>
						<td><?php echo esc_html( innomight_ai_get_api_base_url_source() ); ?></td>
					</tr>
				</tbody>
			</table>

			<form action="options.php" method="post" style="max-width: 760px; margin-top: 20px;">
				<?php settings_fields( 'innomight_ai_connector' ); ?>
				<table class="form-table" role="presentation">
					<tr>
						<th scope="row">
							<label for="<?php echo esc_attr( INNOMIGHT_AI_API_BASE_URL_OPTION ); ?>">
								<?php esc_html_e( 'Backend base URL', 'innomightlabs-ai-connector' ); ?>
							</label>
						</th>
						<td>
							<input
								name="<?php echo esc_attr( INNOMIGHT_AI_API_BASE_URL_OPTION ); ?>"
								id="<?php echo esc_attr( INNOMIGHT_AI_API_BASE_URL_OPTION ); ?>"
								type="url"
								class="regular-text"
								value="<?php echo esc_attr( innomight_ai_get_api_base_url() ); ?>"
							/>
							<p class="description">
								<?php esc_html_e( 'Use the default production URL unless you are testing against a local, UAT, or staging backend.', 'innomightlabs-ai-connector' ); ?>
							</p>
						</td>
					</tr>
				</table>
				<?php submit_button(); ?>
			</form>

			<p>
				<a class="button button-primary" href="<?php echo esc_url( wp_nonce_url( admin_url( 'options-general.php?page=innomightlabs-ai-connector&innomight_test_connection=1' ), 'innomight_test_connection' ) ); ?>">
					<?php esc_html_e( 'Test connection', 'innomightlabs-ai-connector' ); ?>
				</a>
				<a class="button" href="<?php echo esc_url( admin_url( 'options-general.php?page=connectors' ) ); ?>">
					<?php esc_html_e( 'Open WordPress Connectors', 'innomightlabs-ai-connector' ); ?>
				</a>
			</p>

			<?php
			if ( $run_test ) {
				self::render_connection_test();
			}
			?>
		</div>
		<?php
	}

	/**
	 * Render connection test output.
	 *
	 * @return void
	 */
	private static function render_connection_test(): void {
		$client = new Innomight_AI_Client();
		$health = $client->health();
		$config = $client->get_widget_config();
		?>
		<h2><?php esc_html_e( 'Connection test', 'innomightlabs-ai-connector' ); ?></h2>
		<table class="widefat striped" style="max-width: 760px;">
			<tbody>
				<?php self::render_result_row( __( 'Backend health', 'innomightlabs-ai-connector' ), $health ); ?>
				<?php self::render_result_row( __( 'Widget API key', 'innomightlabs-ai-connector' ), $config ); ?>
			</tbody>
		</table>
		<?php
	}

	/**
	 * Render one result row.
	 *
	 * @param string         $label Result label.
	 * @param array|WP_Error $result Result.
	 * @return void
	 */
	private static function render_result_row( string $label, $result ): void {
		$is_error = is_wp_error( $result );
		$message  = $is_error ? $result->get_error_message() : __( 'OK', 'innomightlabs-ai-connector' );
		?>
		<tr>
			<th scope="row"><?php echo esc_html( $label ); ?></th>
			<td>
				<strong style="color: <?php echo esc_attr( $is_error ? '#b32d2e' : '#008a20' ); ?>">
					<?php echo esc_html( $message ); ?>
				</strong>
			</td>
		</tr>
		<?php
	}
}
