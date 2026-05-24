<?php
/**
 * WordPress AI Client provider for Innomight Labs.
 *
 * @package InnomightLabsAIConnector
 */

declare(strict_types=1);

namespace InnomightLabs\AiConnector\Provider;

use InnomightLabs\AiConnector\Availability\InnomightProviderAvailability;
use InnomightLabs\AiConnector\Metadata\InnomightModelMetadataDirectory;
use InnomightLabs\AiConnector\Models\InnomightTextGenerationModel;
use WordPress\AiClient\AiClient;
use WordPress\AiClient\Common\Exception\RuntimeException;
use WordPress\AiClient\Providers\AbstractProvider;
use WordPress\AiClient\Providers\Contracts\ModelMetadataDirectoryInterface;
use WordPress\AiClient\Providers\Contracts\ProviderAvailabilityInterface;
use WordPress\AiClient\Providers\DTO\ProviderMetadata;
use WordPress\AiClient\Providers\Enums\ProviderTypeEnum;
use WordPress\AiClient\Providers\Http\Enums\RequestAuthenticationMethod;
use WordPress\AiClient\Providers\Models\Contracts\ModelInterface;
use WordPress\AiClient\Providers\Models\DTO\ModelMetadata;

/**
 * Innomight Labs provider implementation.
 */
final class InnomightProvider extends AbstractProvider {
	/**
	 * Create model instance.
	 *
	 * @param ModelMetadata    $modelMetadata Model metadata.
	 * @param ProviderMetadata $providerMetadata Provider metadata.
	 * @return ModelInterface Model instance.
	 */
	protected static function createModel( ModelMetadata $modelMetadata, ProviderMetadata $providerMetadata ): ModelInterface {
		foreach ( $modelMetadata->getSupportedCapabilities() as $capability ) {
			if ( $capability->isTextGeneration() ) {
				return new InnomightTextGenerationModel( $modelMetadata, $providerMetadata );
			}
		}

		throw new RuntimeException( 'Unsupported Innomight Labs model capability.' );
	}

	/**
	 * Create provider metadata.
	 *
	 * @return ProviderMetadata Provider metadata.
	 */
	protected static function createProviderMetadata(): ProviderMetadata {
		$args = array(
			'innomight',
			'Innomight Labs',
			ProviderTypeEnum::cloud(),
			'https://innomightlabs.com/dashboard/api-keys',
			RequestAuthenticationMethod::apiKey(),
		);

		if ( version_compare( AiClient::VERSION, '1.2.0', '>=' ) ) {
			$args[] = __( 'Long-term memory AI agent API for WordPress sites.', 'innomightlabs-ai-connector' );
		}

		if ( version_compare( AiClient::VERSION, '1.3.0', '>=' ) ) {
			$args[] = INNOMIGHT_AI_CONNECTOR_DIR . 'assets/logo.svg';
		}

		return new ProviderMetadata( ...$args );
	}

	/**
	 * Create availability checker.
	 *
	 * @return ProviderAvailabilityInterface Availability checker.
	 */
	protected static function createProviderAvailability(): ProviderAvailabilityInterface {
		return new InnomightProviderAvailability();
	}

	/**
	 * Create model metadata directory.
	 *
	 * @return ModelMetadataDirectoryInterface Model metadata directory.
	 */
	protected static function createModelMetadataDirectory(): ModelMetadataDirectoryInterface {
		return new InnomightModelMetadataDirectory();
	}
}
