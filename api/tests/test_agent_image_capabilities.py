from src.agents.image_generation.capabilities import (
    ImageCapability,
    ImageCapabilityRegistry,
    ImageProviderCapability,
    image_capability_registry,
)


def test_a_provider_with_image_generation_supports_every_model_it_offers():
    registry = ImageCapabilityRegistry(
        [ImageProviderCapability(provider="OpenAI", capabilities=frozenset({ImageCapability.GENERATION}))]
    )

    for model in ("gpt-5.4", "gpt-6-astra", "a-model-released-next-year"):
        assert registry.supports("OpenAI", model, ImageCapability.GENERATION)
        assert registry.capabilities_for("OpenAI", model) == ["image_generation"]


def test_a_provider_without_image_generation_supports_none():
    registry = ImageCapabilityRegistry([])

    assert not registry.supports("Anthropic", "claude-opus", ImageCapability.GENERATION)
    assert not registry.supports("OpenAI", None, ImageCapability.GENERATION)


def test_openai_can_generate_images_whatever_the_model_is():
    assert image_capability_registry.supports("OpenAI", "gpt-6-astra", ImageCapability.GENERATION)
