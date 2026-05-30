<?php
/**
 * Text generation model adapter.
 *
 * @package InnomightLabsAIConnector
 */

declare(strict_types=1);

namespace InnomightLabs\AiConnector\Models;

use WordPress\AiClient\Common\Exception\RuntimeException;
use WordPress\AiClient\Files\DTO\File;
use WordPress\AiClient\Messages\DTO\Message;
use WordPress\AiClient\Messages\DTO\MessagePart;
use WordPress\AiClient\Messages\DTO\ModelMessage;
use WordPress\AiClient\Messages\Enums\MessageRoleEnum;
use WordPress\AiClient\Providers\ApiBasedImplementation\AbstractApiBasedModel;
use WordPress\AiClient\Providers\Models\ImageGeneration\Contracts\ImageGenerationModelInterface;
use WordPress\AiClient\Providers\Models\TextGeneration\Contracts\TextGenerationModelInterface;
use WordPress\AiClient\Results\DTO\Candidate;
use WordPress\AiClient\Results\DTO\GenerativeAiResult;
use WordPress\AiClient\Results\DTO\TokenUsage;
use WordPress\AiClient\Results\Enums\FinishReasonEnum;

/**
 * Minimal generation model for Innomight Labs.
 */
final class InnomightTextGenerationModel extends AbstractApiBasedModel implements TextGenerationModelInterface, ImageGenerationModelInterface {
	/**
	 * Generate text result.
	 *
	 * @param array<int, Message> $prompt Prompt messages.
	 * @return GenerativeAiResult Result.
	 */
	public function generateTextResult( array $prompt ): GenerativeAiResult {
		$text = $this->prompt_to_text( $prompt );
		$config = $this->getConfig();
		$system_instruction = $config->getSystemInstruction();

		if ( '' === $text ) {
			throw new RuntimeException( 'Innomight Labs prompt is empty.' );
		}

		$path = apply_filters( 'innomight_ai_text_generation_path', '/widget/generate-text' );
		if ( ! is_string( $path ) || '' === trim( $path ) ) {
			throw new RuntimeException( 'Innomight Labs text generation endpoint is not configured.' );
		}

		$response = \innomight_ai_request(
			'POST',
			$path,
			array(
				'message' => $this->build_backend_message( $text, $system_instruction, $config ),
				'context' => array_merge(
					\innomight_ai_get_wordpress_context(),
					array(
						'system_instruction' => $system_instruction,
						'model_config'       => $config->toArray(),
					)
				),
				'model'   => $this->metadata()->getId(),
			)
		);

		if ( is_wp_error( $response ) ) {
			throw new RuntimeException( $response->get_error_message() );
		}

		$output = $this->extract_response_text( $response );
		if ( $this->is_json_response() ) {
			$output = $this->normalize_json_response( $output );
		}
		if ( '' === $output ) {
			throw new RuntimeException( 'Innomight Labs response did not include text output.' );
		}

		return new GenerativeAiResult(
			wp_generate_uuid4(),
			array(
				new Candidate(
					new ModelMessage( array( new MessagePart( $output ) ) ),
					FinishReasonEnum::stop()
				),
			),
			new TokenUsage( 0, 0, 0 ),
			$this->providerMetadata(),
			$this->metadata(),
			array( 'raw' => $response )
		);
	}

	/**
	 * Generate image result.
	 *
	 * @param array<int, Message> $prompt Prompt messages.
	 * @return GenerativeAiResult Result.
	 */
	public function generateImageResult( array $prompt ): GenerativeAiResult {
		$text = $this->prompt_to_text( $prompt );
		if ( '' === $text ) {
			throw new RuntimeException( 'Innomight Labs image prompt is empty.' );
		}

		$response = \innomight_ai_generate_image(
			$text,
			array_merge(
				\innomight_ai_get_wordpress_context(),
				array(
					'model_config' => $this->getConfig()->toArray(),
				)
			),
			$this->image_request_options()
		);

		if ( is_wp_error( $response ) ) {
			throw new RuntimeException( $response->get_error_message() );
		}

		$candidates = $this->extract_image_candidates( $response );
		if ( array() === $candidates ) {
			throw new RuntimeException( 'Innomight Labs response did not include image output.' );
		}

		return new GenerativeAiResult(
			wp_generate_uuid4(),
			$candidates,
			new TokenUsage( 0, 0, 0 ),
			$this->providerMetadata(),
			$this->metadata(),
			array( 'raw' => $response )
		);
	}

	/**
	 * Convert prompt messages into plain text.
	 *
	 * @param array<int, Message> $prompt Prompt messages.
	 * @return string Text prompt.
	 */
	private function prompt_to_text( array $prompt ): string {
		$lines = array();
		foreach ( $prompt as $message ) {
			if ( ! $message instanceof Message ) {
				continue;
			}
			foreach ( $message->getParts() as $part ) {
				if ( $part instanceof MessagePart && null !== $part->getText() ) {
					$lines[] = $part->getText();
				}
			}
		}

		return trim( implode( "\n\n", $lines ) );
	}

	/**
	 * Build an explicit backend message from AI Client instructions and input.
	 *
	 * @param string      $text Prompt text from message parts.
	 * @param string|null $system_instruction Optional AI Client system instruction.
	 * @param mixed       $config Model config.
	 * @return string Backend message.
	 */
	private function build_backend_message( string $text, ?string $system_instruction, $config ): string {
		$sections = array();
		$system_instruction = is_string( $system_instruction ) ? trim( $system_instruction ) : '';
		if ( '' !== $system_instruction ) {
			$sections[] = "Instruction:\n" . $system_instruction;
		}

		if ( $this->is_json_response() ) {
			$json_instruction = "Output requirement:\nReturn only valid JSON. Do not include markdown fences, commentary, or explanatory text.";
			if ( method_exists( $config, 'getOutputSchema' ) ) {
				$output_schema = $config->getOutputSchema();
				if ( is_array( $output_schema ) ) {
					$json_instruction .= "\nThe JSON must conform to this schema:\n" . wp_json_encode( $output_schema );
				}
			}

			$sections[] = $json_instruction;
		}

		$sections[] = "Input:\n" . $text;

		return implode( "\n\n", $sections );
	}

	/**
	 * Extract text from common backend response shapes.
	 *
	 * @param array<string, mixed> $response Parsed response.
	 * @return string Text output.
	 */
	private function extract_response_text( array $response ): string {
		foreach ( array( 'text', 'content', 'response', 'message', 'output' ) as $key ) {
			if ( isset( $response[ $key ] ) && is_string( $response[ $key ] ) ) {
				return trim( $response[ $key ] );
			}
		}

		if ( isset( $response['data'] ) && is_array( $response['data'] ) ) {
			return $this->extract_response_text( $response['data'] );
		}

		return '';
	}

	/**
	 * Check whether the current call expects JSON text.
	 *
	 * @return bool Whether JSON output was requested.
	 */
	private function is_json_response(): bool {
		$config = $this->getConfig();
		if ( ! method_exists( $config, 'getOutputMimeType' ) ) {
			return false;
		}

		return 'application/json' === $config->getOutputMimeType();
	}

	/**
	 * Normalize backend text into a JSON string for AI Client JSON abilities.
	 *
	 * @param string $output Backend output.
	 * @return string JSON string, or original output when it cannot be normalized.
	 */
	private function normalize_json_response( string $output ): string {
		$output = trim( $output );
		if ( '' === $output ) {
			return '';
		}

		$output = preg_replace( '/^```(?:json)?\s*/i', '', $output ) ?? $output;
		$output = preg_replace( '/\s*```$/', '', $output ) ?? $output;
		$output = trim( $output );

		$decoded = json_decode( $output, true );
		if ( null === $decoded && JSON_ERROR_NONE !== json_last_error() ) {
			$json_fragment = $this->extract_json_fragment( $output );
			if ( null !== $json_fragment ) {
				$decoded = json_decode( $json_fragment, true );
				if ( JSON_ERROR_NONE === json_last_error() ) {
					$output = $json_fragment;
				}
			}
		}

		if ( null === $decoded && JSON_ERROR_NONE !== json_last_error() ) {
			return $output;
		}

		if ( is_array( $decoded ) && array_is_list( $decoded ) && $this->output_schema_has_property( 'suggestions' ) ) {
			$decoded = array( 'suggestions' => $decoded );
		}

		$encoded = wp_json_encode( $decoded );
		return is_string( $encoded ) ? $encoded : $output;
	}

	/**
	 * Extract the first top-level JSON object or array from text.
	 *
	 * @param string $text Text that may contain JSON.
	 * @return string|null JSON fragment.
	 */
	private function extract_json_fragment( string $text ): ?string {
		foreach ( array( array( '{', '}' ), array( '[', ']' ) ) as $pair ) {
			$start = strpos( $text, $pair[0] );
			$end   = strrpos( $text, $pair[1] );
			if ( false !== $start && false !== $end && $end > $start ) {
				return substr( $text, $start, $end - $start + 1 );
			}
		}

		return null;
	}

	/**
	 * Check whether the configured JSON schema contains a top-level property.
	 *
	 * @param string $property Property name.
	 * @return bool Whether the property exists in the output schema.
	 */
	private function output_schema_has_property( string $property ): bool {
		$config = $this->getConfig();
		if ( ! method_exists( $config, 'getOutputSchema' ) ) {
			return false;
		}

		$output_schema = $config->getOutputSchema();
		return is_array( $output_schema )
			&& isset( $output_schema['properties'] )
			&& is_array( $output_schema['properties'] )
			&& array_key_exists( $property, $output_schema['properties'] );
	}

	/**
	 * Build image request options from AI Client model config.
	 *
	 * @return array<string, mixed> Backend request options.
	 */
	private function image_request_options(): array {
		$config  = $this->getConfig();
		$options = array();

		if ( method_exists( $config, 'getOutputMimeType' ) ) {
			$output_mime_type = $config->getOutputMimeType();
			if ( is_string( $output_mime_type ) && '' !== $output_mime_type ) {
				$options['output_format'] = preg_replace( '/^image\//', '', $output_mime_type );
			}
		}

		if ( method_exists( $config, 'getOutputMediaAspectRatio' ) ) {
			$aspect_ratio = $config->getOutputMediaAspectRatio();
			if ( is_string( $aspect_ratio ) && '' !== $aspect_ratio ) {
				$options['size'] = $this->size_from_aspect_ratio( $aspect_ratio );
			}
		}

		if ( ! isset( $options['size'] ) && method_exists( $config, 'getOutputMediaOrientation' ) ) {
			$orientation = $config->getOutputMediaOrientation();
			if ( null !== $orientation && method_exists( $orientation, 'isPortrait' ) ) {
				$options['size'] = $orientation->isPortrait() ? '1024x1536' : '1536x1024';
			}
		}

		if ( method_exists( $config, 'getCustomOptions' ) ) {
			foreach ( $config->getCustomOptions() as $key => $value ) {
				if ( is_string( $key ) && ! array_key_exists( $key, $options ) ) {
					$options[ $key ] = $value;
				}
			}
		}

		return $options;
	}

	/**
	 * Convert common aspect ratios to backend image sizes.
	 *
	 * @param string $aspect_ratio Requested aspect ratio.
	 * @return string Image size.
	 */
	private function size_from_aspect_ratio( string $aspect_ratio ): string {
		switch ( $aspect_ratio ) {
			case '2:3':
			case '4:7':
				return '1024x1536';
			case '3:2':
			case '7:4':
				return '1536x1024';
			case '1:1':
			default:
				return '1024x1024';
		}
	}

	/**
	 * Extract image candidates from the backend response.
	 *
	 * @param array<string, mixed> $response Parsed response.
	 * @return array<int, Candidate> Image candidates.
	 */
	private function extract_image_candidates( array $response ): array {
		$images = array();
		if ( isset( $response['images'] ) && is_array( $response['images'] ) ) {
			$images = $response['images'];
		} elseif ( isset( $response['data']['images'] ) && is_array( $response['data']['images'] ) ) {
			$images = $response['data']['images'];
		}

		$candidates = array();
		foreach ( $images as $image ) {
			if ( ! is_array( $image ) ) {
				continue;
			}

			$file = $this->image_to_file( $image );
			if ( null === $file ) {
				continue;
			}

			$candidates[] = new Candidate(
				new Message( MessageRoleEnum::model(), array( new MessagePart( $file ) ) ),
				FinishReasonEnum::stop()
			);
		}

		return $candidates;
	}

	/**
	 * Convert one backend image item to an AI Client file.
	 *
	 * @param array<string, mixed> $image Backend image item.
	 * @return File|null Image file.
	 */
	private function image_to_file( array $image ): ?File {
		$mime_type = isset( $image['mime_type'] ) && is_string( $image['mime_type'] ) ? $image['mime_type'] : 'image/png';

		foreach ( array( 'b64_json', 'base64', 'base64_data' ) as $key ) {
			if ( isset( $image[ $key ] ) && is_string( $image[ $key ] ) && '' !== trim( $image[ $key ] ) ) {
				return new File( trim( $image[ $key ] ), $mime_type );
			}
		}

		if ( isset( $image['url'] ) && is_string( $image['url'] ) && '' !== trim( $image['url'] ) ) {
			$url = trim( $image['url'] );
			if ( $this->should_return_inline_image() ) {
				$inline_file = $this->remote_image_to_inline_file( $url, $mime_type );
				if ( null !== $inline_file ) {
					return $inline_file;
				}
			}

			return new File( $url, $mime_type );
		}

		return null;
	}

	/**
	 * Check whether the caller requested inline image data.
	 *
	 * @return bool Whether inline output was requested.
	 */
	private function should_return_inline_image(): bool {
		$config = $this->getConfig();
		if ( ! method_exists( $config, 'getOutputFileType' ) ) {
			return false;
		}

		$output_file_type = $config->getOutputFileType();
		return null !== $output_file_type && method_exists( $output_file_type, 'isInline' ) && $output_file_type->isInline();
	}

	/**
	 * Download a remote image and convert it to an inline AI Client file.
	 *
	 * @param string $url Remote image URL.
	 * @param string $mime_type Expected MIME type.
	 * @return File|null Inline image file, or null when download fails.
	 */
	private function remote_image_to_inline_file( string $url, string $mime_type ): ?File {
		$response = wp_remote_get(
			$url,
			array(
				'timeout' => 60,
				'headers' => array(
					'Accept'     => 'image/*,*/*;q=0.8',
					'User-Agent' => 'InnomightAIConnector/' . INNOMIGHT_AI_CONNECTOR_VERSION,
				),
			)
		);

		if ( is_wp_error( $response ) ) {
			return null;
		}

		$status = wp_remote_retrieve_response_code( $response );
		if ( $status < 200 || $status >= 300 ) {
			return null;
		}

		$body = wp_remote_retrieve_body( $response );
		if ( '' === $body ) {
			return null;
		}

		$content_type = wp_remote_retrieve_header( $response, 'content-type' );
		if ( is_string( $content_type ) && false !== strpos( $content_type, 'image/' ) ) {
			$mime_type = trim( explode( ';', $content_type )[0] );
		}

		return new File( base64_encode( $body ), $mime_type );
	}
}
