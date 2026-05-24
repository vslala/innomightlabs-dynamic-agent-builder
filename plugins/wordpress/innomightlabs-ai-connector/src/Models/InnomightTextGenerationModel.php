<?php
/**
 * Text generation model adapter.
 *
 * @package InnomightLabsAIConnector
 */

declare(strict_types=1);

namespace InnomightLabs\AiConnector\Models;

use WordPress\AiClient\Common\Exception\RuntimeException;
use WordPress\AiClient\Messages\DTO\Message;
use WordPress\AiClient\Messages\DTO\MessagePart;
use WordPress\AiClient\Messages\DTO\ModelMessage;
use WordPress\AiClient\Providers\ApiBasedImplementation\AbstractApiBasedModel;
use WordPress\AiClient\Providers\Models\TextGeneration\Contracts\TextGenerationModelInterface;
use WordPress\AiClient\Results\DTO\Candidate;
use WordPress\AiClient\Results\DTO\GenerativeAiResult;
use WordPress\AiClient\Results\DTO\TokenUsage;
use WordPress\AiClient\Results\Enums\FinishReasonEnum;

/**
 * Minimal text generation model for Innomight Labs.
 */
final class InnomightTextGenerationModel extends AbstractApiBasedModel implements TextGenerationModelInterface {
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
				'message' => $this->build_backend_message( $text, $system_instruction ),
				'context' => array(
					'source'             => 'wordpress_ai_client',
					'site_url'           => home_url(),
					'system_instruction' => $system_instruction,
					'model_config'       => $config->toArray(),
				),
				'model'   => $this->metadata()->getId(),
			)
		);

		if ( is_wp_error( $response ) ) {
			throw new RuntimeException( $response->get_error_message() );
		}

		$output = $this->extract_response_text( $response );
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
	 * @return string Backend message.
	 */
	private function build_backend_message( string $text, ?string $system_instruction ): string {
		$system_instruction = is_string( $system_instruction ) ? trim( $system_instruction ) : '';
		if ( '' === $system_instruction ) {
			return $text;
		}

		return sprintf(
			"Instruction:\n%s\n\nInput:\n%s",
			$system_instruction,
			$text
		);
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
}
