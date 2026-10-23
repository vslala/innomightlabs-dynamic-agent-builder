<?php
/**
 * The visitor-facing chat: block, shortcode and automatic placement on search results.
 *
 * @package InnomightAISearch
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class Innomight_Search_UI {
	private static bool $rendered = false;

	public static function init(): void {
		add_action( 'init', array( self::class, 'register' ) );
		add_action( 'wp_enqueue_scripts', array( self::class, 'maybe_enqueue' ) );
		add_filter( 'render_block', array( self::class, 'place_in_block_theme' ), 10, 2 );
		add_action( 'loop_start', array( self::class, 'place_above_classic' ) );
		add_action( 'loop_end', array( self::class, 'place_below_classic' ) );
	}

	public static function register(): void {
		wp_register_style( 'innomight-search', INNOMIGHT_SEARCH_URL . 'assets/css/chat.css', array(), INNOMIGHT_SEARCH_VERSION );
		wp_register_script( 'innomight-search', INNOMIGHT_SEARCH_URL . 'assets/js/chat.js', array(), INNOMIGHT_SEARCH_VERSION, array( 'in_footer' => true, 'strategy' => 'defer' ) );
		register_block_type( INNOMIGHT_SEARCH_DIR . 'block', array( 'render_callback' => array( self::class, 'render_block' ) ) );
		add_shortcode( 'innomight_ai_search', array( self::class, 'render_block' ) );
	}

	/** Load the assets early on search pages so the chat is styled on first paint. */
	public static function maybe_enqueue(): void {
		if ( is_search() && Innomight_Search_Settings::is_ready() && 'off' !== Innomight_Search_Settings::get( 'placement' ) ) {
			wp_enqueue_style( 'innomight-search' );
			wp_enqueue_script( 'innomight-search' );
		}
	}

	/** Block and shortcode callback. */
	public static function render_block(): string {
		return self::render();
	}

	/** The chat card, or an empty string when chat is not switched on and configured. */
	public static function render(): string {
		if ( ! Innomight_Search_Settings::is_ready() ) {
			return current_user_can( 'manage_options' ) && ( ! defined( 'REST_REQUEST' ) || ! REST_REQUEST ) && ! is_admin()
				? '<p class="innomight-search__notice"><em>' . esc_html__( 'Innomight AI Search: add your agent ID and secret key under Settings → Innomight AI Search, and switch the chat on. Only administrators see this note.', 'innomight-ai-search' ) . '</em></p>'
				: '';
		}
		$title = (string) Innomight_Search_Settings::get( 'title' );
		$head  = '<header class="innomight-search__hd"><span class="innomight-search__badge">' . self::icon( 'spark' ) . '</span><h2 class="innomight-search__title">' . esc_html( $title ) . '</h2></header>';
		if ( defined( 'REST_REQUEST' ) && REST_REQUEST ) { // Block editor preview.
			return '<section class="innomight-search">' . $head . '<p class="innomight-search__intro">' . esc_html__( 'The follow-up chat appears here on your site.', 'innomight-ai-search' ) . '</p></section>';
		}
		self::$rendered = true;
		wp_enqueue_style( 'innomight-search' );
		wp_enqueue_script( 'innomight-search' );

		$search = is_search() ? trim( mb_substr( wp_strip_all_tags( get_search_query( false ) ), 0, 300 ) ) : '';
		$i18n   = array(
			'thinking' => __( 'Looking through the site…', 'innomight-ai-search' ),
			'error'    => __( 'Something went wrong. Please try again.', 'innomight-ai-search' ),
		);
		$accent = (string) Innomight_Search_Settings::get( 'accent' );
		$out    = '<section class="innomight-search" data-innomight-search'
			. ' data-endpoint="' . esc_url( rest_url( 'innomight-search/v1/chat' ) ) . '"'
			. ' data-search="' . esc_attr( $search ) . '"'
			. ' data-i18n="' . esc_attr( (string) wp_json_encode( $i18n ) ) . '"'
			. ( $accent ? ' style="--innomight-accent:' . esc_attr( $accent ) . '"' : '' )
			. ' aria-label="' . esc_attr( $title ) . '">' . $head;
		$intro  = (string) Innomight_Search_Settings::get( 'intro' );
		if ( '' !== $intro ) {
			$out .= '<p class="innomight-search__intro">' . esc_html( $intro ) . '</p>';
		}
		$out        .= '<div class="innomight-search__thread" role="log" aria-live="polite" hidden></div>';
		$suggestions = array_values( array_filter( array_map( 'trim', explode( "\n", (string) Innomight_Search_Settings::get( 'suggestions' ) ) ) ) );
		if ( $suggestions ) {
			$out .= '<div class="innomight-search__sug">';
			foreach ( array_slice( $suggestions, 0, 4 ) as $s ) {
				$out .= '<button type="button">' . esc_html( $s ) . '</button>';
			}
			$out .= '</div>';
		}
		$placeholder = (string) Innomight_Search_Settings::get( 'placeholder' );
		$out        .= '<form class="innomight-search__form"><input type="text" maxlength="1000" autocomplete="off" placeholder="' . esc_attr( $placeholder ) . '" aria-label="' . esc_attr( $placeholder ) . '">'
			. '<button type="submit" aria-label="' . esc_attr__( 'Send', 'innomight-ai-search' ) . '">' . self::icon( 'send' ) . '</button></form>';
		$fine = (string) Innomight_Search_Settings::get( 'disclaimer' );
		if ( '' !== $fine ) {
			$out .= '<p class="innomight-search__fine">' . esc_html( $fine ) . '</p>';
		}
		return $out . '</section>';
	}

	private static function icon( string $name ): string {
		$paths = array(
			'spark' => '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>',
			'send'  => '<path d="M5 12h14m-6-6 6 6-6 6"/>',
		);
		return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' . $paths[ $name ] . '</svg>';
	}

	/* ------------------------------------------------------------ automatic placement on search results */

	private static function auto_ok( string $position ): bool {
		return ! is_admin() && is_search() && ! self::$rendered && Innomight_Search_Settings::is_ready()
			&& Innomight_Search_Settings::get( 'placement' ) === $position;
	}

	/** Block themes: wrap the main Query Loop block that shows the search results. */
	public static function place_in_block_theme( $content, $block ) {
		if ( empty( $block['blockName'] ) || 'core/query' !== $block['blockName'] || empty( $block['attrs']['query']['inherit'] ) ) {
			return $content;
		}
		foreach ( array( 'above', 'below' ) as $position ) {
			if ( self::auto_ok( $position ) ) {
				$card = self::render();
				return 'above' === $position ? $card . $content : $content . $card;
			}
		}
		return $content;
	}

	/** Classic themes: before and after the main loop. */
	public static function place_above_classic( $query ): void {
		if ( ! wp_is_block_theme() && $query instanceof WP_Query && $query->is_main_query() && self::auto_ok( 'above' ) ) {
			echo self::render(); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Built from escaped parts.
		}
	}

	public static function place_below_classic( $query ): void {
		if ( ! wp_is_block_theme() && $query instanceof WP_Query && $query->is_main_query() && self::auto_ok( 'below' ) ) {
			echo self::render(); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Built from escaped parts.
		}
	}
}
