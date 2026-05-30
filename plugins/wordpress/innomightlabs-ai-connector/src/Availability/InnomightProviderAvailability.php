<?php
/**
 * Provider availability checker.
 *
 * @package InnomightLabsAIConnector
 */

declare(strict_types=1);

namespace InnomightLabs\AiConnector\Availability;

use WordPress\AiClient\Providers\Contracts\ProviderAvailabilityInterface;
use WordPress\AiClient\Providers\Http\Contracts\RequestAuthenticationInterface;
use WordPress\AiClient\Providers\Http\Contracts\WithRequestAuthenticationInterface;
use WordPress\AiClient\Providers\Http\DTO\ApiKeyRequestAuthentication;
use WordPress\AiClient\Providers\Http\Traits\WithRequestAuthenticationTrait;

/**
 * Checks whether the Innomight Labs widget API key is configured.
 */
final class InnomightProviderAvailability implements ProviderAvailabilityInterface, WithRequestAuthenticationInterface {
	use WithRequestAuthenticationTrait;

	/**
	 * Check if provider is configured.
	 *
	 * The WordPress AI plugin calls this during feature support checks before it
	 * invokes the model. Keep it local and deterministic; the admin connection
	 * test and generation requests still validate the key against the backend.
	 *
	 * @return bool True when a widget API key is available.
	 */
	public function isConfigured(): bool {
		try {
			$api_key = $this->api_key_from_authentication( $this->getRequestAuthentication() );
		} catch ( \Throwable $e ) {
			$api_key = \innomight_ai_get_api_key();
		}

		return is_string( $api_key ) && '' !== trim( $api_key );
	}

	/**
	 * Extract an API key from SDK authentication.
	 *
	 * @param RequestAuthenticationInterface $authentication Authentication object.
	 * @return string|null API key.
	 */
	private function api_key_from_authentication( RequestAuthenticationInterface $authentication ): ?string {
		if ( $authentication instanceof ApiKeyRequestAuthentication ) {
			return $authentication->getApiKey();
		}

		if ( method_exists( $authentication, 'toArray' ) ) {
			$data = $authentication->toArray();
			if ( is_array( $data ) && isset( $data['apiKey'] ) && is_string( $data['apiKey'] ) ) {
				return $data['apiKey'];
			}
		}

		return null;
	}
}
