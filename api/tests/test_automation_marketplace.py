from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from src.automation_marketplace.models import (
    ImportMarketplaceAutomationRequest,
    MarketplaceAutomationEdgeTemplate,
    MarketplaceAutomationNodeTemplate,
    MarketplaceAutomationSkillTemplate,
    MarketplaceAutomationStatus,
    MarketplaceAutomationTemplate,
    PublishMarketplaceAutomationRequest,
    SaveMarketplaceAutomationImportSessionRequest,
)
from src.automation_marketplace.repository import AutomationMarketplaceRepository
from src.automation_marketplace.service import AutomationMarketplaceService
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.automations.models import (
    Automation,
    AutomationEdge,
    AutomationNode,
    AutomationNodeType,
    AutomationSkill,
    AutomationTrigger,
    AutomationTriggerType,
)
from src.automations.repository import AutomationRepository
from src.form_models import Form, FormInput, FormInputType, FormOptionsSource
from tests.mock_data import TEST_USER_EMAIL


def _service(repo: AutomationRepository | None = None) -> AutomationMarketplaceService:
    automation_repo = repo or AutomationRepository()
    return AutomationMarketplaceService(
        repository=AutomationMarketplaceRepository(),
        automation_repository=automation_repo,
        automation_service=_FakeAutomationService(automation_repo),
    )


class _FakeAutomationService:
    def __init__(self, repo: AutomationRepository):
        self.repo = repo
        self.skill_registry = _FakeSkillRegistry()

    def get_graph(self, automation_id: str, user_email: str) -> SimpleNamespace:
        automation = self.repo.find_automation_by_id(automation_id, user_email)
        assert automation is not None
        nodes, edges, triggers = self.repo.get_graph(automation_id)
        return SimpleNamespace(automation=automation, nodes=nodes, edges=edges, triggers=triggers)

    def validate_graph(self, nodes, edges, triggers, user_email, automation_id=None):
        del nodes, edges, triggers, user_email, automation_id

    def validate_skill_config(
        self,
        *,
        skill_id,
        raw_config,
        user_email,
        validate_connectors=True,
    ):
        del user_email, validate_connectors
        loaded = self.skill_registry.get(skill_id)
        if not loaded:
            raise ValueError(f"Unknown skill: {skill_id}")
        form_inputs = loaded.manifest.form
        for form_input in form_inputs:
            if form_input.name not in raw_config:
                raise ValueError(f"Missing required field: {form_input.name}")
        return raw_config

    def install_skill(
        self,
        *,
        automation_id,
        skill_id,
        raw_config,
        user_email,
        enabled=True,
        validate_connectors=True,
    ):
        normalized = self.validate_skill_config(
            skill_id=skill_id,
            raw_config=raw_config,
            user_email=user_email,
            validate_connectors=validate_connectors,
        )
        loaded = self.skill_registry.get(skill_id)
        skill = AutomationSkill(
            automation_id=automation_id,
            installed_skill_id=skill_id,
            skill_id=skill_id,
            namespace="test",
            skill_name=loaded.manifest.name,
            skill_description="Test skill",
            enabled=enabled,
            config=normalized,
            enabled_by=user_email,
        )
        return self.repo.save_skill(skill)


class _FakeSkillRegistry:
    def get(self, skill_id: str):
        if skill_id == "agent_invocation":
            return SimpleNamespace(manifest=SimpleNamespace(name="Invoke Agent", form=self.install_form(skill_id, "").form_inputs))
        if skill_id == "google_mail":
            return SimpleNamespace(manifest=SimpleNamespace(name="Gmail", form=[]))
        return None

    def install_form(self, skill_id: str, submit_path: str):
        del submit_path
        if skill_id != "agent_invocation":
            return Form(form_name="Install", submit_path="", form_inputs=[])
        return Form(
            form_name="Invoke Agent",
            submit_path="",
            form_inputs=[
                FormInput(
                    input_type=FormInputType.SELECT,
                    name="target_agent_id",
                    label="Agent",
                    options_source=FormOptionsSource(type="agents"),
                )
            ],
        )


def _source_automation_with_graph(repo: AutomationRepository) -> tuple[Automation, list[AutomationNode], list[AutomationEdge]]:
    automation = repo.save_automation(Automation(title="Source workflow", created_by=TEST_USER_EMAIL))
    start = AutomationNode(
        automation_id=automation.automation_id,
        node_id="source-start",
        type=AutomationNodeType.START,
        name="Start",
        position={"x": 12.5, "y": 42.75},
    )
    final = AutomationNode(
        automation_id=automation.automation_id,
        node_id="source-final",
        type=AutomationNodeType.FINAL,
        name="Done",
        position={"x": 200.25, "y": 42.75},
    )
    edge = AutomationEdge(
        automation_id=automation.automation_id,
        edge_id="source-edge",
        source_node_id=start.node_id,
        target_node_id=final.node_id,
    )
    trigger = AutomationTrigger(
        automation_id=automation.automation_id,
        trigger_id="source-trigger",
        type=AutomationTriggerType.MANUAL,
        name="Manual",
        enabled=True,
        entry_node_id=start.node_id,
    )
    repo.save_graph(automation.automation_id, [start, final], [edge], [trigger])
    return automation, [start, final], [edge]


def test_automation_marketplace_import_preserves_node_ids_without_triggers(dynamodb_table):
    del dynamodb_table
    automation_repo = AutomationRepository()
    service = _service(automation_repo)
    source, nodes, edges = _source_automation_with_graph(automation_repo)

    published = service.publish_automation(
        user_email=TEST_USER_EMAIL,
        request=PublishMarketplaceAutomationRequest(
            automation_id=source.automation_id,
            title="Reusable workflow",
            short_description="Reusable",
            full_description="Reusable workflow",
            tags=["workflow"],
            included_node_ids=[node.node_id for node in nodes],
            included_edge_ids=[edge.edge_id for edge in edges],
            included_skill_ids=[],
            import_inputs=[],
            status=MarketplaceAutomationStatus.PUBLISHED,
        ),
    )

    imported = service.import_automation(
        template_id=published.template_id,
        user_email=TEST_USER_EMAIL,
        request=ImportMarketplaceAutomationRequest(
            title="Imported workflow",
            skill_configs={},
            import_inputs={},
        ),
    )

    imported_nodes, imported_edges, imported_triggers = automation_repo.get_graph(imported.automation_id)
    imported_node_ids = {node.node_id for node in imported_nodes}

    assert imported.title == "Imported workflow"
    assert imported_triggers == []
    assert imported_node_ids == {node.node_id for node in nodes}
    assert {edge.edge_id for edge in imported_edges}.isdisjoint({edge.edge_id for edge in edges})
    assert {
        (edge.source_node_id, edge.target_node_id)
        for edge in imported_edges
    } == {(edge.source_node_id, edge.target_node_id) for edge in edges}

    template = AutomationMarketplaceRepository().find_by_id(published.template_id)
    assert template is not None
    assert template.import_count == 1


def test_automation_marketplace_publish_exports_complete_graph(dynamodb_table):
    del dynamodb_table
    automation_repo = AutomationRepository()
    service = _service(automation_repo)
    source, nodes, edges = _source_automation_with_graph(automation_repo)

    published = service.publish_automation(
        user_email=TEST_USER_EMAIL,
        request=PublishMarketplaceAutomationRequest(
            automation_id=source.automation_id,
            title="Complete workflow",
            short_description="Complete",
            full_description="Complete workflow",
            tags=[],
            included_node_ids=[nodes[0].node_id],
            included_edge_ids=[],
            included_skill_ids=[],
            import_inputs=[],
            status=MarketplaceAutomationStatus.PUBLISHED,
        ),
    )

    template = AutomationMarketplaceRepository().find_by_id(published.template_id)

    assert template is not None
    assert {node.node_id for node in template.nodes} == {node.node_id for node in nodes}
    assert {edge.edge_id for edge in template.edges} == {edge.edge_id for edge in edges}


def test_automation_marketplace_import_session_persists_with_ttl(dynamodb_table):
    del dynamodb_table
    template = AutomationMarketplaceRepository().save(
        MarketplaceAutomationTemplate(
            title="Session workflow",
            short_description="Session",
            full_description="Session workflow",
            automation_title="Session workflow",
            status=MarketplaceAutomationStatus.PUBLISHED,
        )
    )

    session = _service().save_import_session(
        template_id=template.template_id,
        user_email=TEST_USER_EMAIL,
        request=SaveMarketplaceAutomationImportSessionRequest(
            title="Configured workflow",
            description="Configured description",
        ),
    )

    saved = AutomationMarketplaceRepository().find_import_session(
        owner_email=TEST_USER_EMAIL,
        session_id=session.session_id,
    )

    assert saved is not None
    assert saved.title == "Configured workflow"
    assert saved.description == "Configured description"
    assert saved.ttl > int(datetime.now(timezone.utc).timestamp())


def test_automation_marketplace_import_uses_saved_session_values(dynamodb_table):
    del dynamodb_table
    automation_repo = AutomationRepository()
    service = _service(automation_repo)
    source, nodes, edges = _source_automation_with_graph(automation_repo)

    published = service.publish_automation(
        user_email=TEST_USER_EMAIL,
        request=PublishMarketplaceAutomationRequest(
            automation_id=source.automation_id,
            title="Reusable workflow",
            short_description="Reusable",
            full_description="Reusable workflow",
            tags=[],
            included_node_ids=[node.node_id for node in nodes],
            included_edge_ids=[edge.edge_id for edge in edges],
            included_skill_ids=[],
            import_inputs=[],
            status=MarketplaceAutomationStatus.PUBLISHED,
        ),
    )
    session = service.save_import_session(
        template_id=published.template_id,
        user_email=TEST_USER_EMAIL,
        request=SaveMarketplaceAutomationImportSessionRequest(
            title="Imported from saved session",
            description="Saved while configuring.",
        ),
    )

    imported = service.import_automation(
        template_id=published.template_id,
        user_email=TEST_USER_EMAIL,
        request=ImportMarketplaceAutomationRequest(session_id=session.session_id),
    )

    saved_automation = automation_repo.find_automation_by_id(imported.automation_id, TEST_USER_EMAIL)
    cleared_session = AutomationMarketplaceRepository().find_import_session(
        owner_email=TEST_USER_EMAIL,
        session_id=session.session_id,
    )

    assert imported.title == "Imported from saved session"
    assert saved_automation is not None
    assert saved_automation.description == "Saved while configuring."
    assert cleared_session is None


def test_automation_marketplace_import_does_not_require_config_for_empty_skill_form(dynamodb_table):
    del dynamodb_table
    automation_repo = AutomationRepository()
    service = _service(automation_repo)
    source, nodes, edges = _source_automation_with_graph(automation_repo)
    template = AutomationMarketplaceRepository().save(
        MarketplaceAutomationTemplate(
            title="Gmail workflow",
            short_description="Gmail",
            full_description="Gmail workflow",
            automation_title=source.title,
            nodes=[
                MarketplaceAutomationNodeTemplate(
                    node_id=node.node_id,
                    type=node.type,
                    name=node.name,
                    description=node.description,
                    position=node.position,
                    config=node.config,
                )
                for node in nodes
            ],
            edges=[
                MarketplaceAutomationEdgeTemplate(
                    edge_id=edge.edge_id,
                    source_node_id=edge.source_node_id,
                    target_node_id=edge.target_node_id,
                    label=edge.label,
                    condition=edge.condition,
                )
                for edge in edges
            ],
            skills=[
                MarketplaceAutomationSkillTemplate(
                    template_skill_key="google_mail",
                    skill_id="google_mail",
                    display_name="Gmail",
                    required=True,
                    enabled_on_import=False,
                )
            ],
            status=MarketplaceAutomationStatus.PUBLISHED,
        )
    )

    imported = service.import_automation(
        template_id=template.template_id,
        user_email=TEST_USER_EMAIL,
        request=ImportMarketplaceAutomationRequest(title="Imported Gmail workflow"),
    )

    skills = automation_repo.list_skills(imported.automation_id)
    assert imported.title == "Imported Gmail workflow"
    assert len(skills) == 1
    assert skills[0].skill_id == "google_mail"
    assert skills[0].enabled is False


def test_automation_marketplace_republish_creates_new_version(dynamodb_table):
    del dynamodb_table
    automation_repo = AutomationRepository()
    service = _service(automation_repo)
    source, nodes, edges = _source_automation_with_graph(automation_repo)
    payload = {
        "automation_id": source.automation_id,
        "title": "Versioned workflow",
        "short_description": "One",
        "full_description": "One",
        "tags": [],
        "included_node_ids": [node.node_id for node in nodes],
        "included_edge_ids": [edge.edge_id for edge in edges],
        "included_skill_ids": [],
        "import_inputs": [],
        "status": MarketplaceAutomationStatus.PUBLISHED,
    }

    first = service.publish_automation(user_email=TEST_USER_EMAIL, request=PublishMarketplaceAutomationRequest(**payload))
    second = service.publish_automation(
        user_email=TEST_USER_EMAIL,
        request=PublishMarketplaceAutomationRequest(**{**payload, "short_description": "Two", "full_description": "Two"}),
    )

    assert first.template_version == 1
    assert second.template_version == 2
    assert first.template_id != second.template_id


def test_automation_marketplace_rejects_publisher_owned_agent_id(dynamodb_table):
    del dynamodb_table
    automation_repo = AutomationRepository()
    service = _service(automation_repo)
    automation = automation_repo.save_automation(Automation(title="Unsafe workflow", created_by=TEST_USER_EMAIL))
    start = AutomationNode(
        automation_id=automation.automation_id,
        node_id="start",
        type=AutomationNodeType.START,
        name="Start",
    )
    action = AutomationNode(
        automation_id=automation.automation_id,
        node_id="agent-action",
        type=AutomationNodeType.ACTION,
        name="Invoke publisher agent",
        config={
            "action_type": "invoke_agent",
            "agent_id": "publisher-agent-id",
            "prompt_template": "Run this.",
        },
    )
    final = AutomationNode(
        automation_id=automation.automation_id,
        node_id="final",
        type=AutomationNodeType.FINAL,
        name="Done",
    )
    edge_one = AutomationEdge(
        automation_id=automation.automation_id,
        edge_id="start-action",
        source_node_id=start.node_id,
        target_node_id=action.node_id,
    )
    edge_two = AutomationEdge(
        automation_id=automation.automation_id,
        edge_id="action-final",
        source_node_id=action.node_id,
        target_node_id=final.node_id,
    )
    automation_repo.save_graph(automation.automation_id, [start, action, final], [edge_one, edge_two], [])

    with pytest.raises(ValueError, match="import input placeholder"):
        service.publish_automation(
            user_email=TEST_USER_EMAIL,
            request=PublishMarketplaceAutomationRequest(
                automation_id=automation.automation_id,
                title="Unsafe workflow",
                short_description="Unsafe",
                full_description="Unsafe",
                tags=[],
                included_node_ids=[start.node_id, action.node_id, final.node_id],
                included_edge_ids=[edge_one.edge_id, edge_two.edge_id],
                included_skill_ids=[],
                import_inputs=[],
                status=MarketplaceAutomationStatus.PUBLISHED,
            ),
        )


def test_automation_marketplace_import_plan_hydrates_agent_options(dynamodb_table):
    del dynamodb_table
    AgentRepository().save(
        Agent(
            agent_name="Research Agent",
            agent_architecture="krishna-mini",
            agent_provider="Bedrock",
            agent_persona="Research.",
            created_by=TEST_USER_EMAIL,
        )
    )
    template = AutomationMarketplaceRepository().save(
        MarketplaceAutomationTemplate(
            title="Invoke Agent Workflow",
            short_description="Invoke an agent.",
            full_description="Invoke an agent.",
            automation_title="Invoke Agent Workflow",
            status=MarketplaceAutomationStatus.PUBLISHED,
            skills=[
                MarketplaceAutomationSkillTemplate(
                    template_skill_key="agent_invocation",
                    skill_id="agent_invocation",
                    display_name="Invoke Agent",
                    required=True,
                )
            ],
        )
    )

    plan = _service().get_import_plan(
        template_id=template.template_id,
        user_email=TEST_USER_EMAIL,
    )

    target_agent = plan.skill_forms[0].form.form_inputs[0]
    assert target_agent.name == "target_agent_id"
    assert target_agent.options
    assert target_agent.options[0].label == "Research Agent"
