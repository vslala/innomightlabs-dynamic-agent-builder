"""Accounts and memberships: one identity, many independent accounts (KAN-75)."""
import pytest
from fastapi.testclient import TestClient

from src.accounts import Account, AccountRepository, AccountService, Member, personal_account_id
from src.identity import Identity, IdentityRepository
from tests.mock_data import TEST_USER_EMAIL
from tests.oauth_handoff import owner_headers
from tests.test_identity import EMAIL, SignsIn, sign_in


@pytest.fixture
def accounts(dynamodb_table) -> AccountService:
    return AccountService()


@pytest.fixture
def ada(dynamodb_table) -> Identity:
    return IdentityRepository().create(Identity(email="ada@example.com", name="Ada"))


@pytest.fixture
def grace(dynamodb_table) -> Identity:
    return IdentityRepository().create(Identity(email="grace@example.com", name="Grace"))


def keys_in(table, account_id: str) -> set[str]:
    items = table.query(KeyConditionExpression="pk = :pk", ExpressionAttributeValues={":pk": f"Account#{account_id}"})
    return {item["sk"] for item in items["Items"]}


def owned_account_count(table, user_id: str) -> int:
    item = table.get_item(Key={"pk": f"Identity#{user_id}", "sk": "OwnedAccountCount"}).get("Item")
    return int(item["n"]) if item else 0


def join(table, account: Account, person: Identity, *policies: str, groups: tuple[str, ...] = ()) -> None:
    """Stands in for accepting an invite (KAN-82) and for the IAM module's attachments and groups (KAN-77)."""
    pk = f"Account#{account.account_id}"
    table.put_item(Item=Member(account_id=account.account_id, user_id=person.user_id, email=person.email,
                               name=person.name, invited_by=account.created_by).to_dynamo_item())
    for policy in policies:
        table.put_item(Item={"pk": pk, "sk": f"Attachment#member#{person.user_id}#{policy}", "policy": policy})
    for group_id in groups:
        table.put_item(Item={"pk": pk, "sk": f"Member#{person.user_id}#Group#{group_id}"})
        table.put_item(Item={"pk": pk, "sk": f"GroupMember#{group_id}#{person.user_id}"})


def test_the_creator_is_the_only_member_and_an_admin(accounts, ada, dynamodb_table):
    account = accounts.create_account(ada, "Ada's lab")

    assert keys_in(dynamodb_table, account.account_id) == {
        "Account#Metadata",
        f"Member#{ada.user_id}",
        f"Attachment#member#{ada.user_id}#AdministratorAccess",
    }
    member = AccountRepository().get_member(account.account_id, ada.user_id)
    assert (member.email, member.name, member.status) == (ada.email, ada.name, "active")
    assert AccountRepository().get(account.account_id) == account


def test_every_account_created_is_counted_against_its_creator(accounts, ada, dynamodb_table):
    accounts.create_account(ada, "One")
    accounts.create_account(ada, "Two")

    assert owned_account_count(dynamodb_table, ada.user_id) == 2


def test_one_person_belongs_to_several_independent_accounts(accounts, ada, grace, dynamodb_table):
    own = accounts.create_account(ada, "Ada's lab")
    graces = accounts.create_account(grace, "Grace's lab")
    join(dynamodb_table, graces, ada, "MemberAccess")

    listed = {(entry.name, entry.access_summary) for entry in accounts.list_accounts(ada.user_id)}

    assert listed == {("Ada's lab", "admin"), ("Grace's lab", "member")}
    assert [entry.account_id for entry in accounts.list_accounts(grace.user_id)] == [graces.account_id]
    assert owned_account_count(dynamodb_table, ada.user_id) == 1, "joining an account doesn't count as owning one"
    assert own.account_id != graces.account_id


def test_removing_a_member_leaves_the_person_and_their_other_accounts(accounts, ada, grace, dynamodb_table):
    own = accounts.create_account(ada, "Ada's lab")
    graces = accounts.create_account(grace, "Grace's lab")
    join(dynamodb_table, graces, ada, "MemberAccess", "custom:p1", groups=("g1", "g2"))
    before = AccountRepository().get(graces.account_id)

    accounts.remove_member(graces.account_id, ada.user_id)

    assert keys_in(dynamodb_table, graces.account_id) == {
        "Account#Metadata",
        f"Member#{grace.user_id}",
        f"Attachment#member#{grace.user_id}#AdministratorAccess",
    }, "the membership, its attachments and its groups are gone; Grace's are not"
    assert AccountRepository().get(graces.account_id).authz_version == before.authz_version + 1
    assert IdentityRepository().get(ada.user_id) == ada
    assert [entry.account_id for entry in accounts.list_accounts(ada.user_id)] == [own.account_id]
    assert keys_in(dynamodb_table, own.account_id) == {
        "Account#Metadata",
        f"Member#{ada.user_id}",
        f"Attachment#member#{ada.user_id}#AdministratorAccess",
    }


def test_a_person_without_an_account_gets_one_personal_account(accounts, ada, dynamodb_table):
    created = accounts.ensure_personal_account(ada)
    again = accounts.ensure_personal_account(ada)

    assert created is not None and created.account_id == personal_account_id(ada.user_id)
    assert again is None
    assert [(entry.name, entry.access_summary) for entry in accounts.list_accounts(ada.user_id)] == [("Personal", "admin")]


def test_a_member_of_another_account_gets_no_personal_account(accounts, ada, grace, dynamodb_table):
    join(dynamodb_table, accounts.create_account(grace, "Grace's lab"), ada, "MemberAccess")

    assert accounts.ensure_personal_account(ada) is None
    assert AccountRepository().get(personal_account_id(ada.user_id)) is None


def test_racing_sign_ins_make_one_personal_account(accounts, ada, dynamodb_table, monkeypatch):
    """Both sign-ins saw no membership before either wrote; the account id is the person's, so one wins."""
    accounts.ensure_personal_account(ada)
    monkeypatch.setattr(accounts.repository, "list_memberships", lambda _user_id: [])

    assert accounts.ensure_personal_account(ada) is None
    assert len(AccountRepository().list_memberships(ada.user_id)) == 1
    assert owned_account_count(dynamodb_table, ada.user_id) == 1, "the losing transaction counted nothing"


def test_signing_up_creates_the_personal_account_once(test_client: TestClient, monkeypatch):
    claims = sign_in(test_client, monkeypatch, SignsIn())
    sign_in(test_client, monkeypatch, SignsIn())

    memberships = AccountRepository().list_memberships(claims["sub"])
    assert [member.account_id for member in memberships] == [personal_account_id(claims["sub"])]
    assert IdentityRepository().find_by_email(EMAIL).user_id == claims["sub"]


def test_local_sign_up_creates_the_personal_account(test_client: TestClient, monkeypatch):
    monkeypatch.setattr("src.config.settings.environment", "local")

    test_client.post("/auth/local/signup", json={"username": "ada", "password": "correct horse"})

    identity = IdentityRepository().find_by_email("ada@example.com")
    assert AccountRepository().get_member(personal_account_id(identity.user_id), identity.user_id) is not None


def test_creating_and_listing_accounts_over_http(test_client: TestClient):
    headers = owner_headers(TEST_USER_EMAIL)

    created = test_client.post("/accounts", json={"name": "  Side project  "}, headers=headers)
    listed = test_client.get("/accounts", headers=headers)

    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Side project"
    assert [(entry["account_id"], entry["access_summary"]) for entry in listed.json()] == [
        (created.json()["account_id"], "admin")
    ]


def test_an_account_needs_a_name(test_client: TestClient):
    response = test_client.post("/accounts", json={"name": "   "}, headers=owner_headers(TEST_USER_EMAIL))

    assert response.status_code == 422


def test_accounts_require_sign_in(test_client: TestClient):
    assert test_client.get("/accounts").status_code == 401
