"""The Claude models an account's AWS keys can use on Bedrock."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Optional

import boto3

from src.llm.models import ModelInfo, chat_capabilities
from src.llm.providers.provider import stored_credentials
from src.settings.models import ProviderSettings

log = logging.getLogger(__name__)

#: The project's Bedrock region; chat and listing use the same one.
BEDROCK_REGION = "eu-west-2"

#: Short names for the Claude families, in the order they are offered: the best available in eu-west-2 first. A model
#: id is named after the family it contains; no family's name contains another's.
CLAUDE_FAMILIES = (
    "claude-3-7-sonnet",
    "claude-sonnet-4",
    "claude-opus-4",
    "claude-3-5-sonnet",
    "claude-3-5-haiku",
    "claude-3-sonnet",
    "claude-3-haiku",
    "claude-3-opus",
)

DISPLAY_NAMES = {
    "claude-sonnet-4": "Claude Sonnet 4 (Latest)",
    "claude-opus-4": "Claude Opus 4",
    "claude-3-5-haiku": "Claude 3.5 Haiku (Fast)",
    "claude-3-5-sonnet": "Claude 3.5 Sonnet v2",
    "claude-3-7-sonnet": "Claude 3.7 Sonnet",
    "claude-3-sonnet": "Claude 3 Sonnet",
    "claude-3-haiku": "Claude 3 Haiku (Fast)",
    "claude-3-opus": "Claude 3 Opus",
}

#: Offered when the listing fails: models available in eu-west-2.
FALLBACK_MODELS = (
    ModelInfo(
        model_id="anthropic.claude-3-7-sonnet-20250219-v1:0",
        model_name="claude-3-7-sonnet",
        display_name="Claude 3.7 Sonnet",
        provider="bedrock",
        capabilities=chat_capabilities(reads_images=True),
    ),
    ModelInfo(
        model_id="anthropic.claude-3-sonnet-20230229-v1:0",
        model_name="claude-3-sonnet",
        display_name="Claude 3 Sonnet",
        provider="bedrock",
        capabilities=chat_capabilities(reads_images=True),
    ),
    ModelInfo(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        model_name="claude-3-haiku",
        display_name="Claude 3 Haiku (Fast)",
        provider="bedrock",
        capabilities=chat_capabilities(reads_images=True),
    ),
)


class BedrockCatalog:
    def list_models(self, provider_settings: ProviderSettings) -> list[ModelInfo]:
        credentials = stored_credentials(provider_settings)
        return self.list_models_with_keys(credentials["access_key"], credentials["secret_key"])

    def list_models_with_keys(self, access_key: str, secret_key: str) -> list[ModelInfo]:
        """Claude models on Bedrock for these AWS keys, best first, or the fallback list when listing fails.

        Always the account's own keys: the server's AWS identity is not a Bedrock account anyone configured.
        """
        try:
            client = boto3.client(
                service_name="bedrock",
                region_name=BEDROCK_REGION,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
            )
            response = client.list_foundation_models(byProvider="Anthropic", byInferenceType="ON_DEMAND")
        except Exception as e:
            log.error("Error fetching Bedrock models: %s", e, exc_info=True)
            return list(FALLBACK_MODELS)

        models: dict[str, ModelInfo] = {}
        for summary in response.get("modelSummaries", []):
            model_id = summary.get("modelId", "")
            family = claude_family(model_id)
            if not family or family in models:
                continue
            display_name = DISPLAY_NAMES.get(family, summary.get("modelName") or family.replace("-", " ").title())
            models[family] = ModelInfo(
                model_id=model_id,
                model_name=family,
                display_name=f"[Bedrock] {display_name}",
                provider="bedrock",
                capabilities=chat_capabilities(reads_images=reads_images(summary)),
            )

        log.info("Fetched %d Bedrock Claude models", len(models))
        return sorted(models.values(), key=lambda model: CLAUDE_FAMILIES.index(model.model_name))


def claude_family(model_id: str) -> Optional[str]:
    """The short name of a Bedrock Claude model id: "us.anthropic.claude-sonnet-4-20250514-v1:0" -> "claude-sonnet-4"."""
    name = model_id.split("anthropic.")[-1]
    if "claude" not in name.lower():
        return None
    return next((family for family in CLAUDE_FAMILIES if family in name), None)


def reads_images(summary: Mapping[str, Any]) -> bool:
    """`ListFoundationModels` names each model's `inputModalities` (TEXT, IMAGE, ...)."""
    return "IMAGE" in (summary.get("inputModalities") or [])
