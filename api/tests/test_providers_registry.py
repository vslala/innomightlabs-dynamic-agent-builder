"""The LLM providers: one definition each, found by name, and named nowhere else."""

import ast
import json
from pathlib import Path

import pytest

from src.crypto import encrypt
from src.llm.models import ModelCapability
from src.llm.providers import PROVIDERS, find_provider, provider
from src.settings.models import ProviderSettings

SRC = Path(__file__).resolve().parents[1] / "src"
PROVIDER_PACKAGES = SRC / "llm" / "providers"


def test_names_and_titles_are_unique():
    assert len({p.name for p in PROVIDERS}) == len(PROVIDERS)
    assert len({p.title for p in PROVIDERS}) == len(PROVIDERS)


def test_each_settings_form_saves_to_its_own_provider_unless_it_is_signed_into():
    for each in PROVIDERS:
        expected = each.settings_form.submit_path if each.oauth else f"/settings/providers/{each.name}"
        assert each.settings_form.submit_path == expected, each.name


def test_a_provider_is_found_by_name_whatever_its_case():
    assert find_provider("openaiapi") is find_provider("OpenAIAPI") is provider("OpenAIAPI")
    assert find_provider("Nope") is None


def test_an_unknown_provider_is_refused_with_the_ones_there_are():
    with pytest.raises(ValueError, match="Supported: Bedrock, Anthropic"):
        provider("Nope")


def test_no_code_outside_the_provider_packages_names_a_provider():
    """A provider-specific need becomes a `Provider` field (as `oauth` and `apply_thinking` did), not an `if`."""
    names = {p.name for p in PROVIDERS}
    found = [
        f"{path.relative_to(SRC.parent)}:{node.lineno} {node.value!r}"
        for path in sorted(SRC.rglob("*.py"))
        if PROVIDER_PACKAGES not in path.parents
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Constant) and node.value in names
    ]
    assert found == []


def test_the_settings_page_is_told_each_providers_title_and_how_it_connects(test_client, auth_headers, dynamodb_table):
    listed = {p["provider_name"]: p for p in test_client.get("/settings/providers", headers=auth_headers).json()}

    assert list(listed) == [p.name for p in PROVIDERS]
    assert listed["OpenAIAPI"]["title"] == "OpenAI (API key)" and listed["OpenAIAPI"]["oauth"] is None
    assert listed["OpenAI"]["oauth"]["start_path"] == "/auth/openai/start"
    assert listed["OpenAI"]["form"]["submit_path"] == "/auth/openai/complete"


def _listed_without_a_vendor(name: str):
    """The provider's catalog when its vendor can't be reached (credentials no vendor accepts, no network): its
    fallback list."""
    broken = ProviderSettings(
        account_id="acct", provider_name=name, encrypted_credentials=encrypt(json.dumps({"api_key": "x"}))
    )
    try:
        return provider(name).catalog.list_models(broken)
    except Exception:
        return []  # A catalog with no fallback raises; form_options shows the provider as unlisted.


@pytest.mark.parametrize("each", PROVIDERS, ids=lambda p: p.name)
def test_only_a_provider_that_draws_offers_models_that_draw(each, monkeypatch):
    def unreachable(*args, **kwargs):
        raise ConnectionError("no network in tests")

    for client in ("httpx.get", "httpx.post", "boto3.client", "anthropic.Anthropic", "google.genai.Client"):
        monkeypatch.setattr(client, unreachable)

    draws = [m.model_name for m in _listed_without_a_vendor(each.name) if m.can(ModelCapability.IMAGE_GENERATION)]

    if each.images is None:
        assert draws == []
    else:
        assert draws, f"{each.name} draws, so its fallback models should offer drawing"
