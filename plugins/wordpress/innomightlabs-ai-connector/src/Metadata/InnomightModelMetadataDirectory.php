<?php
/**
 * Innomight Labs model metadata.
 *
 * @package InnomightLabsAIConnector
 */

declare(strict_types=1);

namespace InnomightLabs\AiConnector\Metadata;

use WordPress\AiClient\Common\Exception\InvalidArgumentException;
use WordPress\AiClient\Files\Enums\FileTypeEnum;
use WordPress\AiClient\Messages\Enums\ModalityEnum;
use WordPress\AiClient\Providers\Contracts\ModelMetadataDirectoryInterface;
use WordPress\AiClient\Providers\Models\DTO\ModelMetadata;
use WordPress\AiClient\Providers\Models\DTO\SupportedOption;
use WordPress\AiClient\Providers\Models\Enums\CapabilityEnum;
use WordPress\AiClient\Providers\Models\Enums\OptionEnum;

/**
 * Static model directory for the WordPress AI Client.
 */
final class InnomightModelMetadataDirectory implements ModelMetadataDirectoryInterface {
	public const MODEL_ID = 'innomight-memory-agent';

	/**
	 * List model metadata.
	 *
	 * @return array<int, ModelMetadata> Models.
	 */
	public function listModelMetadata(): array {
		$output_modalities = array( array( ModalityEnum::text() ) );
		$image_modality    = ModalityEnum::tryFrom( 'image' );
		if ( null !== $image_modality ) {
			$output_modalities[] = array( $image_modality );
		}

		$capabilities = array(
			CapabilityEnum::textGeneration(),
			CapabilityEnum::chatHistory(),
		);

		$image_generation = CapabilityEnum::tryFrom( 'image_generation' );
		if ( null !== $image_generation ) {
			$capabilities[] = $image_generation;
		}

		$options = array(
			new SupportedOption( OptionEnum::systemInstruction() ),
			new SupportedOption( OptionEnum::maxTokens() ),
			new SupportedOption( OptionEnum::temperature() ),
			new SupportedOption( OptionEnum::customOptions() ),
			new SupportedOption( OptionEnum::inputModalities(), array( array( ModalityEnum::text() ) ) ),
			new SupportedOption( OptionEnum::outputModalities(), $output_modalities ),
		);

		$output_media_aspect_ratio = OptionEnum::tryFrom( 'outputMediaAspectRatio' );
		if ( null !== $output_media_aspect_ratio ) {
			$options[] = new SupportedOption( $output_media_aspect_ratio );
		}

		$output_media_orientation = OptionEnum::tryFrom( 'outputMediaOrientation' );
		if ( null !== $output_media_orientation ) {
			$options[] = new SupportedOption( $output_media_orientation );
		}

		$output_mime_type = OptionEnum::tryFrom( 'outputMimeType' );
		if ( null !== $output_mime_type ) {
			$options[] = new SupportedOption( $output_mime_type, array( 'application/json', 'image/png', 'image/jpeg', 'image/webp' ) );
		}

		$output_schema = OptionEnum::tryFrom( 'outputSchema' );
		if ( null !== $output_schema ) {
			$options[] = new SupportedOption( $output_schema );
		}

		$candidate_count = OptionEnum::tryFrom( 'candidateCount' );
		if ( null !== $candidate_count ) {
			$options[] = new SupportedOption( $candidate_count );
		}

		$output_file_type = OptionEnum::tryFrom( 'outputFileType' );
		if ( null !== $output_file_type && class_exists( FileTypeEnum::class ) ) {
			$file_types = array();

			$remote_file_type = FileTypeEnum::tryFrom( 'remote' );
			if ( null !== $remote_file_type ) {
				$file_types[] = $remote_file_type;
			}

			$inline_file_type = FileTypeEnum::tryFrom( 'inline' );
			if ( null !== $inline_file_type ) {
				$file_types[] = $inline_file_type;
			}

			if ( array() !== $file_types ) {
				$options[] = new SupportedOption( $output_file_type, $file_types );
			}
		}

		return array(
			new ModelMetadata(
				self::MODEL_ID,
				'Innomight Memory Agent',
				$capabilities,
				$options
			),
		);
	}

	/**
	 * Check model metadata.
	 *
	 * @param string $modelId Model ID.
	 * @return bool Whether the model exists.
	 */
	public function hasModelMetadata( string $modelId ): bool {
		return self::MODEL_ID === $modelId;
	}

	/**
	 * Get model metadata.
	 *
	 * @param string $modelId Model ID.
	 * @return ModelMetadata Model metadata.
	 */
	public function getModelMetadata( string $modelId ): ModelMetadata {
		foreach ( $this->listModelMetadata() as $metadata ) {
			if ( $metadata->getId() === $modelId ) {
				return $metadata;
			}
		}

		throw new InvalidArgumentException( sprintf( 'Unknown Innomight Labs model: %s', $modelId ) );
	}
}
