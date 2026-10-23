<?php
/**
 * Settings: one option array, plus a write-only secret key.
 *
 * @package InnomightAISearch
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class Innomight_Search_Settings {
	public const OPTION        = 'innomight_search';
	public const SECRET_OPTION = 'innomight_search_secret';
	public const DEFAULT_API   = 'https://api.innomightlabs.com';

	public const DEFAULT_INSTRUCTIONS = "You are the search assistant for {site} ({url}). Use your tools to find relevant articles on this site and answer from them. Name the articles you used, with their titles and links. If the site's writing does not cover the question, say so instead of guessing. Keep answers concise and use short paragraphs.\n\nThe reader searched for: {search}";

	/** @return array<string, mixed> */
	public static function defaults(): array {
		return array(
			'enabled'      => 0,
			'agent_id'     => '',
			'api_url'      => self::DEFAULT_API,
			'instructions' => '',
			'placement'    => 'above',
			'title'        => __( 'Ask about this', 'innomight-ai-search' ),
			'intro'        => __( 'Not what you wanted? Ask a follow-up and the assistant will look through the site for you.', 'innomight-ai-search' ),
			'placeholder'  => __( 'Ask a follow-up question…', 'innomight-ai-search' ),
			'suggestions'  => __( "What should I read first?\nSummarise the best match", 'innomight-ai-search' ),
			'disclaimer'   => __( 'AI can make mistakes. Check the linked posts.', 'innomight-ai-search' ),
			'accent'       => '',
		);
	}

	/** @return mixed */
	public static function get( string $key ) {
		$saved    = get_option( self::OPTION, array() );
		$settings = array_merge( self::defaults(), is_array( $saved ) ? $saved : array() );
		return $settings[ $key ] ?? null;
	}

	/** Secret key: environment, constant, then the saved option. It is never printed or sent to a browser. */
	public static function secret(): ?string {
		$env = getenv( 'INNOMIGHT_SEARCH_SECRET_KEY' );
		if ( is_string( $env ) && '' !== trim( $env ) ) {
			return trim( $env );
		}
		if ( defined( 'INNOMIGHT_SEARCH_SECRET_KEY' ) && is_string( INNOMIGHT_SEARCH_SECRET_KEY ) && '' !== trim( INNOMIGHT_SEARCH_SECRET_KEY ) ) {
			return trim( INNOMIGHT_SEARCH_SECRET_KEY );
		}
		$option = get_option( self::SECRET_OPTION );
		return is_string( $option ) && '' !== trim( $option ) ? trim( $option ) : null;
	}

	public static function secret_source(): string {
		$env = getenv( 'INNOMIGHT_SEARCH_SECRET_KEY' );
		if ( is_string( $env ) && '' !== trim( $env ) ) {
			return 'environment';
		}
		if ( defined( 'INNOMIGHT_SEARCH_SECRET_KEY' ) && is_string( INNOMIGHT_SEARCH_SECRET_KEY ) && '' !== trim( INNOMIGHT_SEARCH_SECRET_KEY ) ) {
			return 'constant';
		}
		return null !== self::secret() ? 'saved' : 'missing';
	}

	public static function agent_id(): ?string {
		$id = defined( 'INNOMIGHT_SEARCH_AGENT_ID' ) ? INNOMIGHT_SEARCH_AGENT_ID : self::get( 'agent_id' );
		return is_string( $id ) && preg_match( '/\A[A-Za-z0-9_-]{4,128}\z/', trim( $id ) ) ? trim( $id ) : null;
	}

	/** Chat is on and fully configured. */
	public static function is_ready(): bool {
		return (bool) self::get( 'enabled' ) && null !== self::secret() && null !== self::agent_id();
	}

	/* ------------------------------------------------------------ admin screen */

	public static function init(): void {
		add_action( 'admin_menu', array( self::class, 'menu' ) );
		add_action( 'admin_init', array( self::class, 'register' ) );
		add_filter( 'plugin_action_links_' . plugin_basename( INNOMIGHT_SEARCH_FILE ), array( self::class, 'action_links' ) );
	}

	public static function action_links( array $links ): array {
		array_unshift( $links, '<a href="' . esc_url( admin_url( 'options-general.php?page=innomight-ai-search' ) ) . '">' . esc_html__( 'Settings', 'innomight-ai-search' ) . '</a>' );
		return $links;
	}

	public static function menu(): void {
		add_options_page(
			__( 'Innomight AI Search', 'innomight-ai-search' ),
			__( 'Innomight AI Search', 'innomight-ai-search' ),
			'manage_options',
			'innomight-ai-search',
			array( self::class, 'render' )
		);
	}

	public static function register(): void {
		register_setting(
			'innomight_search',
			self::OPTION,
			array( 'type' => 'array', 'sanitize_callback' => array( self::class, 'sanitize' ), 'default' => self::defaults() )
		);
		register_setting(
			'innomight_search',
			self::SECRET_OPTION,
			array( 'type' => 'string', 'sanitize_callback' => array( self::class, 'sanitize_secret' ), 'default' => '' )
		);
	}

	/** A blank secret field keeps the saved key, so the key is never echoed back into the form. */
	public static function sanitize_secret( $value ): string {
		$value = is_string( $value ) ? trim( $value ) : '';
		if ( '' === $value ) {
			$saved = get_option( self::SECRET_OPTION );
			return is_string( $saved ) ? $saved : '';
		}
		return 0 === strpos( $value, 'sk_live_' ) && preg_match( '/\A[A-Za-z0-9_\-]{12,200}\z/', $value ) ? $value : '';
	}

	/** @param mixed $input */
	public static function sanitize( $input ): array {
		$input    = is_array( $input ) ? $input : array();
		$defaults = self::defaults();
		$out      = array();
		$out['enabled']      = empty( $input['enabled'] ) ? 0 : 1;
		$agent               = isset( $input['agent_id'] ) ? trim( (string) $input['agent_id'] ) : '';
		$out['agent_id']     = preg_match( '/\A[A-Za-z0-9_-]{4,128}\z/', $agent ) ? $agent : '';
		$out['api_url']      = self::sanitize_api_url( $input['api_url'] ?? '' );
		$out['instructions'] = isset( $input['instructions'] ) ? mb_substr( sanitize_textarea_field( (string) $input['instructions'] ), 0, 4000 ) : '';
		$placement           = isset( $input['placement'] ) ? (string) $input['placement'] : 'above';
		$out['placement']    = in_array( $placement, array( 'above', 'below', 'off' ), true ) ? $placement : 'above';
		foreach ( array( 'title', 'placeholder', 'disclaimer' ) as $key ) {
			$out[ $key ] = isset( $input[ $key ] ) ? mb_substr( sanitize_text_field( (string) $input[ $key ] ), 0, 200 ) : $defaults[ $key ];
		}
		foreach ( array( 'intro', 'suggestions' ) as $key ) {
			$out[ $key ] = isset( $input[ $key ] ) ? mb_substr( sanitize_textarea_field( (string) $input[ $key ] ), 0, 1000 ) : $defaults[ $key ];
		}
		$accent        = isset( $input['accent'] ) ? sanitize_hex_color( (string) $input['accent'] ) : '';
		$out['accent'] = $accent ? $accent : '';
		return $out;
	}

	/** HTTPS only, except a local development backend. */
	public static function sanitize_api_url( $value ): string {
		$value = is_string( $value ) ? trim( $value ) : '';
		if ( '' === $value ) {
			return self::DEFAULT_API;
		}
		$url  = esc_url_raw( $value, array( 'https', 'http' ) );
		$host = (string) wp_parse_url( $url, PHP_URL_HOST );
		$ok   = 'https' === wp_parse_url( $url, PHP_URL_SCHEME ) || in_array( $host, array( 'localhost', '127.0.0.1' ), true );
		return $url && $ok ? untrailingslashit( $url ) : self::DEFAULT_API;
	}

	public static function render(): void {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}
		$test = null;
		if ( isset( $_GET['innomight_search_test'] ) && check_admin_referer( 'innomight_search_test' ) ) { // phpcs:ignore WordPress.Security.NonceVerification.Recommended
			$test = Innomight_Search_API::ping();
		}
		$o   = get_option( self::OPTION, array() );
		$o   = array_merge( self::defaults(), is_array( $o ) ? $o : array() );
		$f   = self::OPTION;
		$src = self::secret_source();
		?>
		<div class="wrap">
			<h1><?php esc_html_e( 'Innomight AI Search', 'innomight-ai-search' ); ?></h1>
			<p><?php esc_html_e( 'Visitors search your site as usual, then ask follow-up questions in a chat answered by your Innomight Labs agent. The agent does the searching; this plugin only passes the question and streams the answer back.', 'innomight-ai-search' ); ?></p>

			<form action="options.php" method="post" style="max-width:820px">
				<?php settings_fields( 'innomight_search' ); ?>
				<table class="form-table" role="presentation">
					<tr>
						<th scope="row"><?php esc_html_e( 'Chat', 'innomight-ai-search' ); ?></th>
						<td>
							<label><input type="checkbox" name="<?php echo esc_attr( $f ); ?>[enabled]" value="1" <?php checked( ! empty( $o['enabled'] ) ); ?> /> <?php esc_html_e( 'Let visitors chat with my agent', 'innomight-ai-search' ); ?></label>
							<p class="description"><?php esc_html_e( 'Visitors reach the agent exactly as you configured it: anything it can remember or do (memory, tools, knowledge bases) is available to them, and their questions use your AI allowance. Use an agent meant for the public. Limit: 40 questions per IP and 400 per site per hour.', 'innomight-ai-search' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="innomight-agent"><?php esc_html_e( 'Agent ID', 'innomight-ai-search' ); ?></label></th>
						<td><input id="innomight-agent" class="regular-text code" type="text" name="<?php echo esc_attr( $f ); ?>[agent_id]" value="<?php echo esc_attr( (string) $o['agent_id'] ); ?>" autocomplete="off" /></td>
					</tr>
					<tr>
						<th scope="row"><label for="innomight-secret"><?php esc_html_e( 'Agent secret key', 'innomight-ai-search' ); ?></label></th>
						<td>
							<input id="innomight-secret" class="regular-text code" type="password" name="<?php echo esc_attr( self::SECRET_OPTION ); ?>" value="" placeholder="<?php echo esc_attr( 'missing' !== $src ? '•••••••• (' . $src . ')' : 'sk_live_…' ); ?>" autocomplete="new-password" />
							<p class="description"><?php esc_html_e( 'The sk_live_… key for this agent. It is used only by your server and is never sent to visitors. Leave blank to keep the saved key. You can also define INNOMIGHT_SEARCH_SECRET_KEY as an environment variable or in wp-config.php.', 'innomight-ai-search' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="innomight-instr"><?php esc_html_e( 'Conversation instructions', 'innomight-ai-search' ); ?></label></th>
						<td>
							<textarea id="innomight-instr" class="large-text" rows="6" name="<?php echo esc_attr( $f ); ?>[instructions]" placeholder="<?php echo esc_attr( self::DEFAULT_INSTRUCTIONS ); ?>"><?php echo esc_textarea( (string) $o['instructions'] ); ?></textarea>
							<p class="description"><?php esc_html_e( 'Sent to the agent with every conversation. Placeholders: {site}, {url}, {search}. Leave blank for the default shown above.', 'innomight-ai-search' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="innomight-placement"><?php esc_html_e( 'Search results', 'innomight-ai-search' ); ?></label></th>
						<td>
							<select id="innomight-placement" name="<?php echo esc_attr( $f ); ?>[placement]">
								<option value="above" <?php selected( $o['placement'], 'above' ); ?>><?php esc_html_e( 'Show the chat above the results', 'innomight-ai-search' ); ?></option>
								<option value="below" <?php selected( $o['placement'], 'below' ); ?>><?php esc_html_e( 'Show the chat below the results', 'innomight-ai-search' ); ?></option>
								<option value="off" <?php selected( $o['placement'], 'off' ); ?>><?php esc_html_e( 'Do not add it automatically (use the block or shortcode)', 'innomight-ai-search' ); ?></option>
							</select>
							<p class="description"><?php esc_html_e( 'You can also add the "Innomight AI Search" block or the [innomight_ai_search] shortcode anywhere.', 'innomight-ai-search' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="innomight-title"><?php esc_html_e( 'Title', 'innomight-ai-search' ); ?></label></th>
						<td><input id="innomight-title" class="regular-text" type="text" name="<?php echo esc_attr( $f ); ?>[title]" value="<?php echo esc_attr( (string) $o['title'] ); ?>" /></td>
					</tr>
					<tr>
						<th scope="row"><label for="innomight-intro"><?php esc_html_e( 'Intro line', 'innomight-ai-search' ); ?></label></th>
						<td><textarea id="innomight-intro" class="large-text" rows="2" name="<?php echo esc_attr( $f ); ?>[intro]"><?php echo esc_textarea( (string) $o['intro'] ); ?></textarea></td>
					</tr>
					<tr>
						<th scope="row"><label for="innomight-ph"><?php esc_html_e( 'Input placeholder', 'innomight-ai-search' ); ?></label></th>
						<td><input id="innomight-ph" class="regular-text" type="text" name="<?php echo esc_attr( $f ); ?>[placeholder]" value="<?php echo esc_attr( (string) $o['placeholder'] ); ?>" /></td>
					</tr>
					<tr>
						<th scope="row"><label for="innomight-sug"><?php esc_html_e( 'Starter questions', 'innomight-ai-search' ); ?></label></th>
						<td><textarea id="innomight-sug" class="large-text" rows="3" name="<?php echo esc_attr( $f ); ?>[suggestions]"><?php echo esc_textarea( (string) $o['suggestions'] ); ?></textarea><p class="description"><?php esc_html_e( 'One per line, up to four. Leave empty for none.', 'innomight-ai-search' ); ?></p></td>
					</tr>
					<tr>
						<th scope="row"><label for="innomight-fine"><?php esc_html_e( 'Fine print', 'innomight-ai-search' ); ?></label></th>
						<td><input id="innomight-fine" class="regular-text" type="text" name="<?php echo esc_attr( $f ); ?>[disclaimer]" value="<?php echo esc_attr( (string) $o['disclaimer'] ); ?>" /></td>
					</tr>
					<tr>
						<th scope="row"><label for="innomight-accent"><?php esc_html_e( 'Accent color', 'innomight-ai-search' ); ?></label></th>
						<td><input id="innomight-accent" type="text" class="code" name="<?php echo esc_attr( $f ); ?>[accent]" value="<?php echo esc_attr( (string) $o['accent'] ); ?>" placeholder="#2563eb" maxlength="7" /><p class="description"><?php esc_html_e( 'Optional. Leave empty to follow your theme.', 'innomight-ai-search' ); ?></p></td>
					</tr>
					<tr>
						<th scope="row"><label for="innomight-api"><?php esc_html_e( 'Backend URL', 'innomight-ai-search' ); ?></label></th>
						<td><input id="innomight-api" class="regular-text code" type="url" name="<?php echo esc_attr( $f ); ?>[api_url]" value="<?php echo esc_attr( (string) $o['api_url'] ); ?>" /><p class="description"><?php esc_html_e( 'Leave as is unless you are testing against a staging backend. HTTPS only.', 'innomight-ai-search' ); ?></p></td>
					</tr>
				</table>
				<?php submit_button(); ?>
			</form>

			<p>
				<a class="button" href="<?php echo esc_url( wp_nonce_url( admin_url( 'options-general.php?page=innomight-ai-search&innomight_search_test=1' ), 'innomight_search_test' ) ); ?>"><?php esc_html_e( 'Test connection', 'innomight-ai-search' ); ?></a>
			</p>
			<?php if ( null !== $test ) : ?>
				<p>
					<?php if ( is_wp_error( $test ) ) : ?>
						<strong style="color:#b32d2e"><?php echo esc_html( $test->get_error_message() ); ?></strong>
					<?php else : ?>
						<strong style="color:#008a20"><?php esc_html_e( 'Connected: the secret key works for this agent.', 'innomight-ai-search' ); ?></strong>
					<?php endif; ?>
				</p>
			<?php endif; ?>
		</div>
		<?php
	}
}
