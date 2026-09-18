import pytest

from src.dream.redaction import SECRET_PATTERNS, is_safe, redact


@pytest.mark.parametrize(
    ("name", "secret"),
    [
        ("aws_access_key", "AKIA1234567890ABCDEF"),
        ("private_key", "-----BEGIN RSA PRIVATE KEY-----"),
        ("bearer_token", "Bearer abcdefghijklmnopqrstuvwxyz"),
        ("github_token", "ghp_abcdefghijklmnopqrstuvwxyz1234567890"),
        ("openai_key", "sk-abcdefghijklmnopqrstuvwxyz123456"),
        ("slack_token", "xoxb-abcdefghijklmnopqrstuvwxyz"),
        ("jwt", "eyJabcdefghij.abcdefghij.abcdefghij"),
        ("assignment", "password=super-secret"),
    ],
)
def test_redacts_each_secret_pattern(name: str, secret: str):
    redacted, matches = redact(f"store {secret} please")

    assert matches == [name]
    assert secret not in redacted
    assert f"[REDACTED:{name}]" in redacted
    assert not is_safe(secret)


def test_safe_text_is_untouched():
    text = "The user prefers short, direct answers about Python."

    assert redact(text) == (text, [])
    assert is_safe(text)


def test_redacts_multiple_secret_types_in_declaration_order():
    text = "AKIA1234567890ABCDEF and password=hunter2"

    redacted, matches = redact(text)

    assert matches == ["aws_access_key", "assignment"]
    assert redacted == "[REDACTED:aws_access_key] and [REDACTED:assignment]"


def test_patterns_are_exposed_as_the_redaction_contract():
    assert {name for name, _ in SECRET_PATTERNS} == {
        "aws_access_key",
        "private_key",
        "bearer_token",
        "github_token",
        "openai_key",
        "slack_token",
        "jwt",
        "assignment",
    }
