"""Planning against the Meta networks' rules: Threads counts emoji as bytes, Instagram needs an image and caps hashtags
and @mentions. `check` and `publish` share this, so the agent hears the same reason the post would be skipped for."""

from __future__ import annotations

import pytest

from src.config import settings
from src.config.settings import SocialAppCredentials
from src.connectors.social.models import SocialAccount
from src.connectors.social.planning import plan_targets


@pytest.fixture(autouse=True)
def meta_apps(monkeypatch):
    monkeypatch.setattr(settings, "social_apps", {"threads": SocialAppCredentials("t", "s"),
                                                  "facebook_pages": SocialAppCredentials("f", "s")})


def account(network: str) -> SocialAccount:
    return SocialAccount(account_id="acct-1", network=network, external_id="1", handle="@acme", display_name="Acme",
                         encrypted_credentials="sealed", connected_by="user-1")


def plan(network: str, text: str, images: int = 1):
    [target] = plan_targets([account(network)], text, image_count=images)
    return target.reason, target.detail


def test_threads_counts_emoji_as_their_bytes_against_its_500():
    assert plan("threads", "x" * 497 + "🚀", images=0) == ("text_too_long", "501/500 characters")
    assert plan("threads", "é" * 500, images=0) == (None, ""), "accented letters count as one"


def test_instagram_needs_an_image():
    assert plan("instagram", "Hello", images=0) == ("image_required", "Instagram needs an image")
    assert plan("instagram", "Hello") == (None, "")


def test_instagram_caps_hashtags_and_mentions():
    assert plan("instagram", " ".join(f"#tag{n}" for n in range(31))) == ("too_many_hashtags", "31/30 hashtags")
    assert plan("instagram", " ".join(f"@user{n}" for n in range(21))) == ("too_many_mentions", "21/20 @mentions")
    assert plan("instagram", "Mail hello@acme.com about C# and &#39; " + "#ok " * 30) == (None, ""), \
        "an email address, C# and an HTML entity are not hashtags or mentions"


def test_networks_without_those_caps_ignore_them():
    assert plan("facebook_page", " ".join(f"#tag{n}" for n in range(40))) == (None, "")
