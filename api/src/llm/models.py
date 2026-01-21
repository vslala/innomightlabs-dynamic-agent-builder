"""
LLM Models service - fetches available models from providers.
"""

import json
import logging
from typing import Optional
from functools import lru_cache

import boto3
from pydantic import BaseModel

from src.crypto import decrypt
from src.settings.models import ProviderSettings

log = logging.getLogger(__name__)


class ModelInfo(BaseModel):
    """Information about an available model."""
    model_id: str           # Internal ID used by the provider (e.g., "us.anthropic.claude-sonnet-4-20250514-v1:0")
    model_name: str         # Short name for selection (e.g., "claude-sonnet-4")
    display_name: str       # Human-readable name (e.g., "Claude Sonnet 4")
    provider: str           # Provider name (e.g., "bedrock")


class ModelsService:
    """Service for fetching available models from LLM providers."""

    # Bedrock region
    REGION = "eu-west-2"

    # Model name mappings for cleaner display
    MODEL_DISPLAY_NAMES = {
        # Newer models (may not be available in all regions)
        "claude-sonnet-4": "Claude Sonnet 4 (Latest)",
        "claude-opus-4": "Claude Opus 4",
        "claude-3-5-haiku": "Claude 3.5 Haiku (Fast)",
        "claude-3-5-sonnet": "Claude 3.5 Sonnet v2",
        # Models available in eu-west-2
        "claude-3-7-sonnet": "Claude 3.7 Sonnet",
        "claude-3-sonnet": "Claude 3 Sonnet",
        "claude-3-haiku": "Claude 3 Haiku (Fast)",
        "claude-3-opus": "Claude 3 Opus",
    }

    def get_bedrock_models(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
    ) -> list[ModelInfo]:
        """
        Fetch available Claude models from Bedrock.

        Args:
            access_key: AWS access key (optional, uses default credentials if not provided)
            secret_key: AWS secret key (optional)

        Returns:
            List of available model information
        """
        try:
            # Create Bedrock client (not bedrock-runtime)
            client_kwargs = {
                "service_name": "bedrock",
                "region_name": self.REGION,
            }
            if access_key and secret_key:
                client_kwargs["aws_access_key_id"] = access_key
                client_kwargs["aws_secret_access_key"] = secret_key

            client = boto3.client(**client_kwargs)  # type: ignore[call-overload]

            # List foundation models, filtering for Anthropic
            response = client.list_foundation_models(
                byProvider="Anthropic",
                byInferenceType="ON_DEMAND",
            )

            models = []
            seen_names = set()  # Avoid duplicates

            for model in response.get("modelSummaries", []):
                model_id = model.get("modelId", "")
                model_name = model.get("modelName", "")

                # Skip if not a Claude model or if we've seen this base model
                if "claude" not in model_id.lower():
                    continue

                # Extract a clean model name from the ID
                # e.g., "us.anthropic.claude-sonnet-4-20250514-v1:0" -> "claude-sonnet-4"
                clean_name = self._extract_model_name(model_id)
                if not clean_name or clean_name in seen_names:
                    continue

                seen_names.add(clean_name)

                # Get display name
                display_name = self.MODEL_DISPLAY_NAMES.get(
                    clean_name,
                    model_name or clean_name.replace("-", " ").title()
                )

                models.append(ModelInfo(
                    model_id=model_id,
                    model_name=clean_name,
                    display_name=f"[Bedrock] {display_name}",
                    provider="bedrock",
                ))

            # Sort by preference (best available in eu-west-2 first)
            preference_order = [
                "claude-3-7-sonnet",
                "claude-sonnet-4",
                "claude-opus-4",
                "claude-3-5-sonnet",
                "claude-3-5-haiku",
                "claude-3-sonnet",
                "claude-3-haiku",
                "claude-3-opus",
            ]

            def sort_key(m: ModelInfo) -> int:
                try:
                    return preference_order.index(m.model_name)
                except ValueError:
                    return len(preference_order)

            models.sort(key=sort_key)

            log.info(f"Fetched {len(models)} Bedrock Claude models")
            return models

        except Exception as e:
            log.error(f"Error fetching Bedrock models: {e}", exc_info=True)
            # Return fallback list if API fails
            return self._get_fallback_models()

    def _extract_model_name(self, model_id: str) -> Optional[str]:
        """
        Extract clean model name from Bedrock model ID.

        Examples:
            "us.anthropic.claude-sonnet-4-20250514-v1:0" -> "claude-sonnet-4"
            "anthropic.claude-3-5-haiku-20241022-v1:0" -> "claude-3-5-haiku"
        """
        # Remove provider prefix
        if "anthropic." in model_id:
            model_id = model_id.split("anthropic.")[-1]

        # Known model patterns to extract
        patterns = [
            "claude-sonnet-4",
            "claude-opus-4",
            "claude-3-5-haiku",
            "claude-3-5-sonnet",
            "claude-3-7-sonnet",
            "claude-3-sonnet",
            "claude-3-haiku",
            "claude-3-opus",
        ]

        for pattern in patterns:
            if pattern in model_id:
                return pattern

        return None

    def _get_fallback_models(self) -> list[ModelInfo]:
        """Return fallback model list when API is unavailable."""
        # Fallback to models available in eu-west-2
        return [
            ModelInfo(
                model_id="anthropic.claude-3-7-sonnet-20250219-v1:0",
                model_name="claude-3-7-sonnet",
                display_name="Claude 3.7 Sonnet",
                provider="bedrock",
            ),
            ModelInfo(
                model_id="anthropic.claude-3-sonnet-20230229-v1:0",
                model_name="claude-3-sonnet",
                display_name="Claude 3 Sonnet",
                provider="bedrock",
            ),
            ModelInfo(
                model_id="anthropic.claude-3-haiku-20240307-v1:0",
                model_name="claude-3-haiku",
                display_name="Claude 3 Haiku (Fast)",
                provider="bedrock",
            ),
        ]

    def get_anthropic_models(self, provider_settings: ProviderSettings) -> list[ModelInfo]:
        from anthropic import Anthropic
        
        credentials = json.loads(decrypt(provider_settings.encrypted_credentials))
        client = Anthropic(api_key=credentials["api_key"])
        models = client.models.list()
        
        return [
            ModelInfo(
                model_id=m.id,
                model_name=m.id,
                display_name=f"[Anthropic] {m.display_name}",
                provider="anthropic"
            )
            for m in models
        ]

# Singleton instance
models_service = ModelsService()
