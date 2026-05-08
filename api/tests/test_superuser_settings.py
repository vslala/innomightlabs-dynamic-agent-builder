from src.config.settings import DEFAULT_OPENAI_MODELS, Settings


def test_superuser_emails_parses_csv_and_normalizes(monkeypatch):
    monkeypatch.setenv("SUPERUSER_EMAILS", " VarunShrivastava007@gmail.com, Admin@Example.com ")
    parsed = Settings.from_env()
    assert parsed.superuser_emails == ["varunshrivastava007@gmail.com", "admin@example.com"]
    assert parsed.is_superuser_email("VARUNSHRIVASTAVA007@GMAIL.COM")


def test_superuser_emails_parses_json_list(monkeypatch):
    monkeypatch.setenv("SUPERUSER_EMAILS", '["A@X.COM", "b@y.com", "a@x.com"]')
    parsed = Settings.from_env()
    assert parsed.superuser_emails == ["a@x.com", "b@y.com"]


def test_superuser_emails_default_empty(monkeypatch):
    monkeypatch.delenv("SUPERUSER_EMAILS", raising=False)
    parsed = Settings.from_env()
    assert parsed.superuser_emails == []
    assert not parsed.is_superuser_email("user@example.com")


def test_openai_models_default_to_latest_supported_models(monkeypatch):
    monkeypatch.delenv("OPENAI_MODELS", raising=False)
    parsed = Settings.from_env()

    assert parsed.openai_models[:4] == ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano"]
    assert parsed.openai_models == DEFAULT_OPENAI_MODELS


def test_openai_models_can_be_overridden_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_MODELS", "gpt-5.5, gpt-5.4-mini")
    parsed = Settings.from_env()

    assert parsed.openai_models == ["gpt-5.5", "gpt-5.4-mini"]
