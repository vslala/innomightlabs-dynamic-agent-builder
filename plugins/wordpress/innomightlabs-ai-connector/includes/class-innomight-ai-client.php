<?php
/**
 * Innomight Labs backend HTTP client.
 *
 * @package InnomightLabsAIConnector
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Minimal WordPress HTTP API wrapper for the Innomight Labs backend.
 */
final class Innomight_AI_Client {
	/**
	 * Backend base URL.
	 *
	 * @var string
	 */
	private string $base_url;

	/**
	 * Constructor.
	 *
	 * @param string|null $base_url Optional backend base URL.
	 */
	public function __construct( ?string $base_url = null ) {
		$this->base_url = untrailingslashit( $base_url ?: innomight_ai_get_api_base_url() );
	}

	/**
	 * Check backend health.
	 *
	 * @return array|WP_Error Backend response.
	 */
	public function health() {
		return $this->request(
			'GET',
			'/health',
			array(),
			array(
				'requires_api_key' => false,
				'timeout'          => 10,
			)
		);
	}

	/**
	 * Fetch widget configuration for the configured widget API key.
	 *
	 * @return array|WP_Error Backend response.
	 */
	public function get_widget_config() {
		return $this->request( 'GET', '/widget/config' );
	}

	/**
	 * Generate an image through the configured Innomight Labs agent.
	 *
	 * @param string $prompt Image prompt.
	 * @param array  $context Optional request context.
	 * @param array  $options Optional image options.
	 * @return array|WP_Error Backend response.
	 */
	public function generate_image( string $prompt, array $context = array(), array $options = array() ) {
		return $this->generate_image_stream( $prompt, $context, $options );
	}

	/**
	 * Generate an image through the backend SSE endpoint and buffer the final image event.
	 *
	 * @param string $prompt Image prompt.
	 * @param array  $context Optional request context.
	 * @param array  $options Optional image options.
	 * @return array|WP_Error Backend-style image response.
	 */
	public function generate_image_stream( string $prompt, array $context = array(), array $options = array() ) {
		$body = array_merge(
			array(
				'prompt'  => $prompt,
				'context' => array_merge(
					innomight_ai_get_wordpress_context(),
					$context
				),
			),
			$options
		);

		$response = $this->request(
			'POST',
			'/widget/generate-image-stream',
			$body,
			array(
				'timeout' => 120,
			)
		);

		if ( is_wp_error( $response ) ) {
			return $response;
		}

		return $this->parse_image_stream_response( $response );
	}

	/**
	 * Send a request to the Innomight Labs backend.
	 *
	 * @param string $method HTTP method.
	 * @param string $path Relative backend path.
	 * @param array  $body JSON body.
	 * @param array  $args Request args.
	 * @return array|WP_Error Parsed response.
	 */
	public function request( string $method, string $path, array $body = array(), array $args = array() ) {
		$method           = strtoupper( $method );
		$requires_api_key = array_key_exists( 'requires_api_key', $args ) ? (bool) $args['requires_api_key'] : true;
		$api_key          = innomight_ai_get_api_key();

		if ( $requires_api_key && null === $api_key ) {
			return new WP_Error(
				'innomight_missing_api_key',
				__( 'Innomight Labs API key is not configured.', 'innomightlabs-ai-connector' )
			);
		}

		$path = '/' . ltrim( $path, '/' );
		if ( false !== strpos( $path, '://' ) ) {
			return new WP_Error(
				'innomight_invalid_path',
				__( 'Innomight Labs request path must be relative.', 'innomightlabs-ai-connector' )
			);
		}

		$headers = array(
			'Accept'     => 'application/json',
			'Origin'     => home_url(),
			'User-Agent' => $this->user_agent(),
		);

		if ( null !== $api_key ) {
			$headers['X-API-Key'] = $api_key;
		}

		if ( ! empty( $args['visitor_token'] ) && is_string( $args['visitor_token'] ) ) {
			$headers['Authorization'] = 'Bearer ' . trim( $args['visitor_token'] );
		}

		if ( 'GET' !== $method ) {
			$headers['Content-Type'] = 'application/json';
		}

		if ( ! empty( $args['headers'] ) && is_array( $args['headers'] ) ) {
			$headers = array_merge( $headers, $args['headers'] );
		}

		$request_args = array(
			'method'  => $method,
			'timeout' => isset( $args['timeout'] ) ? absint( $args['timeout'] ) : 30,
			'headers' => $headers,
		);

		if ( 'GET' !== $method ) {
			$request_args['body'] = wp_json_encode( $body );
		}

		$response = wp_remote_request( $this->base_url . $path, $request_args );
		if ( is_wp_error( $response ) ) {
			return $response;
		}

		return $this->parse_response( $response );
	}

	/**
	 * Parse a WordPress HTTP API response.
	 *
	 * @param array $response HTTP response.
	 * @return array|WP_Error Parsed response.
	 */
	private function parse_response( array $response ) {
		$status       = wp_remote_retrieve_response_code( $response );
		$content_type = wp_remote_retrieve_header( $response, 'content-type' );
		$raw_body     = wp_remote_retrieve_body( $response );

		$data = null;
		if ( '' !== trim( $raw_body ) && ( ! is_string( $content_type ) || false !== strpos( $content_type, 'json' ) ) ) {
			$data = json_decode( $raw_body, true );
		}

		if ( $status < 200 || $status >= 300 ) {
			return new WP_Error(
				'innomight_api_error',
				$this->error_message( $data, $status ),
				array(
					'status' => $status,
				)
			);
		}

		if ( is_array( $data ) ) {
			return $data;
		}

		return array(
			'status' => $status,
			'body'   => $raw_body,
		);
	}

	/**
	 * Extract a useful error message without leaking credentials.
	 *
	 * @param mixed $data Parsed response data.
	 * @param int   $status HTTP status code.
	 * @return string Error message.
	 */
	private function error_message( $data, int $status ): string {
		if ( is_array( $data ) ) {
			if ( isset( $data['detail'] ) && is_string( $data['detail'] ) ) {
				return sanitize_text_field( $data['detail'] );
			}

			if ( isset( $data['detail'] ) && is_array( $data['detail'] ) ) {
				$detail = wp_json_encode( $data['detail'] );
				if ( is_string( $detail ) && '' !== $detail ) {
					return sanitize_text_field( $detail );
				}
			}

			if ( isset( $data['error']['message'] ) && is_string( $data['error']['message'] ) ) {
				return sanitize_text_field( $data['error']['message'] );
			}
		}

		return sprintf(
			/* translators: %d: HTTP status code. */
			__( 'Innomight Labs API request failed with HTTP status %d.', 'innomightlabs-ai-connector' ),
			$status
		);
	}

	/**
	 * Parse buffered SSE image events into the normal image response shape.
	 *
	 * @param array<string, mixed> $response Parsed response wrapper.
	 * @return array|WP_Error Image response.
	 */
	private function parse_image_stream_response( array $response ) {
		$raw_body = isset( $response['body'] ) && is_string( $response['body'] ) ? $response['body'] : '';
		if ( '' === trim( $raw_body ) ) {
			return new WP_Error(
				'innomight_empty_image_stream',
				__( 'Innomight Labs image stream did not return any events.', 'innomightlabs-ai-connector' )
			);
		}

		$complete_event = null;
		$partial_image  = null;
		foreach ( preg_split( "/\r?\n\r?\n/", trim( $raw_body ) ) as $event_block ) {
			foreach ( preg_split( "/\r?\n/", trim( $event_block ) ) as $line ) {
				if ( 0 !== strpos( $line, 'data:' ) ) {
					continue;
				}

				$data = json_decode( trim( substr( $line, 5 ) ), true );
				if ( ! is_array( $data ) ) {
					continue;
				}

				if ( isset( $data['event_type'] ) && 'ERROR' === $data['event_type'] ) {
					return new WP_Error(
						'innomight_image_stream_error',
						isset( $data['content'] ) && is_string( $data['content'] ) ? sanitize_text_field( $data['content'] ) : __( 'Innomight Labs image stream failed.', 'innomightlabs-ai-connector' )
					);
				}

				if ( isset( $data['event_type'] ) && 'IMAGE_GENERATION_COMPLETE' === $data['event_type'] ) {
					$complete_event = $data;
				}

				if ( isset( $data['event_type'] ) && 'IMAGE_GENERATION_PARTIAL' === $data['event_type'] && ! empty( $data['image_b64'] ) && is_string( $data['image_b64'] ) ) {
					$partial_image = $data;
				}
			}
		}

		if ( ! is_array( $complete_event ) ) {
			return new WP_Error(
				'innomight_missing_image_complete_event',
				__( 'Innomight Labs image stream did not include a completion event.', 'innomightlabs-ai-connector' )
			);
		}

		$images = array();
		if ( isset( $complete_event['images'] ) && is_array( $complete_event['images'] ) ) {
			foreach ( $complete_event['images'] as $image ) {
				if ( is_array( $image ) ) {
					$images[] = $this->normalize_stream_image( $image );
				}
			}
		} elseif ( ! empty( $complete_event['image_url'] ) && is_string( $complete_event['image_url'] ) ) {
			$images[] = $this->normalize_stream_image( $complete_event );
		}

		if ( null !== $partial_image && isset( $images[0] ) && empty( $images[0]['base64'] ) ) {
			$images[0]['base64']    = $partial_image['image_b64'];
			$images[0]['mime_type'] = isset( $partial_image['image_mime_type'] ) && is_string( $partial_image['image_mime_type'] ) ? $partial_image['image_mime_type'] : $images[0]['mime_type'];
			$images[0]['width']     = isset( $partial_image['image_width'] ) && null !== $partial_image['image_width'] ? absint( $partial_image['image_width'] ) : $images[0]['width'];
			$images[0]['height']    = isset( $partial_image['image_height'] ) && null !== $partial_image['image_height'] ? absint( $partial_image['image_height'] ) : $images[0]['height'];
		}

		if ( array() === $images ) {
			return new WP_Error(
				'innomight_missing_image_output',
				__( 'Innomight Labs image stream did not include image output.', 'innomightlabs-ai-connector' )
			);
		}

		return array(
			'images'           => $images,
			'conversation_id'  => isset( $complete_event['conversation_id'] ) && is_string( $complete_event['conversation_id'] ) ? $complete_event['conversation_id'] : '',
			'message_ids'      => array(
				'assistant_message_id' => isset( $complete_event['message_id'] ) && is_string( $complete_event['message_id'] ) ? $complete_event['message_id'] : '',
			),
			'stream_complete'  => true,
			'stream_raw_event' => $complete_event,
		);
	}

	/**
	 * Normalize one stream image item.
	 *
	 * @param array<string, mixed> $image Stream image event or image item.
	 * @return array<string, mixed> Normalized image.
	 */
	private function normalize_stream_image( array $image ): array {
		return array(
			'url'       => isset( $image['url'] ) && is_string( $image['url'] ) ? $image['url'] : ( isset( $image['image_url'] ) && is_string( $image['image_url'] ) ? $image['image_url'] : null ),
			'base64'    => isset( $image['base64'] ) && is_string( $image['base64'] ) ? $image['base64'] : ( isset( $image['image_b64'] ) && is_string( $image['image_b64'] ) ? $image['image_b64'] : null ),
			'mime_type' => isset( $image['mime_type'] ) && is_string( $image['mime_type'] ) ? $image['mime_type'] : ( isset( $image['image_mime_type'] ) && is_string( $image['image_mime_type'] ) ? $image['image_mime_type'] : 'image/png' ),
			'width'     => isset( $image['width'] ) ? absint( $image['width'] ) : ( isset( $image['image_width'] ) ? absint( $image['image_width'] ) : null ),
			'height'    => isset( $image['height'] ) ? absint( $image['height'] ) : ( isset( $image['image_height'] ) ? absint( $image['image_height'] ) : null ),
		);
	}

	/**
	 * Build plugin user agent.
	 *
	 * @return string User agent.
	 */
	private function user_agent(): string {
		return sprintf(
			'InnomightAIConnector/%s; WordPress/%s; %s',
			INNOMIGHT_AI_CONNECTOR_VERSION,
			get_bloginfo( 'version' ),
			home_url()
		);
	}
}
