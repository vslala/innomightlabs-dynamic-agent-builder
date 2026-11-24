<?php
$params = static function ( array $over = array() ): array {
	return array_merge( array( 'mode' => 'ask', 'action' => '', 'length' => 'paragraph', 'prompt' => 'Find a source', 'selection' => 'Agents are useful.', 'before' => 'Intro text.', 'title' => 'My post' ), $over );
};
$editor = static function (): void { $GLOBALS['wp_test']['caps'] = array( Innomight_Search_Editor::CAPABILITY ); };
$write  = static function ( array $p ): string {
	ob_start();
	$result = Innomight_Search_Editor::write( new WP_REST_Request( $p ) );
	$out    = ob_get_clean();
	check( ! is_wp_error( $result ), 'Expected a stream' );
	return $out;
};

return array(
	/* ---- who may write ---- */
	'only editors and administrators can use the writing tools' => static function () use ( $editor ): void {
		error_is( Innomight_Search_Editor::can_write(), 'innomight_search_forbidden', 403 );
		$editor();
		same( true, Innomight_Search_Editor::can_write() );
	},
	'the tools need a connected agent but not the visitor chat switch' => static function () use ( $editor ): void {
		$editor();
		$GLOBALS['wp_test']['options'][ Innomight_Search_Settings::OPTION ] = array( 'enabled' => 0, 'agent_id' => 'agent-1234' );
		same( true, Innomight_Search_Editor::can_write() );
		unset( $GLOBALS['wp_test']['options'][ Innomight_Search_Settings::SECRET_OPTION ] );
		error_is( Innomight_Search_Editor::can_write(), 'innomight_search_unavailable', 503 );
	},
	'a forbidden user sends nothing upstream' => static function () use ( $params ): void {
		error_is( Innomight_Search_Editor::write( new WP_REST_Request( $params() ) ), 'innomight_search_forbidden', 403 );
		same( array(), $GLOBALS['wp_test']['http'] );
	},

	/* ---- inputs ---- */
	'rewrite needs a selection and a known action; the others need a prompt' => static function () use ( $params, $editor ): void {
		$editor();
		foreach ( array(
			array( 'mode' => 'rewrite', 'action' => 'shorten', 'selection' => '' ),
			array( 'mode' => 'rewrite', 'action' => 'delete-everything' ),
			array( 'mode' => 'ask', 'prompt' => '  ' ),
			array( 'mode' => 'generate', 'prompt' => '' ),
		) as $over ) {
			error_is( Innomight_Search_Editor::write( new WP_REST_Request( $params( $over ) ) ), 'innomight_search_invalid_request', 400 );
		}
		same( array(), $GLOBALS['wp_test']['http'] );
	},

	/* ---- the prompts ---- */
	'ask puts the selection, the question and the context in the message' => static function (): void {
		$p = Innomight_Search_Editor::build_prompt( 'ask', '', 'Find a source', 'Agents are useful.', 'Intro text.', 'My post', 'paragraph' );
		foreach ( array( 'Post title: My post', 'Intro text.', 'Agents are useful.', 'The author asks: Find a source' ) as $part ) {
			check( false !== strpos( $p, $part ), "missing: $part" );
		}
	},
	'rewrite asks for plain replacement text only' => static function (): void {
		$p = Innomight_Search_Editor::build_prompt( 'rewrite', 'shorten', '', 'Some long text.', '', '', 'paragraph' );
		check( false !== strpos( $p, 'Some long text.' ) && false !== strpos( $p, 'shorter' ) && false !== strpos( $p, 'only the replacement text' ) );
		check( false === strpos( $p, 'Post title' ), 'empty context is left out' );
	},
	'generate honours the length and falls back to a paragraph' => static function (): void {
		check( false !== strpos( Innomight_Search_Editor::build_prompt( 'generate', '', 'agents', '', '', '', 'sentence' ), 'Write one sentence' ) );
		check( false !== strpos( Innomight_Search_Editor::build_prompt( 'generate', '', 'agents', '', '', '', 'novel' ), 'Write one paragraph' ) );
	},

	/* ---- the conversation ---- */
	'a request opens a conversation for the user and streams the answer' => static function () use ( $params, $editor, $write ): void {
		$editor();
		$GLOBALS['wp_test']['responses'] = array(
			http_reply( 201, json_encode( array( 'conversation_id' => 'conv-12345678' ) ) ),
			http_reply( 200, "event: message.delta\ndata: {\"text\":\"Hello\"}\n\nevent: done\ndata: {}\n\n" ),
		);
		$out = $write( $params() );
		list( $create, $send ) = $GLOBALS['wp_test']['http'];
		$created = json_decode( $create['args']['body'], true );
		same( 'wp-user:7', $created['end_user_id'] );
		check( false !== strpos( $created['context'], 'Example Journal' ), 'the site is named in the instructions' );
		check( false !== strpos( $send['url'], 'end_user_id=wp-user%3A7' ) );
		check( false !== strpos( json_decode( $send['args']['body'], true )['content'], 'Agents are useful.' ) );
		check( false !== strpos( $out, 'Hello' ) && false !== strpos( $out, 'event: done' ) );
		check( false === strpos( $out, 'sk_live' ) );
	},
);
