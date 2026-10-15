from typing import AsyncIterator, Optional

import anthropic
import httpx
import pytest
from google.genai import errors as genai_errors

from src.llm import model_fallback
from src.llm.model_fallback import ModelFallbackProvider, is_model_refusal, pick_substitute
from src.llm.models import ModelInfo, ProviderModelSource
from src.llm.providers.base import LLMEvent, LLMProvider
from src.settings.models import ProviderSettings

CODEX_REFUSAL = RuntimeError(
    "OpenAI OAuth responses error (400, request_id=None): "
    '{"detail":"The \'gpt-5.5\' model is not supported when using Codex with a ChatGPT account."}'
)


def _model(name: str, capabilities: tuple[str, ...] = ()) -> ModelInfo:
    return ModelInfo(model_id=name, model_name=name, display_name=name, provider="openai", capabilities=list(capabilities))


class ScriptedProvider(LLMProvider):
    """Raises (or streams then raises) for the models it was told to, and answers for the rest."""

    default_model = "gpt-5.5"

    def __init__(self, refuse: dict[Optional[str], Exception], stream_before_failing: bool = False):
        self.refuse = refuse
        self.stream_before_failing = stream_before_failing
        self.calls: list[Optional[str]] = []

    async def stream_response(
        self, messages: list[dict], credentials: dict, tools: Optional[list[dict]] = None, model: Optional[str] = None
    ) -> AsyncIterator[LLMEvent]:
        self.calls.append(model)
        if model in self.refuse:
            if self.stream_before_failing:
                yield LLMEvent(type="text", content="partial")
            raise self.refuse[model]
        yield LLMEvent(type="text", content=f"answer from {model}")
        yield LLMEvent(type="stop", content="end_turn")


@pytest.fixture(autouse=True)
def catalog(monkeypatch):
    model_fallback._substitutes.clear()
    loads: list[str] = []
    models = [_model("gpt-5.5"), _model("gpt-5.4-mini"), _model("gpt-5.4", ("image_understanding",))]

    def load(provider_settings: ProviderSettings) -> list[ModelInfo]:
        loads.append(provider_settings.account_id)
        return models

    monkeypatch.setattr(model_fallback, "find_model_source", lambda name: ProviderModelSource(name, load))
    return loads


def _fallback(inner: LLMProvider, **kwargs) -> ModelFallbackProvider:
    settings = ProviderSettings(account_id="acct-1", provider_name="OpenAI", encrypted_credentials="x")
    return ModelFallbackProvider(inner, "OpenAI", settings, **kwargs)


async def _texts(provider: LLMProvider, model: Optional[str]) -> list[str]:
    return [event.content async for event in provider.stream_response([], {}, None, model) if event.type == "text"]


async def test_the_stored_model_is_used_while_the_vendor_accepts_it(catalog):
    inner = ScriptedProvider(refuse={})

    assert await _texts(_fallback(inner), "gpt-5.4") == ["answer from gpt-5.4"]
    assert inner.calls == ["gpt-5.4"]
    assert catalog == []


async def test_a_refused_model_is_swapped_for_the_first_catalog_model_and_remembered(catalog):
    inner = ScriptedProvider(refuse={"gpt-5.5": CODEX_REFUSAL})
    provider = _fallback(inner)

    assert await _texts(provider, "gpt-5.5") == ["answer from gpt-5.4-mini"]
    assert await _texts(provider, "gpt-5.5") == ["answer from gpt-5.4-mini"]
    # The second call skips the doomed try and the catalog lookup.
    assert inner.calls == ["gpt-5.5", "gpt-5.4-mini", "gpt-5.4-mini"]
    assert catalog == ["acct-1"]


async def test_no_stored_model_means_the_refused_one_is_the_provider_default():
    inner = ScriptedProvider(refuse={None: CODEX_REFUSAL})

    assert await _texts(_fallback(inner), None) == ["answer from gpt-5.4-mini"]


async def test_a_substitute_must_have_the_required_capabilities():
    inner = ScriptedProvider(refuse={"gpt-5.5": CODEX_REFUSAL})

    assert await _texts(_fallback(inner, capabilities=["image_understanding"]), "gpt-5.5") == ["answer from gpt-5.4"]


async def test_other_failures_are_not_retried(catalog):
    inner = ScriptedProvider(refuse={"gpt-5.5": RuntimeError("OpenAI OAuth responses error (429, request_id=None): rate limited")})

    with pytest.raises(RuntimeError, match="429"):
        await _texts(_fallback(inner), "gpt-5.5")
    assert inner.calls == ["gpt-5.5"]
    assert catalog == []


async def test_a_refusal_after_streaming_started_is_not_retried():
    inner = ScriptedProvider(refuse={"gpt-5.5": CODEX_REFUSAL}, stream_before_failing=True)

    with pytest.raises(RuntimeError, match="not supported"):
        await _texts(_fallback(inner), "gpt-5.5")
    assert inner.calls == ["gpt-5.5"]


async def test_the_refusal_is_raised_when_the_catalog_has_no_substitute(monkeypatch):
    monkeypatch.setattr(model_fallback, "find_model_source", lambda name: ProviderModelSource(name, lambda s: [_model("gpt-5.5")]))
    inner = ScriptedProvider(refuse={"gpt-5.5": CODEX_REFUSAL})

    with pytest.raises(RuntimeError, match="not supported"):
        await _texts(_fallback(inner), "gpt-5.5")


@pytest.mark.parametrize(
    ("provider_name", "exc"),
    [
        ("OpenAI", CODEX_REFUSAL),
        ("OpenAIAPI", RuntimeError('OpenAI API responses error (404, request_id=r): {"error": {"code": "model_not_found"}}')),
        (
            "Anthropic",
            anthropic.NotFoundError(
                "model: claude-3-opus", response=httpx.Response(404, request=httpx.Request("POST", "https://api")), body=None
            ),
        ),
        ("Gemini", genai_errors.ClientError(404, {"error": {"message": "models/gemini-1.5-pro is not found"}})),
        ("Ollama", RuntimeError("Ollama endpoint at http://host does not have model 'llama3' (HTTP 404). Pull it")),
    ],
)
def test_each_vendors_model_refusal_is_recognised(provider_name, exc):
    assert is_model_refusal(provider_name, exc)


@pytest.mark.parametrize(
    ("provider_name", "exc"),
    [
        ("OpenAI", RuntimeError("OpenAI OAuth responses error (401, request_id=None): token expired")),
        ("Gemini", genai_errors.ClientError(400, {"error": {"message": "bad request"}})),
        ("Anthropic", CODEX_REFUSAL),
        ("Bedrock", RuntimeError("ValidationException: The provided model identifier is invalid.")),
    ],
)
def test_other_errors_are_not_refusals(provider_name, exc):
    assert not is_model_refusal(provider_name, exc)


def test_pick_substitute_skips_the_refused_model_by_name_or_id():
    catalog = [ModelInfo(model_id="vendor/x-1", model_name="x", display_name="X", provider="p"), _model("y")]

    assert pick_substitute(catalog, refused="vendor/x-1") == "y"
    assert pick_substitute(catalog, refused="x") == "y"
    assert pick_substitute([_model("x")], refused="x") is None
