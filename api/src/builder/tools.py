"""Ada's tools: read the blueprint book, ask with forms, plan a blueprint, apply it once approved, and report how
the build is doing.

The book's index is always in Ada's prompt; `open_pages` puts whole pages there for a few turns, and issues from a
plan open the pages that explain them.

Forms come from the Interactive Forms module (`lead_capture`), so the chat renders them like any other
skill's forms. The blueprint tools keep the draft on the BuilderSession, which Ada's prompt shows every
turn, so a plan made in one turn can be approved and applied in the next.
"""

import json
from typing import Any, Callable, Optional

from src.agents.book import Book, open_pages
from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime import BoundTool, ToolCategory, ToolRegistry, ToolSpec
from src.blueprints.approval import approval_form, approves, plan_id_for
from src.blueprints.book import blueprint_book, page_for_issue
from src.blueprints.executor import apply_blueprint, apply_rate_limit
from src.blueprints.export import export_agent, with_ids
from src.blueprints.issues import BlueprintInvalid, BlueprintIssue
from src.blueprints.planner import plan_blueprint
from src.blueprints.repository import DeploymentRepository
from src.blueprints.validator import validate_blueprint
from src.builder.canvas import drawing_for, save_blueprint_canvas
from src.builder.connections import connect_request, missing_connections
from src.builder.models import BuilderSession, PendingInput
from src.builder.skill_inputs import SkillInput, covers, fill_inputs, input_form, missing_inputs
from src.builder.repository import BuilderSessionRepository
from src.agents.repository import AgentRepository
from src.apikeys.repository import ApiKeyRepository
from src.config import settings
from src.skills.repository import AgentSkillRepository
from src.knowledge.repository import AgentKnowledgeBaseRepository, CrawlJobRepository
from src.messages.repositories import MessageRepository, get_message_repository
from src.rate_limits.limiter import RateLimiter
from src.skills.lead_capture.actions import render_custom_form
from src.skills.registry import get_skill_registry

#: Pages one open_pages call may open, so a turn can't fill the prompt with the whole book.
MAX_PAGES_PER_OPEN = 6

DASHBOARD_PATHS = {"Agent": "/dashboard/agents/{id}", "KnowledgeBase": "/dashboard/knowledge-bases/{id}"}


def _forms_schema() -> dict[str, Any]:
    """The Interactive Forms module's own schema for a custom form, so there's one definition of it."""
    loaded = get_skill_registry().get("lead_capture")
    action = loaded.manifest.find_action("render_custom_form") if loaded else None
    if action is None:
        raise RuntimeError("Ada needs the Interactive Forms skill (lead_capture) to be installed on the platform")
    return action.input_schema


BLUEPRINT_INPUT = {
    "type": "object",
    "properties": {
        "yaml": {
            "type": "string",
            "description": "The whole blueprint as YAML text. Leave it out to plan the current draft as it is.",
        },
        "params": {
            "type": "object",
            "description": "Values for the blueprint's params, by param name. Leave it out to keep the draft's.",
        },
    },
}


def builder_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "open_pages",
            "description": (
                "Open pages of the blueprint book by their ids from the index, such as kind/Agent or "
                "skill/lead_capture. The pages appear in your prompt under <open_pages> and stay for a few turns. "
                "Open a page before writing the resource or skill it describes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": MAX_PAGES_PER_OPEN,
                        "description": "Page ids from the book index.",
                    },
                },
                "required": ["page_ids"],
            },
        },
        {
            "name": "search_book",
            "description": (
                "Search the blueprint book when the index doesn't make clear which page covers what the person "
                "wants. Returns page ids to open."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What the person wants, in a few words."}},
                "required": ["query"],
            },
        },
        {
            "name": "show_form",
            "description": (
                "Show the person a form under your message: choices to brainstorm ideas, or fields to collect "
                "requirements. Their answers come back as their next message."
            ),
            "parameters": _forms_schema(),
        },
        {
            "name": "plan_blueprint",
            "description": (
                "Save the blueprint as the current draft, validate it and plan it against the person's account. "
                "If a skill needs settings from the person, the system asks them in a form first. Returns issues "
                "to fix, blockers to explain, a skill form the person is filling in, or a plan with an approval "
                "form for the person."
            ),
            "parameters": BLUEPRINT_INPUT,
        },
        {
            "name": "apply_blueprint",
            "description": (
                "Build the planned draft. Only works after the person chose 'Apply this plan' in the plan's "
                "approval form."
            ),
            "parameters": {
                "type": "object",
                "properties": {"plan_id": {"type": "string", "description": "The plan_id from plan_blueprint."}},
                "required": ["plan_id"],
            },
        },
        {
            "name": "list_my_agents",
            "description": (
                "The person's existing agents: id, name, description, and what they use. Call it when they want "
                "to change or add to something they already have, to find which agent they mean."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "load_agent",
            "description": (
                "Make an existing agent the current draft: the agent, its knowledge bases, skills and widget keys "
                "written as a blueprint with their ids. Change only what the person asks, then plan it; applying "
                "updates those resources instead of creating new ones."
            ),
            "parameters": {
                "type": "object",
                "properties": {"agent_id": {"type": "string", "description": "An id from list_my_agents."}},
                "required": ["agent_id"],
            },
        },
        {
            "name": "get_build_status",
            "description": "How the last build is doing: whether the website crawl has finished, and where to try things.",
            "parameters": {"type": "object", "properties": {}},
        },
    ]


class BuilderTools:
    def __init__(
        self,
        sessions: Optional[BuilderSessionRepository] = None,
        messages: Optional[MessageRepository] = None,
        book: Optional[Callable[[], Book]] = None,
    ) -> None:
        self.sessions = sessions or BuilderSessionRepository()
        self.messages = messages or get_message_repository()
        self.book = book or blueprint_book

    def _session(self, state: AgentTurnState) -> BuilderSession:
        session = self.sessions.find(state.owner_email, state.conversation_id)
        if session is None:
            raise ValueError("This conversation isn't a building session.")
        return session

    async def open_book_pages(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        session = self._session(state)
        page_ids = tool_input.get("page_ids")
        if isinstance(page_ids, str):
            page_ids = [page_ids]
        if not isinstance(page_ids, list) or not page_ids:
            raise ValueError("open_pages needs `page_ids`: a list of ids from the book index.")
        opened = self.book().open(str(page_id) for page_id in page_ids[:MAX_PAGES_PER_OPEN])
        session.opened_pages = open_pages(session.opened_pages, [page.id for page in opened.pages], session.turn)
        self.sessions.save(session)
        return json.dumps({
            "opened": [page.id for page in opened.pages],
            **({"unknown": opened.unknown} if opened.unknown else {}),
            **({"did_you_mean": opened.suggestions} if opened.suggestions else {}),
            "next": (
                f"The opened pages are in your prompt under <open_pages> for the next "
                f"{settings.ada_page_retention_turns} turns, this one included."
            ),
        })

    async def search_book(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        query = str(tool_input.get("query") or "").strip()
        if not query:
            raise ValueError("search_book needs a `query`.")
        pages = self.book().search(query)
        return json.dumps({
            "pages": [
                {"id": page.id, "title": page.title, "summary": page.summary, **({"note": page.note} if page.note else {})}
                for page in pages
            ],
            "next": "Open the pages you need with open_pages." if pages else "Nothing matches; check the book index.",
        })

    def _pointing_at_pages(
        self, session: BuilderSession, issues: list[BlueprintIssue], yaml: str
    ) -> list[dict[str, Any]]:
        """Each issue with the page that explains it. Those pages are opened, so the fix has them to hand."""
        book = self.book()
        described, pages = [], []
        for issue in issues:
            row = issue.model_dump(exclude_none=True)
            page_id = page_for_issue(issue.path, yaml, book)
            if page_id:
                row["page"] = page_id
                pages.append(page_id)
            described.append(row)
        session.opened_pages = open_pages(session.opened_pages, pages, session.turn)
        return described

    async def show_form(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        context = {"agent_id": state.agent_id, "conversation_id": state.conversation_id}
        return json.dumps(render_custom_form(arguments=tool_input, config={}, context=context))

    async def plan(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        session = self._session(state)
        yaml = tool_input.get("yaml") or session.draft_yaml
        params = tool_input["params"] if isinstance(tool_input.get("params"), dict) else session.draft_params
        if not isinstance(yaml, str) or not yaml.strip():
            raise ValueError("plan_blueprint needs `yaml`, the whole blueprint: there's no draft yet.")
        # The person's answers to earlier skill forms, whatever Ada's YAML says.
        yaml = fill_inputs(yaml, session.skill_inputs)
        session.draft_yaml, session.draft_params, session.plan_id = yaml, params, None
        missing = missing_inputs(yaml, params)
        if session.pending_input and all(item.key != session.pending_input.key for item in missing):
            # The form it waited on isn't needed any more (the draft changed, or the setting is Ada's to write).
            session.pending_input = None

        try:
            validated = validate_blueprint(yaml, params)
        except BlueprintInvalid as e:
            # Settings the person hasn't given yet aren't Ada's to fix; anything else is, before they're asked.
            other = [issue for issue in e.issues if not covers(missing, issue.path)]
            if not other and missing:
                return self._ask_for_settings(session, missing, state)
            issues = self._pointing_at_pages(session, other, yaml)
            self.sessions.save(session)
            return json.dumps({
                "ok": False,
                "issues": issues,
                "next": (
                    "Fix every issue in the YAML and call plan_blueprint again. Each issue's `page` is now open in "
                    "your prompt. Don't show these to the person."
                ),
            })

        # Accounts first: the person signs in, then gives any settings, then sees the plan.
        connections = missing_connections(yaml, state.owner_email)
        if connections:
            self.sessions.save(session)
            need = connections[0]
            return json.dumps({
                **connect_request(need, state.conversation_id),
                "ok": False,
                "needs_connection": {"provider": need.title, "connections_left": len(connections)},
                "next": (
                    f"The system is asking the person to connect {need.title} with a card under your message. "
                    "Say one short line about what it gives the agent, and stop. When they say it's connected, "
                    "call plan_blueprint with no arguments."
                ),
            })
        if missing:
            return self._ask_for_settings(session, missing, state)
        session.pending_input = None

        plan = plan_blueprint(validated, state.owner_email)
        steps = [step.model_dump() for step in plan.steps]
        if not plan.ok:
            blockers = self._pointing_at_pages(session, plan.blockers, yaml)
            self.sessions.save(session)
            return json.dumps({
                "ok": False,
                "steps": steps,
                "blockers": blockers,
                "next": "Explain what blocks this in plain words and how to fix it, or change the draft and plan again.",
            })

        if not plan.changes_anything:
            self.sessions.save(session)
            return json.dumps({
                "ok": True,
                "nothing_to_change": True,
                "steps": steps,
                "next": "Everything already matches this draft. Tell the person there's nothing to change; don't ask them to approve.",
            })

        session.plan_id = plan_id_for(yaml, params)
        self.sessions.save(session)
        context = {"agent_id": state.agent_id, "conversation_id": state.conversation_id}
        canvas = save_blueprint_canvas(drawing_for(validated, plan, stage="plan", plan_id=session.plan_id), state)
        return json.dumps({
            **approval_form(session.plan_id, plan, context),
            **({"canvas": canvas} if canvas else {}),
            "ok": True,
            "plan_id": session.plan_id,
            "steps": steps,
            **({"removals": plan.removals} if plan.removals else {}),
            "next": (
                "The person can see the blueprint drawing (with the steps and the YAML) and the approval form "
                "under your message. Describe what you'll build in two or three plain sentences; don't repeat "
                "the steps. Nothing is built until they choose 'Apply this plan'."
                + (" This plan also removes things, which can't be undone: name each one plainly so they know "
                   "before they approve." if plan.removals else "")
            ),
        })

    def _ask_for_settings(self, session: BuilderSession, missing: list[SkillInput], state: AgentTurnState) -> str:
        """The form for the first skill still missing settings. One skill at a time, in draft order."""
        item = missing[0]
        pending = session.pending_input
        error = pending.error if pending is not None and pending.key == item.key else None
        session.pending_input = PendingInput(key=item.key, label=item.label)
        self.sessions.save(session)
        context = {"agent_id": state.agent_id, "conversation_id": state.conversation_id}
        return json.dumps({
            **input_form(item, session.draft_yaml or "", session.draft_params, state.owner_email, context, error),
            "ok": False,
            "needs_input": {"skill": item.skill_name, "agent": item.agent_name, "skills_left": len(missing)},
            "next": (
                f"The system is asking the person for {item.skill_name}'s settings in a form under your message. "
                "Say one short line, such as what the skill will do for them. Don't ask for these settings or "
                "fill them in yourself. When their message is that form, call plan_blueprint with no arguments."
            ),
        })

    def _latest_user_message(self, conversation_id: str) -> str:
        messages, _, _ = self.messages.find_by_conversation_newest_first(conversation_id, limit=10)
        return next((message.content for message in messages if message.role == "user"), "")

    async def apply(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        session = self._session(state)
        plan_id = str(tool_input.get("plan_id") or "").strip()
        if not session.plan_id or plan_id != session.plan_id or not session.draft_yaml:
            return json.dumps({"applied": False, "reason": "That isn't the current plan. Plan the draft again."})
        if not approves(self._latest_user_message(state.conversation_id), plan_id):
            return json.dumps({
                "applied": False,
                "reason": "The person hasn't approved this plan. Wait until they choose 'Apply this plan' in its form.",
            })

        try:
            validated = validate_blueprint(session.draft_yaml, session.draft_params)
        except BlueprintInvalid as e:
            return json.dumps({"applied": False, "issues": [issue.model_dump(exclude_none=True) for issue in e.issues]})
        plan = plan_blueprint(validated, state.owner_email)
        if not plan.ok:
            # The account changed since the plan: a name was taken, or a limit was reached.
            return json.dumps({"applied": False, "blockers": [issue.model_dump(exclude_none=True) for issue in plan.blockers]})

        limiter = RateLimiter(apply_rate_limit())
        decision = limiter.acquire(state.owner_email)
        if not decision.allowed:
            return json.dumps({"applied": False, "reason": "Too many builds in the last hour. Try again later."})
        deployment = apply_blueprint(validated, plan, state.owner_email)
        if deployment.status != "applied":
            limiter.release(decision)
            return json.dumps({
                "applied": False,
                "status": deployment.status.value,
                "error": deployment.error,
                **({"removed": deployment.removed} if deployment.removed else {}),
            })

        session.deployment_id, session.plan_id = deployment.deployment_id, None
        # The next change in this conversation updates what was just built, rather than building it again.
        session.draft_yaml = with_ids(session.draft_yaml, {name: res.id for name, res in deployment.resources.items()})
        self.sessions.save(session)
        canvas = save_blueprint_canvas(
            drawing_for(validated, plan, stage="built", plan_id=plan_id, deployment=deployment), state
        )
        return json.dumps({
            **({"canvas": canvas} if canvas else {}),
            "applied": True,
            **({"removed": deployment.removed} if deployment.removed else {}),
            "outputs": {name: output.model_dump(exclude_none=True) for name, output in deployment.outputs.items()},
            "resources": self._resources(deployment.resources),
            "next": (
                "Tell the person what you built, give each output with its description, and walk them through "
                "testing it. Call get_build_status if they ask whether it's ready."
            ),
        })

    async def list_agents(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        agents = []
        for agent in AgentRepository().find_all_by_created_by(state.owner_email):
            agents.append({
                "agent_id": agent.agent_id,
                "name": agent.agent_name,
                "description": agent.agent_description or "",
                "knowledge_bases": len(AgentKnowledgeBaseRepository().find_kbs_for_agent(agent.agent_id)),
                "skills": [skill.skill_id for skill in AgentSkillRepository().list_by_agent(agent.agent_id)],
                "widget_keys": len(ApiKeyRepository().find_all_by_agent(agent.agent_id)),
            })
        return json.dumps({"agents": agents})

    async def load_agent(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        session = self._session(state)
        agent_id = str(tool_input.get("agent_id") or "").strip()
        yaml = export_agent(agent_id, state.owner_email)
        if yaml is None:
            return json.dumps({"loaded": False, "reason": "There's no agent with that id. Call list_my_agents."})
        session.draft_yaml, session.draft_params, session.plan_id = yaml, {}, None
        # Answers to skill forms belonged to the old draft's resources.
        session.skill_inputs, session.pending_input = {}, None
        self.sessions.save(session)
        return json.dumps({
            "loaded": True,
            "next": (
                "The agent is now the current draft (see your prompt). Keep every `id`. Change only what the person "
                "asked for, add new resources without an id, then call plan_blueprint with the whole YAML."
            ),
        })

    async def build_status(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        session = self._session(state)
        deployment = (
            DeploymentRepository().find_by_id(state.owner_email, session.deployment_id) if session.deployment_id else None
        )
        if deployment is None:
            return json.dumps({"built": False, "reason": "Nothing has been built in this conversation yet."})
        crawls = []
        for name, resource in deployment.resources.items():
            job_id = resource.attributes.get("crawl_job_id")
            job = CrawlJobRepository().find_by_id(job_id, resource.id) if job_id else None
            if job:
                crawls.append({
                    "knowledge_base": name,
                    "status": job.status.value,
                    "pages_read": job.progress.successful_urls,
                    "pages_found": job.progress.discovered_urls,
                })
        return json.dumps({
            "built": True,
            "status": deployment.status.value,
            "crawls": crawls,
            "resources": self._resources(deployment.resources),
            "outputs": {name: output.model_dump(exclude_none=True) for name, output in deployment.outputs.items()},
        })

    @staticmethod
    def _resources(resources: dict[str, Any]) -> dict[str, dict[str, str]]:
        return {
            name: {
                "kind": resource.kind,
                "id": resource.id,
                **({"dashboard_url": settings.frontend_url + DASHBOARD_PATHS[resource.kind].format(id=resource.id)}
                   if resource.kind in DASHBOARD_PATHS else {}),
            }
            for name, resource in resources.items()
        }


def build_builder_tool_registry(tools: Optional[BuilderTools] = None) -> ToolRegistry:
    tools = tools or BuilderTools()
    open_book, search, show_form, plan, apply, list_agents, load_agent, status = builder_tool_definitions()
    return ToolRegistry([
        # Opening pages changes the pages Ada's prompt shows.
        BoundTool(ToolSpec(open_book, ToolCategory.BUILDER, mutates_prompt_context=True), tools.open_book_pages),
        BoundTool(ToolSpec(search, ToolCategory.BUILDER), tools.search_book),
        BoundTool(ToolSpec(show_form, ToolCategory.BUILDER), tools.show_form),
        # Planning and applying change the draft that Ada's prompt shows.
        BoundTool(ToolSpec(plan, ToolCategory.BUILDER, mutates_prompt_context=True), tools.plan),
        BoundTool(ToolSpec(apply, ToolCategory.BUILDER, mutates_prompt_context=True), tools.apply),
        BoundTool(ToolSpec(list_agents, ToolCategory.BUILDER), tools.list_agents),
        # Loading replaces the draft the prompt shows.
        BoundTool(ToolSpec(load_agent, ToolCategory.BUILDER, mutates_prompt_context=True), tools.load_agent),
        BoundTool(ToolSpec(status, ToolCategory.BUILDER), tools.build_status),
    ])


__all__ = ["BuilderTools", "build_builder_tool_registry", "builder_tool_definitions"]
