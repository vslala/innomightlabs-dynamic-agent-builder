<?php
/**
 * REST route that relays one visitor question to the Innomight agent and streams the answer back.
 *
 * The browser sends only the question. WordPress sends no article text: the agent does the searching.
 *
 * @package InnomightAISearch
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class Innomight_Search_Chat {
	private const CLEANUP_HOOK = 'innomight_search_quota_cleanup';

	public static function init(): void {
		add_action( 'rest_api_init', array( self::class, 'register_routes' ) );
		add_action( self::CLEANUP_HOOK, array( self::class, 'cleanup_quota' ) );
	}

	public static function register_routes(): void {
		register_rest_route(
			'innomight-search/v1',
			'/chat',
			array(
				'methods'             => WP_REST_Server::CREATABLE,
				'callback'            => array( self::class, 'chat' ),
				'permission_callback' => array( self::class, 'can_chat' ),
				'args'                => array(
					'question'        => array( 'type' => 'string', 'required' => true, 'minLength' => 1, 'maxLength' => 1000 ),
					'visitor'         => array( 'type' => 'string', 'required' => true, 'maxLength' => 64 ),
					'conversation_id' => array( 'type' => 'string', 'default' => '', 'maxLength' => 128 ),
					'search'          => array( 'type' => 'string', 'default' => '', 'maxLength' => 300 ),
				),
			)
		);
	}

	/** @return true|WP_Error */
	public static function can_chat() {
		if ( ! Innomight_Search_Settings::is_ready() ) {
			return new WP_Error( 'innomight_search_unavailable', 'Chat is not configured.', array( 'status' => 503 ) );
		}
		return true;
	}

	/** Opaque ids from the browser: letters, digits, dash and underscore only. */
	public static function clean_id( $value, int $min, int $max ): string {
		$value = is_string( $value ) ? trim( $value ) : '';
		return preg_match( '/\A[A-Za-z0-9_-]{' . $min . ',' . $max . '}\z/', $value ) ? $value : '';
	}

	/**
	 * Streams the reply as Server-Sent Events and ends the request. Failures before the stream
	 * starts are ordinary JSON errors, which the chat shows inside the conversation.
	 *
	 * @return WP_Error|void
	 */
	public static function chat( WP_REST_Request $request ) {
		$permission = self::can_chat();
		if ( is_wp_error( $permission ) ) {
			return $permission;
		}
		$question = trim( sanitize_textarea_field( (string) $request->get_param( 'question' ) ) );
		if ( '' === $question || mb_strlen( $question ) > 1000 ) {
			return new WP_Error( 'innomight_search_invalid_question', 'Enter a question of at most 1,000 characters.', array( 'status' => 400 ) );
		}
		$visitor = self::clean_id( $request->get_param( 'visitor' ), 8, 64 );
		if ( '' === $visitor ) {
			return new WP_Error( 'innomight_search_invalid_visitor', 'Missing visitor id.', array( 'status' => 400 ) );
		}
		$search          = trim( sanitize_text_field( (string) $request->get_param( 'search' ) ) );
		$conversation_id = self::clean_id( $request->get_param( 'conversation_id' ), 8, 128 );

		$quota = self::reserve_quota();
		if ( is_wp_error( $quota ) ) {
			return $quota;
		}
		$end_user = 'wp:' . $visitor;
		if ( '' === $conversation_id ) {
			$instructions    = trim( (string) Innomight_Search_Settings::get( 'instructions' ) );
			$conversation_id = Innomight_Search_API::create_conversation(
				$end_user,
				'' !== $search ? 'Search: ' . mb_substr( $search, 0, 80 ) : 'Site chat',
				self::build_context( '' !== $instructions ? $instructions : Innomight_Search_Settings::DEFAULT_INSTRUCTIONS, $search )
			);
			if ( is_wp_error( $conversation_id ) ) {
				return $conversation_id;
			}
		}

		self::open_stream();
		self::emit( 'conversation', array( 'conversation_id' => $conversation_id ) );
		$url  = Innomight_Search_API::agent_url( '/conversations/' . rawurlencode( $conversation_id ) . '/messages' ) . '?end_user_id=' . rawurlencode( $end_user );
		$body = wp_json_encode( array( 'content' => $question, 'stream' => true ) );
		self::relay( $url, $body );
		self::finish();
	}

	public static function build_context( string $template, string $search ): string {
		return strtr(
			$template,
			array(
				'{site}'   => wp_strip_all_tags( get_bloginfo( 'name' ) ),
				'{url}'    => home_url( '/' ),
				'{search}' => '' !== $search ? $search : '(none)',
			)
		);
	}

	/* ------------------------------------------------------------ streaming */

	private static function open_stream(): void {
		if ( ! headers_sent() ) {
			header( 'Content-Type: text/event-stream; charset=utf-8' );
			header( 'Cache-Control: no-cache, no-transform' );
			header( 'X-Accel-Buffering: no' );
		}
		// Ask the web server not to compress the stream: a compressed stream is held back until it ends.
		if ( function_exists( 'apache_setenv' ) ) {
			apache_setenv( 'no-gzip', '1' );
		}
		while ( ! defined( 'INNOMIGHT_SEARCH_TESTING' ) && ob_get_level() > 0 ) {
			ob_end_clean();
		}
		// Padding makes proxies that hold back the first few bytes start forwarding.
		echo ':' . str_repeat( ' ', 2048 ) . "\n\n"; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
		self::flush();
	}

	private static function flush(): void {
		if ( function_exists( 'flush' ) ) {
			flush();
		}
	}

	/** @param array<string, mixed> $data */
	private static function emit( string $event, array $data ): void {
		echo self::frame( $event, $data ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- JSON-encoded event frame.
		self::flush();
	}

	/** Ends the request. Tests define INNOMIGHT_SEARCH_TESTING to keep running. */
	private static function finish(): void {
		if ( ! defined( 'INNOMIGHT_SEARCH_TESTING' ) ) {
			exit;
		}
	}

	/** @param array<string, mixed> $data */
	private static function frame( string $event, array $data ): string {
		return 'event: ' . $event . "\ndata: " . ( $data ? wp_json_encode( $data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES ) : '{}' ) . "\n\n";
	}

	/**
	 * Turn one upstream SSE block into what visitors may see, or null to drop it. Exposed for tests.
	 *
	 * Only answer text, tool names, completion and a generic error pass. Message ids, raw provider
	 * errors and anything unknown stay on the server.
	 */
	public static function relay_block( string $block ): ?string {
		$event = '';
		$data  = '';
		foreach ( explode( "\n", $block ) as $line ) {
			if ( 0 === strpos( $line, 'event:' ) ) {
				$event = trim( substr( $line, 6 ) );
			} elseif ( 0 === strpos( $line, 'data:' ) ) {
				$data .= trim( substr( $line, 5 ) );
			}
		}
		$json = '' !== $data ? json_decode( $data, true ) : array();
		$json = is_array( $json ) ? $json : array();
		switch ( $event ) {
			case 'message.delta':
				return isset( $json['text'] ) && is_string( $json['text'] ) ? self::frame( 'message.delta', array( 'text' => $json['text'] ) ) : null;
			case 'tool.started':
				$name = isset( $json['name'] ) && is_string( $json['name'] ) ? substr( (string) preg_replace( '/[^A-Za-z0-9 _.\-]/', '', $json['name'] ), 0, 60 ) : '';
				return self::frame( 'tool.started', array( 'name' => $name ) );
			case 'message.completed':
				return self::frame( 'message.completed', array() );
			case 'done':
				return self::frame( 'done', array() );
			case 'error':
				return self::frame( 'error', array( 'message' => 'The assistant ran into a problem. Please try again.' ) );
		}
		return null;
	}

	/** Map an upstream HTTP failure to a visitor-safe code and message. @return array{0: string, 1: string} */
	public static function status_message( int $status ): array {
		switch ( $status ) {
			case 409:
				return array( 'busy', 'I am still answering your last question. Try again in a moment.' );
			case 404:
				return array( 'conversation_lost', 'That conversation has expired. Ask again to start a new one.' );
			case 429:
				return array( 'rate_limited', 'The assistant is busy. Please try again shortly.' );
		}
		return array( 'unavailable', 'The assistant is temporarily unavailable. Please try again later.' );
	}

	private static function emit_status_error( int $status ): void {
		list( $code, $message ) = self::status_message( $status );
		self::emit( 'error', array( 'code' => $code, 'message' => $message ) );
	}

	/** Send the message upstream and relay its events. Streams with cURL, otherwise relays after completion. */
	private static function relay( string $url, string $body ): void {
		if ( function_exists( 'curl_init' ) && ! defined( 'INNOMIGHT_SEARCH_NO_CURL' ) ) {
			self::relay_curl( $url, $body );
			return;
		}
		$response = wp_remote_post(
			$url,
			array(
				'timeout' => 90,
				'headers' => array_merge( Innomight_Search_API::headers(), array( 'Accept' => 'text/event-stream' ) ),
				'body'    => $body,
			)
		);
		$status = is_wp_error( $response ) ? 0 : (int) wp_remote_retrieve_response_code( $response );
		if ( 200 !== $status ) {
			self::emit_status_error( $status );
			return;
		}
		$buffer = str_replace( "\r\n", "\n", (string) wp_remote_retrieve_body( $response ) );
		foreach ( explode( "\n\n", $buffer ) as $block ) {
			$out = self::relay_block( $block );
			if ( null !== $out ) {
				echo $out; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- JSON-encoded event frame.
			}
		}
		self::flush();
	}

	private static function relay_curl( string $url, string $body ): void {
		$status  = 0;
		$buffer  = '';
		$headers = array();
		foreach ( array_merge( Innomight_Search_API::headers(), array( 'Accept' => 'text/event-stream' ) ) as $k => $v ) {
			$headers[] = $k . ': ' . $v;
		}
		$ch = curl_init( $url ); // phpcs:ignore WordPress.WP.AlternativeFunctions.curl_curl_init -- WordPress HTTP API cannot stream.
		curl_setopt_array( // phpcs:ignore WordPress.WP.AlternativeFunctions.curl_curl_setopt_array
			$ch,
			array(
				CURLOPT_POST           => true,
				CURLOPT_POSTFIELDS     => $body,
				CURLOPT_HTTPHEADER     => $headers,
				CURLOPT_CONNECTTIMEOUT => 15,
				CURLOPT_TIMEOUT        => 180,
				CURLOPT_HEADERFUNCTION => static function ( $handle, $header ) use ( &$status ) {
					if ( preg_match( '#^HTTP/\S+\s+(\d{3})#', $header, $m ) ) {
						$status = (int) $m[1];
					}
					return strlen( $header );
				},
				CURLOPT_WRITEFUNCTION  => static function ( $handle, $chunk ) use ( &$status, &$buffer ) {
					if ( 200 !== $status ) {
						return strlen( $chunk ); // Error bodies are never shown to visitors.
					}
					$buffer .= str_replace( "\r\n", "\n", $chunk );
					while ( false !== ( $pos = strpos( $buffer, "\n\n" ) ) ) {
						$block  = substr( $buffer, 0, $pos );
						$buffer = substr( $buffer, $pos + 2 );
						$out    = self::relay_block( $block );
						if ( null !== $out ) {
							echo $out; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- JSON-encoded event frame.
							self::flush();
						}
					}
					return strlen( $chunk );
				},
			)
		);
		$ok = curl_exec( $ch ); // phpcs:ignore WordPress.WP.AlternativeFunctions.curl_curl_exec
		if ( PHP_VERSION_ID < 80000 ) {
			curl_close( $ch ); // phpcs:ignore WordPress.WP.AlternativeFunctions.curl_curl_close
		}
		if ( false === $ok || 200 !== $status ) {
			self::emit_status_error( $status );
		}
	}

	/* ------------------------------------------------------------ hourly limits */

	/**
	 * Fixed UTC-hour limits reserved atomically with add_option(): per client address, then per site.
	 * Only REMOTE_ADDR is trusted; configure trusted proxies at the web server.
	 *
	 * @return true|WP_Error
	 */
	private static function reserve_quota() {
		$limits = apply_filters( 'innomight_search_limits', array( 'ip' => 40, 'site' => 400 ) );
		$ip     = isset( $_SERVER['REMOTE_ADDR'] ) ? filter_var( wp_unslash( $_SERVER['REMOTE_ADDR'] ), FILTER_VALIDATE_IP ) : false;
		$ip     = $ip ? $ip : 'unknown';
		$site   = self::reserve_slot( 'site', max( 1, (int) $limits['site'] ) );
		if ( is_wp_error( $site ) ) {
			return $site;
		}
		$visitor = self::reserve_slot( 'ip:' . $ip, max( 1, (int) $limits['ip'] ) );
		if ( is_wp_error( $visitor ) ) {
			delete_option( $site );
			return $visitor;
		}
		$keys    = array( $site, $visitor );
		$expires = ( (int) floor( time() / HOUR_IN_SECONDS ) + 1 ) * HOUR_IN_SECONDS + 300;
		foreach ( $keys as $key ) {
			$scheduled = wp_schedule_single_event( $expires, self::CLEANUP_HOOK, array( $key ), true );
			if ( is_wp_error( $scheduled ) || ! $scheduled ) {
				foreach ( $keys as $reserved ) {
					delete_option( $reserved );
					wp_clear_scheduled_hook( self::CLEANUP_HOOK, array( $reserved ) );
				}
				return new WP_Error( 'innomight_search_quota_unavailable', 'The assistant is temporarily unavailable.', array( 'status' => 503 ) );
			}
		}
		return true;
	}

	/** @return string|WP_Error */
	private static function reserve_slot( string $subject, int $limit ) {
		$window = (int) floor( time() / HOUR_IN_SECONDS );
		$hash   = substr( wp_hash( $subject . ':' . $window ), 0, 32 );
		for ( $slot = 0; $slot < $limit; $slot++ ) {
			$key = 'innomight_search_quota_' . $hash . '_' . $slot;
			if ( add_option( $key, 1, '', false ) ) {
				return $key;
			}
		}
		return new WP_Error( 'innomight_search_rate_limit', 'The hourly question limit has been reached. Please try again next hour.', array( 'status' => 429 ) );
	}

	public static function cleanup_quota( string $key ): void {
		if ( preg_match( '/\Ainnomight_search_quota_[a-f0-9]{32}_\d+\z/', $key ) ) {
			delete_option( $key );
		}
	}
}
