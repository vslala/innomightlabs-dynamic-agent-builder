"""A member's access, service by service: the summary the IAM portal shows (pure, no AWS)."""

from src.iam.access_summary import ActionAccess, summarize
from src.iam.actions import SERVICES
from src.iam.builtins import ADMINISTRATOR_ACCESS, MEMBER_ACCESS, OWNER_ACCESS, VIEW_ONLY_ACCESS
from src.iam.engine import NamedPolicy
from src.iam.policy import OWNER_CONDITION, VERSION, PolicyDocument


def policy(*statements: dict, title: str = "Custom") -> NamedPolicy:
    document = PolicyDocument.model_validate({"Version": VERSION, "Statement": list(statements)})
    return NamedPolicy("custom:p1", document, title)


def access(policies: list[NamedPolicy]) -> dict[str, ActionAccess]:
    return {action.action.name: action for service in summarize(policies) for action in service.actions}


def levels(policies: list[NamedPolicy]) -> dict[str, str]:
    return {service.service.name: service.level for service in summarize(policies)}


def test_every_service_is_listed_in_catalog_order():
    assert [service.service.name for service in summarize([])] == [service.name for service in SERVICES]


def test_a_member_with_no_policies_reaches_only_what_they_own():
    actions = access([OWNER_ACCESS])

    assert actions["agents:Chat"].level == "own"
    assert actions["skills:Install"].level == "own", "skills act on an agent, which has an owner"
    assert actions["agents:Create"].level == "none", "a new agent has no owner yet, so the condition can't allow it"
    assert actions["agents:List"].level == "none"
    assert actions["settings:Manage"].level == "none", "account-wide actions have no owner"
    assert levels([OWNER_ACCESS])["agents"] == "limited"
    assert levels([OWNER_ACCESS])["billing"] == "none"


def test_member_access_adds_creating_and_listing():
    actions = access([OWNER_ACCESS, MEMBER_ACCESS])

    assert actions["agents:Create"].level == "all"
    assert actions["knowledge:List"].level == "all"
    assert actions["iam:ListMembers"].level == "all"
    assert actions["iam:Invite"].level == "none"
    assert actions["agents:Create"].allow.policies == ("MemberAccess",)


def test_the_owner_runs_the_account_but_reaches_contents_only_of_what_they_own():
    actions = access([OWNER_ACCESS, ADMINISTRATOR_ACCESS])

    assert levels([OWNER_ACCESS, ADMINISTRATOR_ACCESS])["iam"] == "full"
    assert actions["agents:Delete"].level == "all"
    assert actions["agents:Chat"].level == "own", "AdministratorAccess holds no contents actions"


def test_view_only_sees_lists_and_metadata():
    actions = access([OWNER_ACCESS, VIEW_ONLY_ACCESS])

    assert actions["automations:Describe"].level == "all"
    assert actions["automations:Run"].level == "own"
    assert actions["iam:ListPolicies"].level == "all"
    assert actions["iam:AttachPolicies"].level == "none"


def test_named_resources_are_some_and_listed():
    support = policy({"Effect": "Allow", "Action": "agents:Chat", "Resource": ["agent/b2", "agent/a1"]}, title="Support")
    actions = access([OWNER_ACCESS, support])

    assert actions["agents:Chat"].level == "some"
    assert actions["agents:Chat"].allow.resources == ("agent/a1", "agent/b2")
    assert actions["agents:Chat"].allow.policies == ("Support",)
    assert actions["agents:Get"].level == "own"


def test_type_wildcards_cover_every_resource_of_the_type():
    actions = access([policy({"Effect": "Allow", "Action": "knowledge:*", "Resource": "knowledge-base/*"})])

    assert actions["knowledge:Crawl"].level == "all"
    assert actions["knowledge:Create"].level == "all", "`type/*` covers the actions that name no resource"
    assert levels([policy({"Effect": "Allow", "Action": "knowledge:*", "Resource": "knowledge-base/*"})])["knowledge"] == "full"


def test_a_deny_on_everything_wins_over_any_allow():
    actions = access([ADMINISTRATOR_ACCESS, policy({"Effect": "Deny", "Action": "billing:*", "Resource": "*"})])

    assert actions["billing:Manage"].level == "denied"
    assert actions["billing:Manage"].deny.policies == ("Custom",)
    assert levels([ADMINISTRATOR_ACCESS, policy({"Effect": "Deny", "Action": "billing:*", "Resource": "*"})])["billing"] == "none"


def test_a_deny_on_some_resources_is_reported_beside_the_allow():
    no_prod = policy({"Effect": "Deny", "Action": "agents:Delete", "Resource": "agent/prod"})
    actions = access([ADMINISTRATOR_ACCESS, no_prod])

    assert actions["agents:Delete"].level == "all"
    assert (actions["agents:Delete"].deny.scope, actions["agents:Delete"].deny.resources) == ("some", ("agent/prod",))
    assert levels([ADMINISTRATOR_ACCESS, no_prod])["agents"] == "limited"


def test_owner_conditioned_statements_never_reach_collection_actions():
    own_create = policy({"Effect": "Allow", "Action": "agents:*", "Resource": "*", "Condition": OWNER_CONDITION})

    assert access([own_create])["agents:Create"].level == "none"
    assert access([own_create])["agents:Update"].level == "own"


def test_a_statement_reaches_only_its_own_resource_type():
    knowledge_only = policy({"Effect": "Allow", "Action": "*", "Resource": "knowledge-base/*", "Condition": OWNER_CONDITION},
                            {"Effect": "Allow", "Action": "*", "Resource": "knowledge-base/kb1"})
    actions = access([knowledge_only])

    assert actions["knowledge:Update"].level == "some", "a named resource beats the owner condition"
    assert actions["agents:Update"].level == "none", "knowledge-base patterns never reach agents"
    assert actions["billing:View"].level == "none", "type patterns never reach account-wide actions"
