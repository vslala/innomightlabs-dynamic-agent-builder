<?php
/**
 * Innomight Labs model metadata.
 *
 * @package InnomightLabsAIConnector
 */

declare(strict_types=1);

namespace InnomightLabs\AiConnector\Metadata;

use WordPress\AiClient\Common\Exception\InvalidArgumentException;
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
		return array(
			new ModelMetadata(
				self::MODEL_ID,
				'Innomight Memory Agent',
				array(
					CapabilityEnum::textGeneration(),
					CapabilityEnum::chatHistory(),
				),
				array(
					new SupportedOption( OptionEnum::systemInstruction() ),
					new SupportedOption( OptionEnum::maxTokens() ),
					new SupportedOption( OptionEnum::temperature() ),
					new SupportedOption( OptionEnum::customOptions() ),
					new SupportedOption( OptionEnum::inputModalities(), array( array( ModalityEnum::text() ) ) ),
					new SupportedOption( OptionEnum::outputModalities(), array( array( ModalityEnum::text() ) ) ),
				)
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
