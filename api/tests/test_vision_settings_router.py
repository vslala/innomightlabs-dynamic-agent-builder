"""The account's image-reading setting: members read it, only admins change it, and only vision models can be chosen."""

from __future__ import annotations

import pytest

from src.accounts import AccountService, Member
from src.iam.service import IamService
from src.identity import IdentityRepository
from src.llm.models import ModelInfo
from src.vision.repository import VisionSettingsRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, account_for, user_id_for
from tests.oauth_handoff import owner_headers

ADMIN_EMAIL, MEMBER_EMAIL = TEST_USER_EMAIL, TEST_USER_EMAIL_2
SEES_IMAGES = {"enabled": True, "provider_name": "Bedrock", "model_name": "claude-3-haiku"}


@pytest.fixture(autouse=True)
def bedrock_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    models = [
        ModelInfo(model_id="a", model_name="claude-3-haiku", display_name="Claude 3 Haiku", provider="bedrock",
                  capabilities=["image_understanding"]),
        ModelInfo(model_id="b", model_name="text-only", display_name="Text Only", provider="bedrock"),
    ]
    monkeypatch.setattr("src.llm.models.models_service.get_bedrock_models", lambda *a, **k: models)


@pytest.fixture
def team(dynamodb_table) -> str:
    """An account the first user administers and the second belongs to as a plain member."""
    created = AccountService().create_account(IdentityRepository().get(user_id_for(ADMIN_EMAIL)), "Team")
    member = IdentityRepository().find_by_email(MEMBER_EMAIL)
    dynamodb_table.put_item(
        Item=Member(account_id=created.account_id, user_id=member.user_id, email=MEMBER_EMAIL, name=member.name).to_dynamo_item()
    )
    IamService().attach(created.account_id, user_id_for(ADMIN_EMAIL), "member", member.user_id, "MemberAccess")
    return created.account_id


def as_(email: str, account: str) -> dict[str, str]:
    return {**owner_headers(email), "X-Account-Id": account}


def test_an_admin_turns_it_on_with_a_vision_model(test_client, team) -> None:
    saved = test_client.put("/vision/settings", json=SEES_IMAGES, headers=as_(ADMIN_EMAIL, team))

    assert saved.status_code == 200, saved.text
    assert saved.json() == {**SEES_IMAGES, "is_configured": True}
    stored = VisionSettingsRepository().find_in_account(team)
    assert stored is not None and stored.updated_by == user_id_for(ADMIN_EMAIL)


def test_a_plain_member_can_read_the_setting_but_not_change_it(test_client, team) -> None:
    test_client.put("/vision/settings", json=SEES_IMAGES, headers=as_(ADMIN_EMAIL, team))
    member = as_(MEMBER_EMAIL, team)

    assert test_client.put("/vision/settings", json={"enabled": False}, headers=member).status_code == 403
    assert test_client.get("/vision/settings", headers=member).json()["model_name"] == "claude-3-haiku"
    assert VisionSettingsRepository().find_in_account(team).enabled is True  # type: ignore[union-attr]


def test_a_model_that_cannot_read_images_is_refused(test_client, team) -> None:
    refused = test_client.put(
        "/vision/settings", json={**SEES_IMAGES, "model_name": "text-only"}, headers=as_(ADMIN_EMAIL, team)
    )

    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "vision_model_unsupported"
    assert VisionSettingsRepository().find_in_account(team) is None


def test_a_model_that_does_not_exist_is_refused(test_client, team) -> None:
    refused = test_client.put(
        "/vision/settings", json={**SEES_IMAGES, "model_name": "made-up"}, headers=as_(ADMIN_EMAIL, team)
    )

    assert refused.json()["detail"]["code"] == "vision_model_unsupported"


def test_enabling_needs_a_provider_and_model(test_client, team) -> None:
    response = test_client.put("/vision/settings", json={"enabled": True}, headers=as_(ADMIN_EMAIL, team))

    assert response.status_code == 422


def test_turning_it_off_forgets_the_model(test_client, team) -> None:
    test_client.put("/vision/settings", json=SEES_IMAGES, headers=as_(ADMIN_EMAIL, team))

    off = test_client.put("/vision/settings", json={"enabled": False, **{"provider_name": "Bedrock"}}, headers=as_(ADMIN_EMAIL, team))

    assert off.json() == {"enabled": False, "provider_name": None, "model_name": None, "is_configured": False}


def test_each_account_has_its_own_setting(test_client, team) -> None:
    test_client.put("/vision/settings", json=SEES_IMAGES, headers=as_(ADMIN_EMAIL, team))

    personal = test_client.get("/vision/settings", headers=owner_headers(ADMIN_EMAIL)).json()

    assert personal["enabled"] is False, "the admin's personal account is a different account"
    assert VisionSettingsRepository().find_in_account(account_for(ADMIN_EMAIL)) is None


def test_the_form_offers_only_models_that_read_images(test_client, team) -> None:
    form = test_client.get("/vision/settings/schema", headers=as_(ADMIN_EMAIL, team)).json()

    fields = {field["name"]: field for field in form["form_inputs"]}
    assert fields["model_name"]["options_source"]["type"] == "vision_models"
    assert [option["value"] for option in fields["model_name"]["options"]] == ["claude-3-haiku"]
    assert "Bedrock" in [option["value"] for option in fields["provider_name"]["options"]]
