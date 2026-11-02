"""Threads: one sign-in is one profile on its own Meta app and hosts, a 60-day token renewed while posting, and posts
as containers."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from src.config import settings
from src.config.settings import SocialAppCredentials
from src.connectors.social import networks
from src.connectors.social.networks import meta
from src.connectors.social.networks.base import PreparedImage, PreparedPost, PublishError, PublishErrorKind
from src.connectors.social.networks.threads import ThreadsNetwork, threads_length
from src.connectors.social.publisher import PublishRequest, SocialPublisher
from src.connectors.social.repository import SocialAccountRepository
from src.crypto import encrypt
from tests.mock_data import TEST_USER_EMAIL, account_for
from tests.oauth_handoff import handoff_result, owner_headers

RETURN_TO = "http://localhost:5173/dashboard/connectors?tab=social"
REDIRECT = "http://localhost:8000/connectors/social/oauth/callback"


def credentials(issued_ago: timedelta = timedelta(days=1), expires_in: timedelta = timedelta(days=59)) -> dict:
    now = datetime.now(timezone.utc)
    return {"access_token": "long-token", "user_id": "th-1", "issued_at": (now - issued_ago).isoformat(),
            "expires_at": (now + expires_in).isoformat()}


def image(index: int = 0, alt_text: str = "") -> PreparedImage:
    return PreparedImage(data=b"\xff\xd8jpeg", mime_type="image/jpeg", alt_text=alt_text,
                         url=f"https://api.example/connectors/social/media/token-{index}.jpg")


class FakeThreads:
    """graph.threads.com: the code exchange, the long-lived exchange and refresh, /me, containers, their status,
    threads_publish, a post's permalink and the profile's threads."""

    def __init__(self) -> None:
        self.statuses = ["IN_PROGRESS", "FINISHED"]
        self.failures: dict[str, httpx.Response] = {}
        self.requests: list[httpx.Request] = []
        self.containers = 0
        self._polls: dict[str, int] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path in self.failures:
            return self.failures[path]
        if path == "/oauth/access_token":
            return httpx.Response(200, json={"access_token": "short-token", "user_id": "th-1"})
        if path == "/access_token":
            return httpx.Response(200, json={"access_token": "long-token", "token_type": "bearer", "expires_in": 5184000})
        if path == "/refresh_access_token":
            return httpx.Response(200, json={"access_token": "renewed-token", "token_type": "bearer", "expires_in": 5184000})
        if path == "/v1.0/me":
            return httpx.Response(200, json={"id": "th-1", "username": "acme", "name": "Acme",
                                             "threads_profile_picture_url": "https://cdn.example/acme-th.jpg"})
        if path == "/v1.0/th-1/threads":
            self.containers += 1
            return httpx.Response(200, json={"id": f"container-{self.containers}"})
        if path.startswith("/v1.0/container-"):
            polls = self._polls[path] = self._polls.get(path, -1) + 1
            return httpx.Response(200, json={"status": self.statuses[min(polls, len(self.statuses) - 1)],
                                             "error_message": "FAILED_DOWNLOADING_IMAGE"})
        if path == "/v1.0/th-1/threads_publish":
            return httpx.Response(200, json={"id": "post-9"})
        if path == "/v1.0/post-9":
            return httpx.Response(200, json={"permalink": "https://www.threads.com/@acme/post/abc"})
        if path == "/v1.0/me/threads":
            return httpx.Response(200, json={"data": [
                {"id": "p2", "text": "Second", "timestamp": "2026-11-02T09:30:00+0000",
                 "permalink": "https://www.threads.com/@acme/post/p2", "media_type": "CAROUSEL_ALBUM"},
                {"id": "p1", "text": "First", "timestamp": "2026-11-01T08:00:00+0000", "media_type": "TEXT_POST"},
            ]})
        return httpx.Response(404, json={"error": {"message": "Unknown path", "code": 803}})

    def calls(self, suffix: str, method: str | None = None) -> list[httpx.Request]:
        return [request for request in self.requests
                if request.url.path.endswith(suffix) and (method is None or request.method == method)]


@pytest.fixture
def threads(monkeypatch) -> FakeThreads:
    fake = FakeThreads()
    monkeypatch.setattr(networks, "NETWORKS", (ThreadsNetwork(transport=httpx.MockTransport(fake)),))
    monkeypatch.setattr(settings, "social_apps", {"threads": SocialAppCredentials("threads-app", "threads-secret")})
    monkeypatch.setattr(settings, "social_oauth_redirect_uri", REDIRECT)
    monkeypatch.setattr(meta, "POLL_SECONDS", 0)
    return fake


def network(fake: FakeThreads) -> ThreadsNetwork:
    return ThreadsNetwork(transport=httpx.MockTransport(fake))


def start(test_client) -> str:
    response = test_client.post("/connectors/social/networks/threads/connect", json={"return_to": RETURN_TO},
                                headers=owner_headers())
    assert response.status_code == 200, response.text
    return response.json()["authorize_url"]


def connect(test_client) -> dict[str, list[str]]:
    state = parse_qs(urlparse(start(test_client)).query)["state"][0]
    callback = test_client.get("/connectors/social/oauth/callback", params={"code": "auth-code", "state": state},
                               follow_redirects=False)
    return handoff_result(test_client, callback, TEST_USER_EMAIL)


def form(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.content.decode())


def test_the_dialog_is_threads_own_with_the_publishing_scopes(test_client, threads):
    url = urlparse(start(test_client))
    query = parse_qs(url.query)

    assert (url.netloc, url.path) == ("threads.com", "/oauth/authorize")
    assert query["client_id"] == ["threads-app"] and query["scope"] == ["threads_basic,threads_content_publish"]
    assert "code_challenge" not in query


def test_connecting_saves_the_profile_with_a_long_lived_token(test_client, threads):
    assert connect(test_client)["social_oauth"] == ["success"]

    [saved] = SocialAccountRepository().list(account_for(TEST_USER_EMAIL))
    assert (saved.external_id, saved.handle, saved.display_name, saved.grant_id) == ("th-1", "@acme", "Acme", "th-1")
    assert saved.avatar_url == "https://cdn.example/acme-th.jpg"
    stored = saved.credentials()
    assert stored["access_token"] == "long-token" and stored["user_id"] == "th-1"
    assert saved.token_expires_at and timedelta(days=59) < saved.token_expires_at - datetime.now(timezone.utc) <= timedelta(days=60)

    [code] = threads.calls("/oauth/access_token")
    assert form(code)["grant_type"] == ["authorization_code"] and form(code)["redirect_uri"] == [REDIRECT]
    [long] = threads.calls("/access_token", "GET")
    assert long.url.params["grant_type"] == "th_exchange_token" and long.url.params["access_token"] == "short-token"
    assert threads.calls("/v1.0/me")[0].headers["Authorization"] == "Bearer long-token"


def test_a_code_threads_rejects_saves_nothing(test_client, threads):
    threads.failures["/oauth/access_token"] = httpx.Response(400, json={"error": {"message": "Invalid code"}})
    assert connect(test_client)["reason"] == ["callback_failed"]
    assert SocialAccountRepository().list(account_for(TEST_USER_EMAIL)) == []


@pytest.mark.asyncio
async def test_a_text_post_is_a_container_waited_for_then_published(threads):
    published = await network(threads).publish(credentials(), PreparedPost(text="Hello Threads"))

    [create] = threads.calls("/th-1/threads")
    assert form(create) == {"media_type": ["TEXT"], "text": ["Hello Threads"]}
    assert create.headers["Authorization"] == "Bearer long-token"
    assert [request.url.params["fields"] for request in threads.calls("/container-1")] == ["status,error_message"] * 2
    assert form(threads.calls("/threads_publish")[0]) == {"creation_id": ["container-1"]}
    assert published.external_id == "post-9" and published.url == "https://www.threads.com/@acme/post/abc"


@pytest.mark.asyncio
async def test_one_image_carries_its_url_and_alt_text(threads):
    await network(threads).publish(credentials(), PreparedPost(text="Look", images=(image(alt_text="A red bike"),)))

    [create] = threads.calls("/th-1/threads")
    assert form(create) == {"media_type": ["IMAGE"], "image_url": ["https://api.example/connectors/social/media/token-0.jpg"],
                            "alt_text": ["A red bike"], "text": ["Look"]}


@pytest.mark.asyncio
async def test_several_images_are_a_carousel_with_the_text_on_the_parent(threads):
    await network(threads).publish(credentials(), PreparedPost(text="Album", images=(image(0), image(1))))

    first, second, parent = (form(request) for request in threads.calls("/th-1/threads"))
    assert first["is_carousel_item"] == ["true"] and "text" not in first
    assert second["image_url"] == ["https://api.example/connectors/social/media/token-1.jpg"]
    assert parent == {"media_type": ["CAROUSEL"], "children": ["container-1,container-2"], "text": ["Album"]}
    assert form(threads.calls("/threads_publish")[0]) == {"creation_id": ["container-3"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(("statuses", "kind"), [
    (["ERROR"], PublishErrorKind.REJECTED),
    (["EXPIRED"], PublishErrorKind.TRANSIENT),
], ids=["refused media", "lapsed"])
async def test_a_container_that_does_not_finish_is_never_published(threads, statuses, kind):
    threads.statuses = statuses
    with pytest.raises(PublishError) as raised:
        await network(threads).publish(credentials(), PreparedPost(text="Hi"))

    assert raised.value.kind == kind
    assert threads.calls("/threads_publish") == []
    if kind == PublishErrorKind.REJECTED:
        assert str(raised.value) == "Threads could not use the post's media: FAILED_DOWNLOADING_IMAGE"


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "response", "kind"), [
    ("/v1.0/th-1/threads", httpx.Response(400, json={"error": {"code": 190, "message": "Session expired"}}), PublishErrorKind.AUTH),
    ("/v1.0/th-1/threads", httpx.Response(500, json={"error": {"code": 2}}), PublishErrorKind.TRANSIENT),
    ("/v1.0/th-1/threads_publish", httpx.Response(500, json={"error": {"code": 2}}), PublishErrorKind.UNCERTAIN),
    ("/v1.0/th-1/threads_publish", httpx.Response(400, json={"error": {"code": 4, "message": "Limit"}}), PublishErrorKind.RATE_LIMITED),
], ids=["expired token", "container create failed", "publish failed", "daily cap"])
async def test_failures_are_classified_so_only_safe_retries_happen(threads, path, response, kind):
    threads.failures[path] = response
    with pytest.raises(PublishError) as raised:
        await network(threads).publish(credentials(), PreparedPost(text="Hi"))
    assert raised.value.kind == kind
    assert "long-token" not in str(raised.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(("issued_ago", "expires_in", "renews"), [
    (timedelta(hours=2), timedelta(days=20), False),
    (timedelta(days=2), timedelta(days=50), False),
    (timedelta(days=35), timedelta(days=25), True),
    (timedelta(days=61), timedelta(days=-1), False),
], ids=["under a day old", "plenty left", "due", "already lapsed"])
async def test_the_token_is_renewed_once_a_day_old_with_under_30_days_left(threads, issued_ago, expires_in, renews):
    refreshed = await network(threads).fresh_credentials(credentials(issued_ago, expires_in))

    assert (refreshed is not None) == renews
    if refreshed:
        assert refreshed.credentials["access_token"] == "renewed-token" and refreshed.credentials["user_id"] == "th-1"
        assert refreshed.expires_at and refreshed.expires_at - datetime.now(timezone.utc) > timedelta(days=59)
        [renewal] = threads.calls("/refresh_access_token")
        assert renewal.url.params["grant_type"] == "th_refresh_token"


@pytest.mark.asyncio
async def test_a_refused_renewal_needs_a_reconnect_and_a_failed_one_keeps_the_token(threads):
    threads.failures["/refresh_access_token"] = httpx.Response(400, json={"error": {"code": 190}})
    with pytest.raises(PublishError) as raised:
        await network(threads).fresh_credentials(credentials(timedelta(days=35), timedelta(days=25)))
    assert raised.value.kind == PublishErrorKind.AUTH

    threads.failures["/refresh_access_token"] = httpx.Response(503)
    assert await network(threads).fresh_credentials(credentials(timedelta(days=35), timedelta(days=25))) is None


@pytest.mark.asyncio
async def test_recent_posts_reads_the_profiles_own_threads(threads):
    posts = await network(threads).recent_posts(credentials(), limit=3)

    assert [(post.external_id, post.text, post.media) for post in posts] == [("p2", "Second", "carousel"), ("p1", "First", "text")]
    assert posts[0].posted_at == datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)
    assert threads.calls("/me/threads")[0].url.params["limit"] == "3"


def test_threads_counts_an_emoji_as_its_bytes_but_an_accented_letter_as_one():
    assert threads_length("hello") == 5
    assert threads_length("café") == 4
    assert threads_length("🚀") == 4
    assert threads_length("❤️") == len("❤️".encode())
    assert threads_length("👩‍💻") == len("👩‍💻".encode())


def test_a_post_is_renewed_and_saved_before_it_is_published(test_client, threads, dynamodb_table):
    connect(test_client)
    repository = SocialAccountRepository()
    [account] = repository.list(account_for(TEST_USER_EMAIL))
    account = repository.update_credentials(account, encrypt(json.dumps(credentials(timedelta(days=35), timedelta(days=25)))),
                                            datetime.now(timezone.utc) + timedelta(days=25))

    result = asyncio.run(SocialPublisher().publish(PublishRequest(account_id=account.account_id, post_id="post-1", text="Hi")))

    assert result["status"] == "published"
    assert threads.calls("/th-1/threads")[0].headers["Authorization"] == "Bearer renewed-token"
    [saved] = repository.list(account.account_id)
    assert saved.credentials()["access_token"] == "renewed-token"
    assert saved.token_expires_at and saved.token_expires_at - datetime.now(timezone.utc) > timedelta(days=59)
    assert (saved.handle, saved.grant_id) == ("@acme", "th-1"), "renewal changes the credentials only"
