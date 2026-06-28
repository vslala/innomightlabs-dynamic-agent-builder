from __future__ import annotations

import json
from typing import Any

from src.agents.architectures import get_agent_architecture
from src.agents.repository import AgentRepository
from src.conversations.models import Conversation
from src.messages.repositories import get_message_repository


async def generate_report_html_with_agent(
    *,
    agent_id: str,
    owner_email: str,
    actor_email: str,
    actor_id: str,
    prompt: str,
    agent_repository: AgentRepository | None = None,
) -> str:
    repo = agent_repository or AgentRepository()
    agent = repo.find_agent_by_id(agent_id, owner_email)
    if not agent:
        raise ValueError("Report agent not found")
    if agent.agent_architecture != "krishna-mini":
        raise ValueError("Report agent must use krishna-mini architecture")

    conversation = Conversation(
        agent_id=agent.agent_id,
        title="Temporary report generation",
        description="In-memory report generation session",
        created_by=owner_email,
    )
    architecture = get_agent_architecture(
        agent.agent_architecture,
        message_repository=get_message_repository("in_memory"),
    )
    result = await architecture.handle_message_buffered(
        agent=agent,
        conversation=conversation,
        user_message=prompt,
        owner_email=owner_email,
        actor_email=actor_email,
        actor_id=actor_id,
    )
    if not result.success:
        raise ValueError(result.error or "Report generation failed")
    return result.response_text


def build_report_prompt(*, report_data: dict[str, Any]) -> str:
    scope = report_data["report_scope"]
    sections = (
        "overview, player performance, lane and macro insights, combat highlights, "
        "objective control, mistakes, recommendations, and next-game checklist"
        if scope == "single_match"
        else "trend overview, champion and role patterns, consistency, recurring strengths, "
        "recurring mistakes, objective trends, improvement priorities, and practice checklist"
    )
    data_json = json.dumps(report_data, ensure_ascii=True, separators=(",", ":"))
    return f"""Generate a complete, detailed League of Legends HTML report from the JSON data below.

Output requirements:
- Return exactly one complete HTML5 document, starting with <!doctype html> and ending with </html>.
- Use HTML5 and CSS only. Put all CSS inside one inline <style> tag.
- Do not use JavaScript, external images, external fonts, external stylesheets, iframes, or network resources.
- Make the report visually polished, readable, and consistent with a game analytics product.
- Include these sections: {sections}.
- Explain the insights in clear, human language and include concrete improvement advice.
- Use only the supplied data. Do not invent match ids, player stats, ranks, or champion facts.

Report data JSON:
{data_json}
"""
