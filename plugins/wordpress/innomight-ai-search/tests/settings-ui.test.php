<?php
return array(
	'ready only when enabled, with a key and an agent' => static function (): void {
		check( Innomight_Search_Settings::is_ready() );
		foreach ( array( 'enabled', 'secret', 'agent' ) as $missing ) {
			reset_wp_test();
			if ( 'enabled' === $missing ) { $GLOBALS['wp_test']['options'][ Innomight_Search_Settings::OPTION ]['enabled'] = 0; }
			if ( 'secret' === $missing ) { unset( $GLOBALS['wp_test']['options'][ Innomight_Search_Settings::SECRET_OPTION ] ); }
			if ( 'agent' === $missing ) { $GLOBALS['wp_test']['options'][ Innomight_Search_Settings::OPTION ]['agent_id'] = ''; }
			check( ! Innomight_Search_Settings::is_ready(), "ready without $missing" );
			error_is( Innomight_Search_Chat::can_chat(), 'innomight_search_unavailable', 503 );
		}
	},
	'the secret key field never overwrites with blank and rejects non-keys' => static function (): void {
		same( 'sk_live_test-only-key', Innomight_Search_Settings::sanitize_secret( '' ) );
		same( 'sk_live_newkey123456', Innomight_Search_Settings::sanitize_secret( '  sk_live_newkey123456 ' ) );
		same( '', Innomight_Search_Settings::sanitize_secret( 'pk_live_publickey123' ), 'a widget (public) key is not accepted' );
		same( '', Innomight_Search_Settings::sanitize_secret( "sk_live_x\n<script>" ) );
	},
	'settings are sanitised and bounded' => static function (): void {
		$out = Innomight_Search_Settings::sanitize( array(
			'enabled' => '1', 'agent_id' => '../bad id', 'api_url' => 'javascript:alert(1)', 'placement' => 'sideways',
			'title' => '<b>Hi</b>', 'accent' => 'red', 'instructions' => str_repeat( 'x', 9000 ),
		) );
		same( 1, $out['enabled'] );
		same( '', $out['agent_id'] );
		same( Innomight_Search_Settings::DEFAULT_API, $out['api_url'] );
		same( 'above', $out['placement'] );
		same( 'Hi', $out['title'] );
		same( '', $out['accent'] );
		same( 4000, mb_strlen( $out['instructions'] ) );
	},
	'the backend url must be https unless it is local' => static function (): void {
		same( 'https://api.example.com', Innomight_Search_Settings::sanitize_api_url( 'https://api.example.com/' ) );
		same( 'http://localhost:8000', Innomight_Search_Settings::sanitize_api_url( 'http://localhost:8000' ) );
		same( Innomight_Search_Settings::DEFAULT_API, Innomight_Search_Settings::sanitize_api_url( 'http://evil.example.com' ) );
		same( Innomight_Search_Settings::DEFAULT_API, Innomight_Search_Settings::sanitize_api_url( '' ) );
	},
	'the chat card is escaped and carries no secret' => static function (): void {
		$GLOBALS['wp_test']['options'][ Innomight_Search_Settings::OPTION ] += array(
			'title' => '<script>alert(1)</script>', 'suggestions' => "<img src=x onerror=1>\nWhat next?", 'accent' => '#112233',
		);
		$GLOBALS['wp_test']['search'] = '"><script>x</script>';
		$html = Innomight_Search_UI::render();
		check( false === strpos( $html, '<script' ), 'markup is escaped' );
		check( false === strpos( $html, '<img' ) );
		check( false !== strpos( $html, 'data-endpoint="https://example.test/wp-json/innomight-search/v1/chat"' ) );
		check( false !== strpos( $html, '--innomight-accent:#112233' ) );
		check( false === strpos( $html, 'sk_live' ) && false === strpos( $html, 'agent-1234' ), 'no credentials in the page' );
		same( array( 'innomight-search', 'innomight-search' ), $GLOBALS['wp_test']['enqueued'] );
	},
	'nothing is rendered for visitors until configured' => static function (): void {
		$GLOBALS['wp_test']['options'][ Innomight_Search_Settings::OPTION ]['enabled'] = 0;
		same( '', Innomight_Search_UI::render() );
	},
	'block themes: the chat wraps the main query loop once' => static function (): void {
		$block = array( 'blockName' => 'core/query', 'attrs' => array( 'query' => array( 'inherit' => true ) ) );
		$first = Innomight_Search_UI::place_in_block_theme( '<ul>results</ul>', $block );
		check( 0 === strpos( $first, '<section class="innomight-search"' ) && substr( $first, -16 ) === '<ul>results</ul>', 'card above the results' );
		same( '<ul>results</ul>', Innomight_Search_UI::place_in_block_theme( '<ul>results</ul>', $block ), 'only once per page' );
	},
	'block themes: ignores other queries, below placement and non-search pages' => static function (): void {
		$other = array( 'blockName' => 'core/query', 'attrs' => array( 'query' => array( 'inherit' => false ) ) );
		same( 'x', Innomight_Search_UI::place_in_block_theme( 'x', $other ) );
		same( 'x', Innomight_Search_UI::place_in_block_theme( 'x', array( 'blockName' => 'core/paragraph', 'attrs' => array() ) ) );
		$main = array( 'blockName' => 'core/query', 'attrs' => array( 'query' => array( 'inherit' => true ) ) );
		$GLOBALS['wp_test']['is_search'] = false;
		same( 'x', Innomight_Search_UI::place_in_block_theme( 'x', $main ) );
		$GLOBALS['wp_test']['is_search'] = true;
		$GLOBALS['wp_test']['options'][ Innomight_Search_Settings::OPTION ]['placement'] = 'below';
		$below = Innomight_Search_UI::place_in_block_theme( '<ul>r</ul>', $main );
		check( 0 === strpos( $below, '<ul>r</ul><section' ), 'card below the results' );
	},
	'placement can be turned off' => static function (): void {
		$GLOBALS['wp_test']['options'][ Innomight_Search_Settings::OPTION ]['placement'] = 'off';
		$main = array( 'blockName' => 'core/query', 'attrs' => array( 'query' => array( 'inherit' => true ) ) );
		same( 'x', Innomight_Search_UI::place_in_block_theme( 'x', $main ) );
	},
	'classic themes: the loop hooks place the chat, block themes skip them' => static function (): void {
		$GLOBALS['wp_test']['block_theme'] = false;
		ob_start();
		Innomight_Search_UI::place_above_classic( new WP_Query() );
		$out = ob_get_clean();
		check( false !== strpos( $out, 'class="innomight-search"' ) );
		reset_wp_test();
		$GLOBALS['wp_test']['block_theme'] = true;
		ob_start();
		Innomight_Search_UI::place_above_classic( new WP_Query() );
		same( '', ob_get_clean() );
	},
);
