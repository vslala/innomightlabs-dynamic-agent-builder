<?php
$params = static function ( array $over = array() ): array {
	return array_merge( array( 'question' => 'What should I read first?', 'visitor' => 'visitor-abcdef12', 'search' => 'agents', 'conversation_id' => '' ), $over );
};
$sse = static function ( array $events ): string {
	$out = '';
	foreach ( $events as $name => $data ) { $out .= "event: $name\ndata: " . json_encode( $data ) . "\n\n"; }
	return $out;
};

return array(
	/* ---- what readers may see ---- */
	'relay passes answer text, completion and the end marker' => static function (): void {
		same( "event: message.delta\ndata: {\"text\":\"Hello <b>\"}\n\n", Innomight_Search_Chat::relay_block( "id: 3\nevent: message.delta\ndata: {\"text\": \"Hello <b>\"}" ) );
		same( "event: message.completed\ndata: {}\n\n", Innomight_Search_Chat::relay_block( "event: message.completed\ndata: {\"message_id\":\"secret-id\",\"role\":\"assistant\"}" ) );
		same( "event: done\ndata: {}\n\n", Innomight_Search_Chat::relay_block( "event: done\ndata: {}" ) );
	},
	'relay drops ids and unknown events' => static function (): void {
		same( null, Innomight_Search_Chat::relay_block( "event: message.created\ndata: {\"message_id\":\"m1\",\"role\":\"user\"}" ) );
		same( null, Innomight_Search_Chat::relay_block( "event: debug.trace\ndata: {\"x\":1}" ) );
		same( null, Innomight_Search_Chat::relay_block( ': keep-alive' ) );
		same( null, Innomight_Search_Chat::relay_block( "event: message.delta\ndata: {not json" ) );
	},
	'relay shows tool names sanitised and never raw upstream errors' => static function (): void {
		same( "event: tool.started\ndata: {\"name\":\"search_site\"}\n\n", Innomight_Search_Chat::relay_block( "event: tool.started\ndata: {\"name\":\"search_site\"}" ) );
		$name = Innomight_Search_Chat::relay_block( "event: tool.started\ndata: {\"name\":\"<img src=x onerror=1>\"}" );
		check( false === strpos( $name, '<' ) && false === strpos( $name, '=' ) );
		$error = Innomight_Search_Chat::relay_block( "event: error\ndata: {\"message\":\"SECRET provider stack trace\"}" );
		check( false === strpos( $error, 'SECRET' ) );
		check( false !== strpos( $error, 'event: error' ) );
	},
	'upstream failures map to safe messages' => static function (): void {
		same( 'busy', Innomight_Search_Chat::status_message( 409 )[0] );
		same( 'conversation_lost', Innomight_Search_Chat::status_message( 404 )[0] );
		same( 'unavailable', Innomight_Search_Chat::status_message( 500 )[0] );
		same( 'unavailable', Innomight_Search_Chat::status_message( 401 )[0] );
	},

	/* ---- inputs ---- */
	'ids from the browser are opaque tokens only' => static function (): void {
		same( 'visitor-abcdef12', Innomight_Search_Chat::clean_id( 'visitor-abcdef12', 8, 64 ) );
		same( '', Innomight_Search_Chat::clean_id( '../../etc/passwd', 8, 64 ) );
		same( '', Innomight_Search_Chat::clean_id( 'short', 8, 64 ) );
		same( '', Innomight_Search_Chat::clean_id( "abc\ndef12345", 8, 64 ) );
		same( '', Innomight_Search_Chat::clean_id( array( 'x' ), 8, 64 ) );
	},
	'context fills site, url and search without markup' => static function (): void {
		$context = Innomight_Search_Chat::build_context( '{site} {url} {search}', 'agents' );
		same( 'Example Journal https://example.test/ agents', $context );
		same( 'x (none)', Innomight_Search_Chat::build_context( 'x {search}', '' ) );
	},
	'rejects an empty question, an over-long one and a missing visitor' => static function () use ( $params ): void {
		foreach ( array( array( 'question' => '   ' ), array( 'question' => str_repeat( 'a', 1001 ) ) ) as $over ) {
			error_is( Innomight_Search_Chat::chat( new WP_REST_Request( $params( $over ) ) ), 'innomight_search_invalid_question', 400 );
		}
		error_is( Innomight_Search_Chat::chat( new WP_REST_Request( $params( array( 'visitor' => 'x' ) ) ) ), 'innomight_search_invalid_visitor', 400 );
		same( array(), $GLOBALS['wp_test']['http'], 'nothing is sent upstream for invalid input' );
	},

	/* ---- the conversation ---- */
	'first question creates a scoped conversation then streams the reply' => static function () use ( $params, $sse ): void {
		$GLOBALS['wp_test']['responses'] = array(
			http_reply( 201, json_encode( array( 'conversation_id' => 'conv-12345678' ) ) ),
			http_reply( 200, $sse( array( 'message.created' => array( 'message_id' => 'm1' ), 'message.delta' => array( 'text' => 'Read ' ), 'tool.started' => array( 'name' => 'search_site' ), 'message.delta' => array( 'text' => 'A2A.' ), 'message.completed' => array( 'message_id' => 'm2' ), 'done' => array() ) ) ),
		);
		$out = chat_output( $params() );
		list( $create, $send ) = $GLOBALS['wp_test']['http'];
		same( 'https://api.innomightlabs.com/v1/agents/agent-1234/conversations', $create['url'] );
		same( 'Bearer sk_live_test-only-key', $create['args']['headers']['Authorization'] );
		$created = json_decode( $create['args']['body'], true );
		same( 'wp:visitor-abcdef12', $created['end_user_id'] );
		check( false !== strpos( $created['context'], 'The reader searched for: agents' ) );
		same( 'https://api.innomightlabs.com/v1/agents/agent-1234/conversations/conv-12345678/messages?end_user_id=wp%3Avisitor-abcdef12', $send['url'] );
		same( array( 'content' => 'What should I read first?', 'stream' => true ), json_decode( $send['args']['body'], true ) );
		check( false !== strpos( $out, "event: conversation\ndata: {\"conversation_id\":\"conv-12345678\"}" ) );
		check( false !== strpos( $out, 'A2A.' ) );
		check( false !== strpos( $out, "event: done\ndata: {}" ) );
		check( false === strpos( $out, 'm1' ) && false === strpos( $out, 'm2' ), 'message ids stay on the server' );
		check( false === strpos( $out, 'sk_live' ), 'the secret never reaches the page' );
	},
	'a follow-up reuses the conversation without creating another' => static function () use ( $params, $sse ): void {
		$GLOBALS['wp_test']['responses'] = array( http_reply( 200, $sse( array( 'message.delta' => array( 'text' => 'More.' ), 'done' => array() ) ) ) );
		$out = chat_output( $params( array( 'conversation_id' => 'conv-12345678' ) ) );
		same( 1, count( $GLOBALS['wp_test']['http'] ) );
		check( false !== strpos( $GLOBALS['wp_test']['http'][0]['url'], '/conversations/conv-12345678/messages' ) );
		check( false !== strpos( $out, 'More.' ) );
	},
	'a failed conversation start is a generic 502 that leaks nothing' => static function () use ( $params ): void {
		$GLOBALS['wp_test']['responses'] = array( http_reply( 401, '{"detail":"SECRET key sk_live_abc rejected"}' ) );
		$result = Innomight_Search_Chat::chat( new WP_REST_Request( $params() ) );
		error_is( $result, 'innomight_search_failed', 502 );
		check( false === strpos( serialize( $result ), 'SECRET' ) );
	},
	'an upstream conflict streams a friendly busy error' => static function () use ( $params ): void {
		$GLOBALS['wp_test']['responses'] = array( http_reply( 409, '{"detail":{"message":"A response is already in progress."}}' ) );
		$out = chat_output( $params( array( 'conversation_id' => 'conv-12345678' ) ) );
		check( false !== strpos( $out, '"code":"busy"' ) );
		check( false === strpos( $out, 'already in progress' ) );
	},

	/* ---- abuse limits ---- */
	'hourly limits stop a busy client and refund the site slot' => static function () use ( $params ): void {
		add_filter( 'innomight_search_limits', static function () { return array( 'ip' => 2, 'site' => 50 ); } );
		$GLOBALS['wp_test']['responses'] = array_fill( 0, 4, http_reply( 200, "event: done\ndata: {}\n\n" ) );
		chat_output( $params( array( 'conversation_id' => 'conv-12345678' ) ) );
		chat_output( $params( array( 'conversation_id' => 'conv-12345678' ) ) );
		error_is( Innomight_Search_Chat::chat( new WP_REST_Request( $params( array( 'conversation_id' => 'conv-12345678' ) ) ) ), 'innomight_search_rate_limit', 429 );
		$site_slots = count( array_filter( array_keys( $GLOBALS['wp_test']['options'] ), static function ( $k ) { return 0 === strpos( $k, 'innomight_search_quota_' ); } ) );
		same( 4, $site_slots, 'two questions use two site and two ip slots; the refused one leaves no extra site slot' );
		$_SERVER['REMOTE_ADDR'] = '198.51.100.9';
		chat_output( $params( array( 'conversation_id' => 'conv-12345678' ) ) );
	},
	'quota cleanup only deletes its own options' => static function (): void {
		$GLOBALS['wp_test']['options']['blogname'] = 'keep';
		$GLOBALS['wp_test']['options'][ 'innomight_search_quota_' . str_repeat( 'a', 32 ) . '_0' ] = 1;
		Innomight_Search_Chat::cleanup_quota( 'blogname' );
		Innomight_Search_Chat::cleanup_quota( 'innomight_search_quota_' . str_repeat( 'a', 32 ) . '_0' );
		same( 'keep', get_option( 'blogname' ) );
		check( ! isset( $GLOBALS['wp_test']['options'][ 'innomight_search_quota_' . str_repeat( 'a', 32 ) . '_0' ] ) );
	},
);
