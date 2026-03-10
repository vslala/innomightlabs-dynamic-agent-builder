from src.config.settings import Settings


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
