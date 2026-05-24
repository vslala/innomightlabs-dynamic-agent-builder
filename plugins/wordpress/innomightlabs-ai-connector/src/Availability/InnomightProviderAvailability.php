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
 * Checks whether the Innomight Labs widget API key is valid.
 */
final class InnomightProviderAvailability implements ProviderAvailabilityInterface, WithRequestAuthenticationInterface {
	use WithRequestAuthenticationTrait;

	/**
	 * Check if provider is configured.
	 *
	 * @return bool True when the key can access the backend.
	 */
	public function isConfigured(): bool {
		try {
			$api_key = $this->api_key_from_authentication( $this->getRequestAuthentication() );
		} catch ( \Throwable $e ) {
			$api_key = \innomight_ai_get_api_key();
		}

		if ( ! is_string( $api_key ) || '' === trim( $api_key ) ) {
			return false;
		}

		$response = wp_remote_get(
			\innomight_ai_get_api_base_url() . '/widget/config',
			array(
				'timeout' => 10,
				'headers' => array(
					'Accept'     => 'application/json',
					'Origin'     => home_url(),
					'User-Agent' => 'InnomightAIConnector/' . INNOMIGHT_AI_CONNECTOR_VERSION,
					'X-API-Key'  => trim( $api_key ),
				),
			)
		);

		if ( is_wp_error( $response ) ) {
			return false;
		}

		$status = wp_remote_retrieve_response_code( $response );
		return $status >= 200 && $status < 300;
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
