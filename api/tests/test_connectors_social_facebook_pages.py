"""Facebook Pages: one Facebook sign-in connects every Page the person can post as, and a post is by the Page."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from src.config import settings
from src.config.settings import SocialAppCredentials
from src.connectors.social import networks
from src.connectors.social.models import SocialAccount
from src.connectors.social.networks.base import PreparedImage, PreparedPost, PublishError, PublishErrorKind
from src.connectors.social.networks.facebook_pages import FacebookPagesNetwork
from src.connectors.social.repository import SocialAccountRepository
from src.crypto import encrypt
from tests.mock_data import TEST_USER_EMAIL, account_for, user_id_for
from tests.oauth_handoff import handoff_result, owner_headers

RETURN_TO = "http://localhost:5173/dashboard/connectors?tab=social"
REDIRECT = "http://localhost:8000/connectors/social/oauth/callback"
CREDENTIALS = {"page_access_token": "page-token-111", "page_id": "111", "user_access_token": "user-token"}
IMAGE = PreparedImage(data=b"\xff\xd8jpeg", mime_type="image/jpeg")


class FakeGraph:
    """The Graph API endpoints Facebook Pages uses: tokens, /me, /me/accounts, photos, feed, posts, permissions."""

    def __init__(self) -> None:
        self.user_id = "fb-user-1"
        self.pages = [
            {"id": "111", "name": "Acme", "access_token": "page-token-111", "tasks": ["MANAGE", "CREATE_CONTENT"],
             "picture": {"data": {"url": "https://cdn.example/acme.jpg"}}},
            {"id": "222", "name": "Acme Labs", "access_token": "page-token-222", "tasks": ["CREATE_CONTENT"]},
            {"id": "333", "name": "Watched", "access_token": "page-token-333", "tasks": ["ANALYZE"]},
        ]
        #: path -> a response to answer instead of the normal one
        self.failures: dict[str, httpx.Response] = {}
        self.requests: list[httpx.Request] = []
        self.photos = 0
        self.permissions: list[tuple[str, str]] = [("pages_show_list", "granted")]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/v26.0")
        if path in self.failures:
            return self.failures[path]
        if path == "/oauth/access_token":
            if "fb_exchange_token" in request.url.params:
                return httpx.Response(200, json={"access_token": "user-token", "expires_in": 5183944})
            return httpx.Response(200, json={"access_token": "short-token", "expires_in": 3600})
        if path == "/me":
            return httpx.Response(200, json={"id": self.user_id})
        if path == "/me/accounts":
            return httpx.Response(200, json={"data": self.pages})
        if path == "/me/permissions":
            if request.method == "GET":
                return httpx.Response(200, json={"data": [{"permission": name, "status": status}
                                                          for name, status in self.permissions]})
            return httpx.Response(200, json={"success": True})
        if path.endswith("/photos"):
            self.photos += 1
            if b'name="published"' in request.content:
                return httpx.Response(200, json={"id": f"photo-{self.photos}"})
            return httpx.Response(200, json={"id": f"photo-{self.photos}", "post_id": "111_555"})
        if path.endswith("/feed"):
            return httpx.Response(200, json={"id": "111_999"})
        if path.endswith("/posts"):
            return httpx.Response(200, json={"data": [
                {"id": "111_2", "message": "Second", "created_time": "2026-11-02T09:30:00+0000",
                 "permalink_url": "https://www.facebook.com/111/posts/2", "attachments": {"data": [{"media_type": "album"}]}},
                {"id": "111_1", "created_time": "2026-11-01T08:00:00+0000"},
            ]})
        return httpx.Response(404, json={"error": {"message": "Unknown path", "code": 803}})

    def calls(self, suffix: str, method: str | None = None) -> list[httpx.Request]:
        return [request for request in self.requests
                if request.url.path.endswith(suffix) and (method is None or request.method == method)]


@pytest.fixture
def graph(monkeypatch) -> FakeGraph:
    fake = FakeGraph()
    monkeypatch.setattr(networks, "NETWORKS", (FacebookPagesNetwork(transport=httpx.MockTransport(fake)),))
    monkeypatch.setattr(settings, "social_apps", {"facebook_pages": SocialAppCredentials("meta-app", "meta-secret")})
    monkeypatch.setattr(settings, "social_oauth_redirect_uri", REDIRECT)
    monkeypatch.setattr(settings, "social_facebook_login_config_id", "")
    monkeypatch.setattr(settings, "social_meta_graph_version", "v26.0")
    return fake


def network(graph: FakeGraph) -> FacebookPagesNetwork:
    return FacebookPagesNetwork(transport=httpx.MockTransport(graph))


def start(test_client) -> str:
    response = test_client.post("/connectors/social/networks/facebook_page/connect", json={"return_to": RETURN_TO},
                                headers=owner_headers())
    assert response.status_code == 200, response.text
    return response.json()["authorize_url"]


def connect_pages(test_client) -> dict[str, list[str]]:
    state = parse_qs(urlparse(start(test_client)).query)["state"][0]
    callback = test_client.get("/connectors/social/oauth/callback", params={"code": "auth-code", "state": state},
                               follow_redirects=False)
    return handoff_result(test_client, callback, TEST_USER_EMAIL)


def accounts(test_client) -> list[dict]:
    return test_client.get("/connectors/social/accounts", headers=owner_headers()).json()


def form(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.content.decode())


def test_without_a_login_configuration_the_dialog_asks_for_the_page_scopes(test_client, graph):
    url = urlparse(start(test_client))
    query = parse_qs(url.query)

    assert (url.netloc, url.path) == ("www.facebook.com", "/v26.0/dialog/oauth")
    assert query["client_id"] == ["meta-app"] and query["response_type"] == ["code"]
    assert query["scope"] == ["pages_show_list,pages_manage_posts,pages_read_engagement"]
    assert "config_id" not in query


def test_a_login_configuration_decides_the_permissions_instead_of_scope(test_client, graph, monkeypatch):
    monkeypatch.setattr(settings, "social_facebook_login_config_id", "2417542848653209")

    query = parse_qs(urlparse(start(test_client)).query)

    assert query["config_id"] == ["2417542848653209"] and query["override_default_response_type"] == ["true"]
    assert "scope" not in query


def test_one_sign_in_connects_every_page_the_person_can_post_as(test_client, graph):
    result = connect_pages(test_client)

    assert result["social_oauth"] == ["success"] and result["network"] == ["facebook_page"]
    shown = {account["display_name"]: account for account in accounts(test_client)}
    assert set(shown) == {"Acme", "Acme Labs"}, "a Page the person can only analyse can't be posted to"
    assert shown["Acme"]["avatar_url"] == "https://cdn.example/acme.jpg"
    assert shown["Acme"]["token_expires_at"] is None, "Page tokens have no fixed expiry"
    assert "page-token" not in json.dumps(accounts(test_client))

    saved = {account.external_id: account for account in SocialAccountRepository().list(account_for(TEST_USER_EMAIL))}
    assert saved["111"].credentials() == {"page_access_token": "page-token-111", "page_id": "111",
                                          "user_access_token": "user-token"}
    assert {account.grant_id for account in saved.values()} == {"fb-user-1"}
    assert {account.external_id for account in SocialAccountRepository().for_grant("facebook_page", "fb-user-1")} == {"111", "222"}


def test_the_code_is_exchanged_and_then_made_long_lived(test_client, graph):
    connect_pages(test_client)

    short, long = graph.calls("/oauth/access_token")
    assert short.url.params["code"] == "auth-code" and short.url.params["redirect_uri"] == REDIRECT
    assert long.url.params["grant_type"] == "fb_exchange_token" and long.url.params["fb_exchange_token"] == "short-token"
    assert graph.calls("/me/accounts")[0].headers["Authorization"] == "Bearer user-token"


def test_a_person_who_cannot_post_as_any_page_is_told_so(test_client, graph):
    graph.pages = [graph.pages[2]]
    result = connect_pages(test_client)
    assert result["social_oauth"] == ["error"] and result["reason"] == ["no_accounts"]
    assert accounts(test_client) == []


def outcome_of_a_sign_in_with(test_client, graph, pages: list[dict], permissions: list[tuple[str, str]]) -> dict:
    graph.pages = pages
    graph.permissions = permissions
    result = connect_pages(test_client)
    assert result["social_oauth"] == ["error"] and result["reason"] == ["no_accounts"]
    assert accounts(test_client) == []
    return result


ALL_PERMISSIONS = [("public_profile", "granted"), ("pages_show_list", "granted"), ("pages_manage_posts", "granted")]


def test_a_permission_switched_off_is_named_in_the_persons_terms(test_client, graph, caplog):
    with caplog.at_level("INFO"):
        result = outcome_of_a_sign_in_with(test_client, graph, [], [("pages_show_list", "granted"), ("pages_manage_posts", "declined")])

    assert result["detail"] == ["Facebook didn't give permission to post to your Pages. Connect again and leave every "
                                "permission Facebook asks for switched on."]
    assert "permissions granted: pages_show_list" in caplog.text, "the log keeps the permission names"
    assert "user-token" not in caplog.text and "page-token" not in caplog.text


def test_a_permission_the_app_never_asked_for_is_reported_as_our_setup(test_client, graph, caplog):
    granted = [("public_profile", "granted"), ("instagram_basic", "granted"), ("ads_read", "granted")]
    with caplog.at_level("INFO"):
        result = outcome_of_a_sign_in_with(test_client, graph, [], granted)

    assert result["detail"] == ["InnoMight Labs' Facebook connection isn't set up to ask to see your Pages and post to "
                                "your Pages yet, so no Page could be connected. This is on our side: contact "
                                "hello@innomightlabs.com."]
    assert "The Facebook Login configuration doesn't ask for pages_show_list, pages_manage_posts" in caplog.text


def test_no_page_chosen_says_how_to_choose_one(test_client, graph):
    result = outcome_of_a_sign_in_with(test_client, graph, [], ALL_PERMISSIONS)
    assert result["detail"][0].startswith("No Page was shared with InnoMight Labs. Connect again")


def test_pages_without_a_posting_role_are_named(test_client, graph):
    result = outcome_of_a_sign_in_with(test_client, graph, [graph.pages[2]], ALL_PERMISSIONS)
    assert result["detail"][0].startswith("Your role on Watched doesn't allow posting.")


def test_a_page_listed_without_tasks_is_connected_with_its_page_token(test_client, graph):
    graph.pages = [{"id": "444", "name": "Portfolio Page", "access_token": "page-token-444"}]
    assert connect_pages(test_client)["social_oauth"] == ["success"]
    assert [account["display_name"] for account in accounts(test_client)] == ["Portfolio Page"]


def test_a_code_facebook_rejects_saves_nothing(test_client, graph):
    graph.failures["/oauth/access_token"] = httpx.Response(400, json={"error": {"message": "Invalid code", "code": 100}})
    assert connect_pages(test_client)["reason"] == ["callback_failed"]
    assert accounts(test_client) == []


def test_someone_else_reconnecting_a_page_moves_its_grant_to_them(test_client, graph):
    connect_pages(test_client)
    graph.user_id = "fb-user-2"

    connect_pages(test_client)

    repository = SocialAccountRepository()
    assert len(repository.list(account_for(TEST_USER_EMAIL))) == 2, "reconnecting refreshes, it doesn't duplicate"
    assert repository.for_grant("facebook_page", "fb-user-1") == []
    assert len(repository.for_grant("facebook_page", "fb-user-2")) == 2


@pytest.mark.asyncio
async def test_a_text_post_goes_to_the_pages_feed_as_the_page(graph):
    published = await network(graph).publish(CREDENTIALS, PreparedPost(text="Hello Facebook"))

    [feed] = graph.calls("/111/feed")
    assert form(feed) == {"message": ["Hello Facebook"]}
    assert feed.headers["Authorization"] == "Bearer page-token-111"
    assert published.external_id == "111_999" and published.url == "https://www.facebook.com/111_999"


@pytest.mark.asyncio
async def test_one_image_is_uploaded_and_posted_in_one_call(graph):
    published = await network(graph).publish(CREDENTIALS, PreparedPost(text="Look", images=(IMAGE,)))

    [photo] = graph.calls("/111/photos")
    assert b'name="message"' in photo.content and b"Look" in photo.content and b"\xff\xd8jpeg" in photo.content
    assert b'name="published"' not in photo.content
    assert graph.calls("/111/feed") == []
    assert published.url == "https://www.facebook.com/111_555"


@pytest.mark.asyncio
async def test_several_images_are_uploaded_unpublished_and_attached_to_one_post(graph):
    published = await network(graph).publish(CREDENTIALS, PreparedPost(text="Album", images=(IMAGE, IMAGE)))

    assert len(graph.calls("/111/photos")) == 2
    [feed] = graph.calls("/111/feed")
    assert form(feed) == {"message": ["Album"], "attached_media[0]": ['{"media_fbid": "photo-1"}'],
                          "attached_media[1]": ['{"media_fbid": "photo-2"}']}
    assert published.external_id == "111_999"


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "response", "kind"), [
    ("/111/feed", httpx.Response(400, json={"error": {"code": 190, "message": "Session expired"}}), PublishErrorKind.AUTH),
    ("/111/feed", httpx.Response(400, json={"error": {"code": 32, "message": "Page request limit"}}), PublishErrorKind.RATE_LIMITED),
    ("/111/feed", httpx.Response(500, json={"error": {"code": 2}}), PublishErrorKind.UNCERTAIN),
    ("/111/photos", httpx.Response(500, json={"error": {"code": 2}}), PublishErrorKind.TRANSIENT),
    ("/111/feed", httpx.Response(400, json={"error": {"code": 100, "error_user_msg": "Text is not allowed"}}), PublishErrorKind.REJECTED),
], ids=["expired token", "throttled", "post call failed", "unpublished upload failed", "refused"])
async def test_failures_are_classified_so_only_safe_retries_happen(graph, path, response, kind):
    graph.failures[path] = response
    with pytest.raises(PublishError) as raised:
        await network(graph).publish(CREDENTIALS, PreparedPost(text="Album", images=(IMAGE, IMAGE)))
    assert raised.value.kind == kind
    assert "page-token" not in str(raised.value)
    if kind == PublishErrorKind.REJECTED:
        assert str(raised.value) == "Facebook refused the post: Text is not allowed"


@pytest.mark.asyncio
async def test_a_post_call_that_times_out_may_have_posted(graph, monkeypatch):
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(PublishError) as raised:
        await FacebookPagesNetwork(transport=httpx.MockTransport(timeout)).publish(CREDENTIALS, PreparedPost(text="Hi"))
    assert raised.value.kind == PublishErrorKind.UNCERTAIN


@pytest.mark.asyncio
async def test_recent_posts_reads_the_pages_own_posts_newest_first(graph):
    posts = await network(graph).recent_posts(CREDENTIALS, limit=5)

    assert [(post.external_id, post.text, post.media) for post in posts] == [("111_2", "Second", "carousel"), ("111_1", "", "text")]
    assert posts[0].posted_at == datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)
    assert posts[0].url == "https://www.facebook.com/111/posts/2" and posts[1].url is None
    assert graph.calls("/111/posts")[0].url.params["limit"] == "5"


def test_disconnecting_one_page_keeps_the_grant_the_others_use_until_the_last_goes(test_client, graph):
    connect_pages(test_client)
    first, second = accounts(test_client)

    test_client.delete(f"/connectors/social/accounts/{first['social_account_id']}", headers=owner_headers())
    assert graph.calls("/me/permissions", "DELETE") == []

    test_client.delete(f"/connectors/social/accounts/{second['social_account_id']}", headers=owner_headers())
    [revoke] = graph.calls("/me/permissions", "DELETE")
    assert revoke.headers["Authorization"] == "Bearer user-token"
    assert SocialAccountRepository().for_grant("facebook_page", "fb-user-1") == []


def test_a_grant_another_innomightlabs_account_still_uses_is_not_revoked(test_client, graph):
    connect_pages(test_client)
    SocialAccountRepository().connect(SocialAccount(
        account_id="another-account", network="facebook_page", external_id="111", handle="Acme", display_name="Acme",
        encrypted_credentials=encrypt(json.dumps(CREDENTIALS)), grant_id="fb-user-1", connected_by=user_id_for(TEST_USER_EMAIL),
    ))

    for account in accounts(test_client):
        test_client.delete(f"/connectors/social/accounts/{account['social_account_id']}", headers=owner_headers())

    assert graph.calls("/me/permissions", "DELETE") == []
