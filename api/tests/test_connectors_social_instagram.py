"""Instagram: the Facebook sign-in connects every professional account linked to a shared Page, and a post is a
container Instagram fetches its images for, processes, then publishes."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from src.config import settings
from src.config.settings import SocialAppCredentials
from src.connectors.social import networks
from src.connectors.social.networks import meta
from src.connectors.social.networks.base import PreparedImage, PreparedPost, PublishError, PublishErrorKind
from src.connectors.social.networks.facebook_pages import FacebookPagesNetwork
from src.connectors.social.networks.instagram import InstagramNetwork
from src.connectors.social.repository import SocialAccountRepository
from tests.mock_data import TEST_USER_EMAIL, account_for
from tests.oauth_handoff import handoff_result, owner_headers

RETURN_TO = "http://localhost:5173/dashboard/connectors?tab=social"
REDIRECT = "http://localhost:8000/connectors/social/oauth/callback"
CREDENTIALS = {"page_access_token": "page-token-111", "instagram_id": "ig-1", "page_id": "111",
               "user_access_token": "user-token"}


def image(alt_text: str = "", index: int = 0) -> PreparedImage:
    return PreparedImage(data=b"\xff\xd8jpeg", mime_type="image/jpeg", alt_text=alt_text,
                         url=f"https://api.example/connectors/social/media/token-{index}.jpg")


class FakeGraph:
    """The Graph API endpoints Instagram uses through Facebook Login: tokens, /me, /me/accounts, permissions, media
    containers, their status, media_publish and the account's media."""

    def __init__(self) -> None:
        self.pages = [
            {"id": "111", "name": "Acme", "access_token": "page-token-111", "tasks": ["CREATE_CONTENT"],
             "instagram_business_account": {"id": "ig-1", "username": "acme", "name": "Acme Co",
                                            "profile_picture_url": "https://cdn.example/acme-ig.jpg"}},
            {"id": "222", "name": "Acme Labs", "access_token": "page-token-222", "tasks": ["CREATE_CONTENT"]},
        ]
        self.permissions = [("pages_show_list", "granted"), ("instagram_basic", "granted"),
                            ("instagram_content_publish", "granted")]
        #: Status answers per container, in order; the last repeats
        self.statuses: list[str] = ["IN_PROGRESS", "FINISHED"]
        self.failures: dict[str, httpx.Response] = {}
        self.requests: list[httpx.Request] = []
        self.containers = 0
        self._polls: dict[str, int] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/v26.0")
        if path in self.failures:
            return self.failures[path]
        if path == "/oauth/access_token":
            token = "user-token" if "fb_exchange_token" in request.url.params else "short-token"
            return httpx.Response(200, json={"access_token": token})
        if path == "/me":
            return httpx.Response(200, json={"id": "fb-user-1"})
        if path == "/me/accounts":
            return httpx.Response(200, json={"data": self.pages})
        if path == "/me/permissions":
            if request.method == "GET":
                return httpx.Response(200, json={"data": [{"permission": name, "status": status}
                                                          for name, status in self.permissions]})
            return httpx.Response(200, json={"success": True})
        if path == "/ig-1/media" and request.method == "POST":
            self.containers += 1
            return httpx.Response(200, json={"id": f"container-{self.containers}"})
        if path == "/ig-1/media":
            return httpx.Response(200, json={"data": [
                {"id": "m2", "caption": "Second", "timestamp": "2026-11-02T09:30:00+0000",
                 "permalink": "https://www.instagram.com/p/m2/", "media_type": "CAROUSEL_ALBUM"},
                {"id": "m1", "timestamp": "2026-11-01T08:00:00+0000", "media_type": "IMAGE"},
            ]})
        if path.startswith("/container-"):
            polls = self._polls[path] = self._polls.get(path, -1) + 1
            status = self.statuses[min(polls, len(self.statuses) - 1)]
            return httpx.Response(200, json={"status_code": status, "status": f"{status}: details"})
        if path == "/ig-1/media_publish":
            return httpx.Response(200, json={"id": "media-9"})
        if path == "/media-9":
            return httpx.Response(200, json={"permalink": "https://www.instagram.com/p/media-9/"})
        return httpx.Response(404, json={"error": {"message": "Unknown path", "code": 803}})

    def calls(self, suffix: str, method: str | None = None) -> list[httpx.Request]:
        return [request for request in self.requests
                if request.url.path.endswith(suffix) and (method is None or request.method == method)]


@pytest.fixture
def graph(monkeypatch) -> FakeGraph:
    fake = FakeGraph()
    transport = httpx.MockTransport(fake)
    monkeypatch.setattr(networks, "NETWORKS", (FacebookPagesNetwork(transport=transport), InstagramNetwork(transport=transport)))
    monkeypatch.setattr(settings, "social_apps", {"facebook_pages": SocialAppCredentials("meta-app", "meta-secret")})
    monkeypatch.setattr(settings, "social_oauth_redirect_uri", REDIRECT)
    monkeypatch.setattr(settings, "social_facebook_login_config_id", "")
    monkeypatch.setattr(settings, "social_meta_graph_version", "v26.0")
    monkeypatch.setattr(meta, "POLL_SECONDS", 0)
    return fake


def network(graph: FakeGraph) -> InstagramNetwork:
    return InstagramNetwork(transport=httpx.MockTransport(graph))


def connect(test_client, key: str = "instagram") -> dict[str, list[str]]:
    response = test_client.post(f"/connectors/social/networks/{key}/connect", json={"return_to": RETURN_TO},
                                headers=owner_headers())
    assert response.status_code == 200, response.text
    state = parse_qs(urlparse(response.json()["authorize_url"]).query)["state"][0]
    callback = test_client.get("/connectors/social/oauth/callback", params={"code": "auth-code", "state": state},
                               follow_redirects=False)
    return handoff_result(test_client, callback, TEST_USER_EMAIL)


def accounts(test_client) -> list[dict]:
    return test_client.get("/connectors/social/accounts", headers=owner_headers()).json()


def form(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.content.decode())


def test_without_a_login_configuration_the_dialog_asks_for_the_instagram_scopes(test_client, graph):
    response = test_client.post("/connectors/social/networks/instagram/connect", json={"return_to": RETURN_TO},
                                headers=owner_headers())
    url = urlparse(response.json()["authorize_url"])

    assert (url.netloc, url.path) == ("www.facebook.com", "/v26.0/dialog/oauth"), "the same Facebook sign-in"
    assert parse_qs(url.query)["scope"] == ["pages_show_list,pages_read_engagement,instagram_basic,instagram_content_publish"]


def test_the_sign_in_connects_each_professional_account_linked_to_a_shared_page(test_client, graph):
    result = connect(test_client)

    assert result["social_oauth"] == ["success"] and result["network"] == ["instagram"]
    [shown] = accounts(test_client)
    assert (shown["handle"], shown["display_name"], shown["avatar_url"]) == ("@acme", "Acme Co", "https://cdn.example/acme-ig.jpg")
    assert shown["token_expires_at"] is None, "it posts with the Page token, which has no fixed expiry"

    [saved] = SocialAccountRepository().list(account_for(TEST_USER_EMAIL))
    assert saved.external_id == "ig-1" and saved.grant_id == "fb-user-1"
    assert saved.credentials() == CREDENTIALS
    assert "instagram_business_account{" in graph.calls("/me/accounts")[0].url.params["fields"]


def test_pages_without_a_linked_professional_account_are_explained(test_client, graph):
    graph.pages = [graph.pages[1]]
    result = connect(test_client)

    assert result["reason"] == ["no_accounts"]
    assert result["detail"][0].startswith("No Instagram professional account is linked to Acme Labs.")
    assert accounts(test_client) == []


def test_a_login_configuration_without_the_instagram_permissions_is_our_setup(test_client, graph):
    graph.permissions = [("pages_show_list", "granted"), ("pages_manage_posts", "granted")]
    graph.pages = [{key: value for key, value in page.items() if key != "instagram_business_account"} for page in graph.pages]
    result = connect(test_client)

    assert result["detail"] == ["InnoMight Labs' Facebook connection isn't set up to ask to see the Instagram accounts "
                                "linked to them and post to Instagram yet, so no Instagram account could be connected. "
                                "This is on our side: contact hello@innomightlabs.com."]


@pytest.mark.asyncio
async def test_one_image_is_a_container_waited_for_then_published(graph):
    published = await network(graph).publish(CREDENTIALS, PreparedPost(text="Look #acme", images=(image("A red bike"),)))

    [create] = graph.calls("/ig-1/media", "POST")
    assert form(create) == {"image_url": ["https://api.example/connectors/social/media/token-0.jpg"],
                            "caption": ["Look #acme"], "alt_text": ["A red bike"]}
    assert create.headers["Authorization"] == "Bearer page-token-111"
    assert len(graph.calls("/container-1")) == 2, "it polls until FINISHED"
    [publish] = graph.calls("/ig-1/media_publish")
    assert form(publish) == {"creation_id": ["container-1"]}
    assert published.external_id == "media-9" and published.url == "https://www.instagram.com/p/media-9/"


@pytest.mark.asyncio
async def test_a_carousel_puts_the_caption_on_the_parent_only(graph):
    await network(graph).publish(CREDENTIALS, PreparedPost(text="Album", images=(image(index=0), image(index=1))))

    first, second, parent = (form(request) for request in graph.calls("/ig-1/media", "POST"))
    assert first == {"image_url": ["https://api.example/connectors/social/media/token-0.jpg"], "is_carousel_item": ["true"]}
    assert second["is_carousel_item"] == ["true"] and "caption" not in second
    assert parent == {"media_type": ["CAROUSEL"], "children": ["container-1,container-2"], "caption": ["Album"]}
    assert form(graph.calls("/ig-1/media_publish")[0]) == {"creation_id": ["container-3"]}


@pytest.mark.asyncio
async def test_a_container_instagram_refuses_is_rejected_and_never_published(graph):
    graph.statuses = ["ERROR"]
    with pytest.raises(PublishError) as raised:
        await network(graph).publish(CREDENTIALS, PreparedPost(text="Look", images=(image(),)))

    assert raised.value.kind == PublishErrorKind.REJECTED
    assert str(raised.value) == "Instagram could not use the post's media: ERROR: details"
    assert graph.calls("/ig-1/media_publish") == []


@pytest.mark.asyncio
async def test_a_container_still_processing_at_the_timeout_is_safe_to_retry(graph, monkeypatch):
    graph.statuses = ["IN_PROGRESS"]
    monkeypatch.setattr(settings, "social_publish_timeout_seconds", 0)
    with pytest.raises(PublishError) as raised:
        await network(graph).publish(CREDENTIALS, PreparedPost(text="Look", images=(image(),)))

    assert raised.value.kind == PublishErrorKind.TRANSIENT
    assert graph.calls("/ig-1/media_publish") == []


@pytest.mark.asyncio
async def test_publishing_that_fails_on_meta_may_have_posted(graph):
    graph.failures["/ig-1/media_publish"] = httpx.Response(500, json={"error": {"code": 2}})
    with pytest.raises(PublishError) as raised:
        await network(graph).publish(CREDENTIALS, PreparedPost(text="Look", images=(image(),)))
    assert raised.value.kind == PublishErrorKind.UNCERTAIN


@pytest.mark.asyncio
async def test_a_permalink_that_cannot_be_read_leaves_the_post_published(graph):
    graph.failures["/media-9"] = httpx.Response(500)
    published = await network(graph).publish(CREDENTIALS, PreparedPost(text="Look", images=(image(),)))
    assert published.external_id == "media-9" and published.url is None


@pytest.mark.asyncio
async def test_recent_posts_reads_the_accounts_own_media(graph):
    posts = await network(graph).recent_posts(CREDENTIALS, limit=5)

    assert [(post.external_id, post.text, post.media) for post in posts] == [("m2", "Second", "carousel"), ("m1", "", "image")]
    assert posts[0].posted_at == datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)
    assert graph.calls("/ig-1/media", "GET")[0].url.params["limit"] == "5"


def test_disconnecting_instagram_keeps_the_facebook_grant_its_pages_still_use(test_client, graph):
    connect(test_client, "facebook_page")
    connect(test_client, "instagram")
    by_network = {account["network"]: account for account in accounts(test_client)}

    test_client.delete(f"/connectors/social/accounts/{by_network['instagram']['social_account_id']}", headers=owner_headers())
    assert graph.calls("/me/permissions", "DELETE") == [], "one Facebook grant serves both networks"

    for account in accounts(test_client):
        test_client.delete(f"/connectors/social/accounts/{account['social_account_id']}", headers=owner_headers())
    assert len(graph.calls("/me/permissions", "DELETE")) == 1, "the last account of the grant ends it"
