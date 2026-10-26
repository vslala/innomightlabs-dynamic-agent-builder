"""What an agent can do that asks its owner first: its skills' consent actions and its MCP connections' asking tools.

What the owner can always allow on the agent's pages, and tick for an automation's agent step.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.connectors.mcp.service import MCPConnectorService
from src.skills.service import SkillRuntimeService


@dataclass(frozen=True)
class ConsentAction:
    key: str
    title: str
    #: Where it comes from, as the agent's pages name it: the skill, or the MCP connection.
    source: str
    warning: str | None = None
    #: For a skill action, so a blueprint's `skill.action` can name it.
    skill_id: str | None = None
    action: str | None = None


def consent_actions(
    agent_id: str,
    account_id: str,
    *,
    skill_runtime: SkillRuntimeService | None = None,
    mcp: MCPConnectorService | None = None,
) -> list[ConsentAction]:
    found = [
        ConsentAction(
            key=key,
            title=action.consent.title,
            source=installed.skill_name or installed.skill_id,
            warning=action.consent.warning,
            skill_id=installed.skill_id,
            action=action.name,
        )
        for key, installed, action in (skill_runtime or SkillRuntimeService()).consent_actions(agent_id)
        if action.consent is not None
    ]
    found += [
        ConsentAction(key=key, title=title, source=connection)
        for key, title, connection in (mcp or MCPConnectorService()).consent_tools(account_id=account_id, agent_id=agent_id)
    ]
    return found
