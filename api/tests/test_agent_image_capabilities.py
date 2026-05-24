from src.agents.image_generation.capabilities import (
    ImageCapability,
    ImageCapabilityRegistry,
    ImageModelCapability,
)


def test_registry_reports_generation_support_for_configured_model():
    registry = ImageCapabilityRegistry(
        [
            ImageModelCapability(
                provider="OpenAI",
                model_id="gpt-5.4",
                capabilities=frozenset({ImageCapability.GENERATION}),
            )
        ]
    )

    assert registry.supports("OpenAI", "gpt-5.4", ImageCapability.GENERATION)
    assert registry.capabilities_for("OpenAI", "gpt-5.4") == ["image_generation"]


def test_registry_returns_false_for_unsupported_or_missing_model():
    registry = ImageCapabilityRegistry([])

    assert not registry.supports("OpenAI", "gpt-5.4", ImageCapability.GENERATION)
    assert not registry.supports("OpenAI", None, ImageCapability.GENERATION)
