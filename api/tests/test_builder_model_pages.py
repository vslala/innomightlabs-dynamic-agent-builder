"""The `account/models` page: the providers set up in Settings are named in Ila's index every turn (a settings read
only), and their models are asked of the providers only when she opens the page."""

import pytest

from src.agents.architectures.vishwakarma_prompt import build_vishwakarma_system_prompt
from src.agents.service import validate_provider_model
from src.blueprints.account_pages import MODELS_PAGE
from src.blueprints.book import blueprint_book
from src.builder.models import BuilderSession
from src.llm.models import ModelInfo, ProviderModelSource
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL, account_for
from tests.mock_data import test_owner as _test_owner

TEST_OWNER = _test_owner()


class Listing:
    """Fake provider catalogs that count how often each provider is asked for its models."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.failing: set[str] = set()
        self.models = {
            "Bedrock": [
                ModelInfo(model_id="b1", model_name="claude-sonnet", display_name="Claude Sonnet", provider="bedrock",
                          capabilities=["image_understanding"]),
                ModelInfo(model_id="b2", model_name="nova-micro", display_name="Nova Micro", provider="bedrock"),
            ],
            "Anthropic": [ModelInfo(model_id="a1", model_name="claude-haiku", display_name="Claude Haiku", provider="anthropic")],
            "OpenAI": [ModelInfo(model_id="o1", model_name="gpt-5.5", display_name="GPT-5.5", provider="openai")],
        }

    def source(self, provider: str) -> ProviderModelSource:
        def load(_settings: ProviderSettings) -> list[ModelInfo]:
            self.calls.append(provider)
            if provider in self.failing:
                raise RuntimeError("provider is down")
            return self.models[provider]

        return ProviderModelSource(provider, load)


@pytest.fixture
def listing(dynamodb_table, monkeypatch) -> Listing:
    fake = Listing()
    monkeypatch.setattr("src.llm.models.PROVIDER_MODEL_SOURCES", tuple(fake.source(name) for name in fake.models))
    return fake


def set_up(*providers: str) -> None:
    for provider in providers:
        ProviderSettingsRepository().save(ProviderSettings(
            account_id=account_for(TEST_USER_EMAIL), provider_name=provider, encrypted_credentials="{}",
        ))


def index_line(book) -> str:
    [line] = [page for chapter in book.chapters for page in chapter.pages if page.id == MODELS_PAGE]
    return line.summary


def test_the_index_names_only_the_providers_set_up_and_lists_no_models(listing):
    set_up("Bedrock", "OpenAI")
    book = blueprint_book(owner=TEST_OWNER)
    session = BuilderSession(conversation_id="c1", account_id=TEST_OWNER.account_id, user_id=TEST_OWNER.user_id,
                             provider="Bedrock", model="claude-sonnet")

    prompt = build_vishwakarma_system_prompt(book=book, session=session, retention=3)

    assert index_line(book) == "Providers set up in Settings: Bedrock, OpenAI. Open it for the models each one offers."
    assert "Providers set up in Settings: Bedrock, OpenAI" in prompt
    assert "`account/models`" in prompt
    assert listing.calls == []


def test_opening_the_page_lists_each_providers_models_once(listing):
    set_up("Bedrock", "OpenAI")
    book = blueprint_book(owner=TEST_OWNER)

    page = book.get(MODELS_PAGE)
    book.get(MODELS_PAGE)

    assert page is not None and page.summary == "3 models from 2 providers."
    assert "## Bedrock\n- `claude-sonnet`: Claude Sonnet (reads images)\n- `nova-micro`: Nova Micro" in page.body
    assert "## OpenAI\n- `gpt-5.5`: GPT-5.5" in page.body
    assert "Anthropic" not in page.body
    assert listing.calls == ["Bedrock", "OpenAI"]


def test_every_model_on_the_page_is_one_the_plan_accepts(listing):
    set_up("Bedrock", "Anthropic")
    page = blueprint_book(owner=TEST_OWNER).get(MODELS_PAGE)
    assert page is not None

    for provider, models in (("Bedrock", ["claude-sonnet", "nova-micro"]), ("Anthropic", ["claude-haiku"])):
        for model in models:
            assert f"`{model}`" in page.body
            validate_provider_model(TEST_OWNER, provider, model)
    with pytest.raises(ValueError):
        validate_provider_model(TEST_OWNER, "Anthropic", "nova-micro")


def test_a_provider_that_cant_list_its_models_now_says_so(listing):
    set_up("Bedrock", "Anthropic")
    listing.failing.add("Anthropic")

    page = blueprint_book(owner=TEST_OWNER).get(MODELS_PAGE)

    assert page is not None
    assert "## Anthropic\nIts models couldn't be listed just now." in page.body
    assert "`claude-sonnet`" in page.body


def test_with_no_provider_set_up_the_index_says_nothing_can_be_built(listing, without_bedrock):
    book = blueprint_book(owner=TEST_OWNER)

    assert index_line(book) == "No provider is set up in Settings yet, so no agent can be built."
    page = book.get(MODELS_PAGE)
    assert page is not None and "Settings > Provider Configuration" in page.body
