"""An existing agent written out as a blueprint, so it can be changed and applied again.

Every resource carries its `id`, so applying the exported blueprint as it is changes nothing, and applying an
edited one updates the same agent, knowledge bases and widget keys instead of creating new ones.
"""

import re
from typing import Any, Optional

import yaml  # type: ignore[import-untyped,unused-ignore]

from src.agents.repository import AgentRepository
from src.apikeys.repository import ApiKeyRepository
from src.blueprints.kinds.knowledge_base import last_crawl
from src.blueprints.skills_schema import skill_variants
from src.blueprints.spec import API_VERSION
from src.knowledge.models import KnowledgeBaseStatus
from src.knowledge.repository import AgentKnowledgeBaseRepository, KnowledgeBaseRepository
from src.skills.models import ActorKind
from src.skills.repository import AgentSkillRepository


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "agent"


def _numbered(base: str, index: int) -> str:
    return base if index == 0 else f"{base}_{index + 1}"


def export_agent(agent_id: str, user_email: str) -> Optional[str]:
    """The agent as blueprint YAML, or None if it isn't the person's.

    Skills a blueprint can't describe (ones that need a secret to install) are left out; applying never removes
    a skill, so they stay on the agent as they are.
    """
    agent = AgentRepository().find_agent_by_id(agent_id, user_email)
    if agent is None:
        return None

    resources: dict[str, Any] = {}
    kb_names = []
    kb_repo = KnowledgeBaseRepository()
    links = AgentKnowledgeBaseRepository().find_kbs_for_agent(agent_id)
    for index, kb in enumerate(kb for link in links if (kb := kb_repo.find_by_id(link.kb_id, user_email))):
        if kb.status == KnowledgeBaseStatus.DELETED:
            continue
        name = _numbered("knowledge", index)
        kb_names.append(name)
        resource: dict[str, Any] = {"kind": "KnowledgeBase", "id": kb.kb_id, "name": kb.name}
        if kb.description:
            resource["description"] = kb.description
        crawl = last_crawl(kb.kb_id)
        if crawl:
            resource["crawl"] = crawl.model_dump()
        resources[name] = resource

    variants = skill_variants()
    skills = []
    for installed in AgentSkillRepository().list_by_agent(agent_id):
        variant = variants.get(installed.skill_id)
        if variant is None or any(
            field.name in variant.secret_fields and not field.is_optional and field.value is None
            for field in variant.skill.manifest.form
        ):
            continue
        entry: dict[str, Any] = {"id": installed.skill_id}
        config = {key: value for key, value in installed.config.items() if key in variant.config_fields}
        if config:
            entry["config"] = config
        audience = [ActorKind(kind).value for kind in installed.available_to if ActorKind(kind) != ActorKind.OWNER]
        if audience and variant.shareable:
            entry["available_to"] = audience
        if not installed.enabled:
            entry["enabled"] = False
        skills.append(entry)

    agent_resource: dict[str, Any] = {
        "kind": "Agent",
        "id": agent.agent_id,
        "name": agent.agent_name,
        "provider": agent.agent_provider,
        "instructions": agent.agent_persona,
        "session_timeout_minutes": agent.session_timeout_minutes,
    }
    if agent.agent_model:
        agent_resource["model"] = agent.agent_model
    if agent.agent_description:
        agent_resource["description"] = agent.agent_description
    if kb_names:
        agent_resource["knowledge_bases"] = kb_names
    if skills:
        agent_resource["skills"] = skills
    resources["agent"] = agent_resource

    outputs: dict[str, Any] = {"agent_id": {"description": "The agent in the dashboard.", "value": "{{ resources.agent.id }}"}}
    # A key that works on any site has no origins to write down; a blueprint never makes those, so leave it alone.
    for index, key in enumerate(key for key in ApiKeyRepository().find_all_by_agent(agent_id) if key.allowed_origins):
        name = _numbered("widget", index)
        resources[name] = {
            "kind": "WidgetKey",
            "id": key.key_id,
            "agent": "agent",
            "name": key.name,
            "allowed_origins": list(key.allowed_origins),
            "allow_guests": key.allow_guests,
        }
        outputs.setdefault("snippet", {
            "description": "Paste this before </body> on every page of your site.",
            "value": f"{{{{ resources.{name}.snippet }}}}",
        })

    document = {
        "apiVersion": API_VERSION,
        "kind": "Blueprint",
        "metadata": {
            "name": _slug(agent.agent_name),
            "title": agent.agent_name,
            **({"description": agent.agent_description} if agent.agent_description else {}),
        },
        "resources": resources,
        "outputs": outputs,
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)


def with_ids(text: str, ids: dict[str, str]) -> str:
    """The blueprint with each named resource pinned to the id it was built as, so the next apply updates it."""
    document = yaml.safe_load(text)
    for name, resource_id in ids.items():
        resource = document.get("resources", {}).get(name)
        if isinstance(resource, dict):
            # Put `id` right after `kind`, where a reader expects it.
            pinned = {"kind": resource.get("kind"), "id": resource_id}
            pinned.update({key: value for key, value in resource.items() if key not in ("kind", "id")})
            document["resources"][name] = pinned
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)
