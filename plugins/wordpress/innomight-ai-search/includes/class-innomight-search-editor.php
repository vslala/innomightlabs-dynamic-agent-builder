<?php
/**
 * Writing tools in the block editor: ask about or rewrite selected text, and the /ai block.
 *
 * Unlike the visitor chat, these send article text (the selection, a few blocks before it and the
 * post title) to the agent, because that text is what the writer is working on.
 *
 * @package InnomightAISearch
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class Innomight_Search_Editor {
	/** Editors and administrators. */
	public const CAPABILITY = 'edit_others_posts';

	public const INSTRUCTIONS = "You are the writing assistant inside the WordPress editor of {site} ({url}). You help the author research and write articles. Follow the output format asked for in each message exactly: when asked for text to insert, reply with that text only, with no preface, quotes or closing remarks.";

	/** What each rewrite action asks the agent to do. */
	private const REWRITES = array(
		'improve'      => 'Improve the clarity and flow of the text.',
		'grammar'      => 'Fix spelling, grammar and punctuation only. Change nothing else.',
		'shorten'      => 'Make the text shorter while keeping its meaning.',
		'expand'       => 'Expand the text with more detail and explanation.',
		'friendly'     => 'Rewrite the text in a warmer, friendlier tone.',
		'professional' => 'Rewrite the text in a more professional, formal tone.',
	);

	private const LENGTHS = array(
		'sentence'  => 'one sentence',
		'paragraph' => 'one paragraph',
		'section'   => 'a section of several paragraphs, with a heading if it helps',
	);

	public static function init(): void {
		add_action( 'init', array( self::class, 'register' ) );
		add_action( 'rest_api_init', array( self::class, 'register_routes' ) );
		add_action( 'enqueue_block_editor_assets', array( self::class, 'enqueue' ) );
	}

	public static function register(): void {
		wp_register_style( 'innomight-search-editor', INNOMIGHT_SEARCH_URL . 'assets/css/editor.css', array(), INNOMIGHT_SEARCH_VERSION );
		register_block_type( INNOMIGHT_SEARCH_DIR . 'blocks/ai-write' );
	}

	public static function register_routes(): void {
		register_rest_route(
			'innomight-search/v1',
			'/write',
			array(
				'methods'             => WP_REST_Server::CREATABLE,
				'callback'            => array( self::class, 'write' ),
				'permission_callback' => array( self::class, 'can_write' ),
				'args'                => array(
					'mode'      => array( 'type' => 'string', 'required' => true, 'enum' => array( 'ask', 'rewrite', 'generate' ) ),
					'action'    => array( 'type' => 'string', 'default' => '', 'maxLength' => 20 ),
					'length'    => array( 'type' => 'string', 'default' => 'paragraph', 'maxLength' => 20 ),
					'prompt'    => array( 'type' => 'string', 'default' => '', 'maxLength' => 2000 ),
					'selection' => array( 'type' => 'string', 'default' => '', 'maxLength' => 10000 ),
					'before'    => array( 'type' => 'string', 'default' => '', 'maxLength' => 6000 ),
					'title'     => array( 'type' => 'string', 'default' => '', 'maxLength' => 300 ),
				),
			)
		);
	}

	/** @return true|WP_Error */
	public static function can_write() {
		if ( ! current_user_can( self::CAPABILITY ) ) {
			return new WP_Error( 'innomight_search_forbidden', 'Only editors and administrators can use the writing assistant.', array( 'status' => 403 ) );
		}
		if ( ! Innomight_Search_Settings::is_configured() ) {
			return new WP_Error( 'innomight_search_unavailable', 'Add your agent ID and secret key under Settings → InnomightLabs AI first.', array( 'status' => 503 ) );
		}
		return true;
	}

	public static function enqueue(): void {
		if ( true !== self::can_write() ) {
			return;
		}
		wp_enqueue_style( 'innomight-search-editor' );
		wp_enqueue_script(
			'innomight-search-editor',
			INNOMIGHT_SEARCH_URL . 'assets/js/editor.js',
			array( 'wp-blocks', 'wp-block-editor', 'wp-components', 'wp-data', 'wp-element', 'wp-i18n', 'wp-rich-text' ),
			INNOMIGHT_SEARCH_VERSION,
			true
		);
		wp_add_inline_script(
			'innomight-search-editor',
			'window.innomightWrite = ' . wp_json_encode( array( 'url' => rest_url( 'innomight-search/v1/write' ), 'nonce' => wp_create_nonce( 'wp_rest' ) ) ) . ';',
			'before'
		);
	}

	/**
	 * Streams the agent's answer as Server-Sent Events. Each request is its own short conversation,
	 * because every action is self-contained.
	 *
	 * @return WP_Error|void
	 */
	public static function write( WP_REST_Request $request ) {
		$permission = self::can_write();
		if ( is_wp_error( $permission ) ) {
			return $permission;
		}
		$mode      = (string) $request->get_param( 'mode' );
		$action    = (string) $request->get_param( 'action' );
		$selection = trim( sanitize_textarea_field( (string) $request->get_param( 'selection' ) ) );
		$prompt    = trim( sanitize_textarea_field( (string) $request->get_param( 'prompt' ) ) );
		if ( 'rewrite' === $mode && ( '' === $selection || ! isset( self::REWRITES[ $action ] ) ) ) {
			return new WP_Error( 'innomight_search_invalid_request', 'Select some text and choose a rewrite action.', array( 'status' => 400 ) );
		}
		if ( 'rewrite' !== $mode && '' === $prompt ) {
			return new WP_Error( 'innomight_search_invalid_request', 'Enter a question or a description first.', array( 'status' => 400 ) );
		}
		$message = self::build_prompt(
			$mode,
			$action,
			$prompt,
			$selection,
			trim( sanitize_textarea_field( (string) $request->get_param( 'before' ) ) ),
			sanitize_text_field( (string) $request->get_param( 'title' ) ),
			(string) $request->get_param( 'length' )
		);

		$end_user        = 'wp-user:' . get_current_user_id();
		$conversation_id = Innomight_Search_API::create_conversation(
			$end_user,
			'Editor: ' . $mode,
			Innomight_Search_Chat::build_context( self::INSTRUCTIONS, '' )
		);
		if ( is_wp_error( $conversation_id ) ) {
			return $conversation_id;
		}
		Innomight_Search_Chat::stream_reply( $end_user, $conversation_id, $message );
	}

	/** The message sent to the agent. Exposed for tests. */
	public static function build_prompt( string $mode, string $action, string $prompt, string $selection, string $before, string $title, string $length ): string {
		$parts = array();
		if ( '' !== $title ) {
			$parts[] = 'Post title: ' . $title;
		}
		if ( '' !== $before ) {
			$parts[] = "The article so far, for context:\n\"\"\"\n" . $before . "\n\"\"\"";
		}
		switch ( $mode ) {
			case 'rewrite':
				$parts[] = "Text to rewrite:\n\"\"\"\n" . $selection . "\n\"\"\"";
				$parts[] = self::REWRITES[ $action ] . ' Keep the same language. Reply with only the replacement text as plain text, without quotes, Markdown or explanation.';
				break;
			case 'ask':
				if ( '' !== $selection ) {
					$parts[] = "The author selected this text:\n\"\"\"\n" . $selection . "\n\"\"\"";
				}
				$parts[] = 'The author asks: ' . $prompt;
				$parts[] = 'Answer concisely in Markdown. Use your tools to look things up when that helps, and give the title and link of any source you used.';
				break;
			default:
				$parts[] = 'Write ' . ( self::LENGTHS[ $length ] ?? self::LENGTHS['paragraph'] ) . ' for the article about the following: ' . $prompt;
				$parts[] = 'Match the voice of the article so far and continue from it naturally. Reply with only the text to insert, in Markdown if it needs headings or lists, with no preface or closing remarks.';
		}
		return implode( "\n\n", $parts );
	}
}
