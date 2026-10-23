<?php
/** Minimal in-memory WordPress boundary doubles; never bootstraps a real site. */
define( 'ABSPATH', __DIR__ . '/' );
define( 'HOUR_IN_SECONDS', 3600 );
define( 'INNOMIGHT_SEARCH_TESTING', true );
define( 'INNOMIGHT_SEARCH_NO_CURL', true );
define( 'INNOMIGHT_SEARCH_VERSION', 'test' );
define( 'INNOMIGHT_SEARCH_FILE', dirname( __DIR__ ) . '/innomight-ai-search.php' );
define( 'INNOMIGHT_SEARCH_DIR', dirname( __DIR__ ) . '/' );
define( 'INNOMIGHT_SEARCH_URL', 'https://example.test/wp-content/plugins/innomight-ai-search/' );

final class WP_Error {
	private $code; private $message; private $data;
	public function __construct( $code, $message, $data = null ) { $this->code = $code; $this->message = $message; $this->data = $data; }
	public function get_error_code() { return $this->code; }
	public function get_error_message() { return $this->message; }
	public function get_error_data() { return $this->data; }
}
final class WP_REST_Server { public const CREATABLE = 'POST'; }
final class WP_REST_Request {
	private $params;
	public function __construct( array $params ) { $this->params = $params; }
	public function get_param( $key ) { return $this->params[ $key ] ?? null; }
}
final class WP_Query { public function is_main_query() { return true; } }

function reset_wp_test(): void {
	$GLOBALS['wp_test'] = array(
		'options'   => array(
			Innomight_Search_Settings::OPTION        => array( 'enabled' => 1, 'agent_id' => 'agent-1234' ),
			Innomight_Search_Settings::SECRET_OPTION => 'sk_live_test-only-key',
		),
		'http' => array(), 'responses' => array(), 'events' => array(), 'filters' => array(),
		'is_search' => true, 'search' => 'agents', 'block_theme' => true, 'enqueued' => array(), 'admin' => false,
	);
	$_SERVER = array( 'REMOTE_ADDR' => '192.0.2.1' );
	$rendered = new ReflectionProperty( 'Innomight_Search_UI', 'rendered' );
	if ( PHP_VERSION_ID < 80100 ) {
		$rendered->setAccessible( true );
	}
	$rendered->setValue( null, false );
}
function is_wp_error( $v ): bool { return $v instanceof WP_Error; }
function get_option( $k, $d = false ) { return $GLOBALS['wp_test']['options'][ $k ] ?? $d; }
function add_option( $k, $v, $dep = '', $auto = null ): bool {
	if ( array_key_exists( $k, $GLOBALS['wp_test']['options'] ) ) { return false; }
	$GLOBALS['wp_test']['options'][ $k ] = $v;
	return true;
}
function delete_option( $k ): bool { unset( $GLOBALS['wp_test']['options'][ $k ] ); return true; }
function add_action( $h, $c, $p = 10, $a = 1 ): void {}
function add_filter( $h, $c, $p = 10, $a = 1 ): void { $GLOBALS['wp_test']['filters'][ $h ][] = $c; }
function apply_filters( $h, $v ) { foreach ( $GLOBALS['wp_test']['filters'][ $h ] ?? array() as $c ) { $v = $c( $v ); } return $v; }
function do_action( $h, ...$a ): void {}
function __( $t ) { return $t; }
function esc_html__( $t ) { return $t; }
function esc_html( $t ): string { return htmlspecialchars( (string) $t, ENT_QUOTES, 'UTF-8' ); }
function esc_attr( $t ): string { return htmlspecialchars( (string) $t, ENT_QUOTES, 'UTF-8' ); }
function esc_attr__( $t ): string { return esc_attr( $t ); }
function esc_url( $u ): string { return esc_attr( $u ); }
function esc_url_raw( $u, $p = null ): string { return preg_match( '#^https?://#i', (string) $u ) ? (string) $u : ''; }
function wp_parse_url( $u, $c = -1 ) { return parse_url( $u, $c ); }
function untrailingslashit( $s ): string { return rtrim( (string) $s, '/' ); }
function home_url( $p = '' ): string { return 'https://example.test' . $p; }
function rest_url( $p = '' ): string { return 'https://example.test/wp-json/' . $p; }
function get_bloginfo( $s = '' ): string { return 'Example <b>Journal</b>'; }
function wp_strip_all_tags( $t ): string { return trim( strip_tags( (string) $t ) ); }
function sanitize_text_field( $t ): string { return trim( preg_replace( '/\s+/', ' ', wp_strip_all_tags( $t ) ) ); }
function sanitize_textarea_field( $t ): string { return trim( wp_strip_all_tags( $t ) ); }
function sanitize_hex_color( $c ) { return preg_match( '/\A#([0-9a-f]{3}|[0-9a-f]{6})\z/i', (string) $c ) ? $c : null; }
function wp_json_encode( $v, $f = 0 ) { return json_encode( $v, $f ); }
function wp_hash( $v ): string { return hash_hmac( 'md5', $v, 'test-only-salt' ); }
function wp_schedule_single_event( $t, $h, $a = array(), $e = false ) { $GLOBALS['wp_test']['events'][] = compact( 't', 'h', 'a' ); return true; }
function wp_clear_scheduled_hook( $h, $a = array() ) { return 0; }
function wp_unslash( $v ) { return $v; }
function wp_remote_post( $url, $args = array() ) { return wp_remote_stub( 'POST', $url, $args ); }
function wp_remote_get( $url, $args = array() ) { return wp_remote_stub( 'GET', $url, $args ); }
function wp_remote_stub( $method, $url, $args ) {
	$GLOBALS['wp_test']['http'][] = compact( 'method', 'url', 'args' );
	return array_shift( $GLOBALS['wp_test']['responses'] ) ?? new WP_Error( 'unexpected', 'No queued response' );
}
function http_reply( int $code, string $body ): array { return array( 'code' => $code, 'body' => $body ); }
function wp_remote_retrieve_response_code( $r ) { return $r['code']; }
function wp_remote_retrieve_body( $r ) { return $r['body']; }
function is_search(): bool { return $GLOBALS['wp_test']['is_search']; }
function get_search_query( $escaped = true ) { return $GLOBALS['wp_test']['search']; }
function is_admin(): bool { return $GLOBALS['wp_test']['admin']; }
function wp_is_block_theme(): bool { return $GLOBALS['wp_test']['block_theme']; }
function current_user_can( $c ): bool { return false; }
function wp_enqueue_style( $h ) { $GLOBALS['wp_test']['enqueued'][] = $h; }
function wp_enqueue_script( $h ) { $GLOBALS['wp_test']['enqueued'][] = $h; }
function mb_substr_safe( $s, $n ) { return mb_substr( $s, 0, $n ); }

require_once dirname( __DIR__ ) . '/includes/class-innomight-search-settings.php';
require_once dirname( __DIR__ ) . '/includes/class-innomight-search-api.php';
require_once dirname( __DIR__ ) . '/includes/class-innomight-search-chat.php';
require_once dirname( __DIR__ ) . '/includes/class-innomight-search-ui.php';

function check( bool $c, string $m = 'Assertion failed' ): void { if ( ! $c ) { throw new RuntimeException( $m ); } }
function same( $expected, $actual, string $m = '' ): void {
	check( $expected === $actual, $m ?: 'Expected ' . var_export( $expected, true ) . ', got ' . var_export( $actual, true ) );
}
function error_is( $r, string $code, int $status ): void {
	check( $r instanceof WP_Error, 'Expected WP_Error, got ' . get_debug_type( $r ) );
	same( $code, $r->get_error_code() );
	same( $status, $r->get_error_data()['status'] );
}
/** Run the chat route and return what it streamed. */
function chat_output( array $params ): string {
	ob_start();
	$result = Innomight_Search_Chat::chat( new WP_REST_Request( $params ) );
	$out    = ob_get_clean();
	check( ! is_wp_error( $result ), 'Expected a stream, got an error' );
	return $out;
}
