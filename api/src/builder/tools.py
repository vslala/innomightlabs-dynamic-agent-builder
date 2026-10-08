"""Ada's tools: ask with forms, plan a blueprint, apply it once approved, and report how the build is doing.

Forms come from the Interactive Forms module (`lead_capture`), so the chat renders them like any other
skill's forms. The blueprint tools keep the draft on the BuilderSession, which Ada's prompt shows every
turn, so a plan made in one turn can be approved and applied in the next.
"""

import json
from typing import Any, Optional

from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime import BoundTool, ToolCategory, ToolRegistry, ToolSpec
from src.blueprints.approval import approval_form, approves, plan_id_for
from src.blueprints.executor import apply_blueprint, apply_rate_limit
from src.blueprints.issues import BlueprintInvalid
from src.blueprints.planner import plan_blueprint
from src.blueprints.repository import DeploymentRepository
from src.blueprints.validator import validate_blueprint
from src.builder.models import BuilderSession
from src.builder.repository import BuilderSessionRepository
from src.config import settings
from src.knowledge.repository import CrawlJobRepository
from src.messages.repositories import MessageRepository, get_message_repository
from src.rate_limits.limiter import RateLimiter
from src.skills.lead_capture.actions import render_custom_form
from src.skills.registry import get_skill_registry

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
        "yaml": {"type": "string", "description": "The whole blueprint as YAML text."},
        "params": {"type": "object", "description": "Values for the blueprint's params, by param name."},
    },
    "required": ["yaml", "params"],
}


def builder_tool_definitions() -> list[dict[str, Any]]:
    return [
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
                "Returns issues to fix, blockers to explain, or a plan with an approval form for the person."
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
    ) -> None:
        self.sessions = sessions or BuilderSessionRepository()
        self.messages = messages or get_message_repository()

    def _session(self, state: AgentTurnState) -> BuilderSession:
        session = self.sessions.find(state.owner_email, state.conversation_id)
        if session is None:
            raise ValueError("This conversation isn't a building session.")
        return session

    async def show_form(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        context = {"agent_id": state.agent_id, "conversation_id": state.conversation_id}
        return json.dumps(render_custom_form(arguments=tool_input, config={}, context=context))

    async def plan(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        session = self._session(state)
        yaml = tool_input.get("yaml")
        params = tool_input.get("params") or {}
        if not isinstance(yaml, str) or not yaml.strip() or not isinstance(params, dict):
            raise ValueError("plan_blueprint needs `yaml` (the whole blueprint) and `params` (an object).")
        session.draft_yaml, session.draft_params, session.plan_id = yaml, params, None

        try:
            validated = validate_blueprint(yaml, params)
        except BlueprintInvalid as e:
            self.sessions.save(session)
            return json.dumps({
                "ok": False,
                "issues": [issue.model_dump(exclude_none=True) for issue in e.issues],
                "next": "Fix every issue in the YAML and call plan_blueprint again. Don't show these to the person.",
            })

        plan = plan_blueprint(validated, state.owner_email)
        steps = [step.model_dump() for step in plan.steps]
        if not plan.ok:
            self.sessions.save(session)
            return json.dumps({
                "ok": False,
                "steps": steps,
                "blockers": [issue.model_dump(exclude_none=True) for issue in plan.blockers],
                "next": "Explain what blocks this in plain words and how to fix it, or change the draft and plan again.",
            })

        session.plan_id = plan_id_for(yaml, params)
        self.sessions.save(session)
        context = {"agent_id": state.agent_id, "conversation_id": state.conversation_id}
        return json.dumps({
            **approval_form(session.plan_id, plan, context),
            "ok": True,
            "plan_id": session.plan_id,
            "steps": steps,
            "next": (
                "Describe what you'll build in a few plain sentences. The approval form appears under your "
                "message. Nothing is built until they choose 'Apply this plan'."
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
        deployment = apply_blueprint(validated, state.owner_email)
        if deployment.status != "applied":
            limiter.release(decision)
            return json.dumps({"applied": False, "status": deployment.status.value, "error": deployment.error})

        session.deployment_id, session.plan_id = deployment.deployment_id, None
        self.sessions.save(session)
        return json.dumps({
            "applied": True,
            "outputs": {name: output.model_dump(exclude_none=True) for name, output in deployment.outputs.items()},
            "resources": self._resources(deployment.resources),
            "next": (
                "Tell the person what you built, give each output with its description, and walk them through "
                "testing it. Call get_build_status if they ask whether it's ready."
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
    show_form, plan, apply, status = builder_tool_definitions()
    return ToolRegistry([
        BoundTool(ToolSpec(show_form, ToolCategory.BUILDER), tools.show_form),
        # Planning and applying change the draft that Ada's prompt shows.
        BoundTool(ToolSpec(plan, ToolCategory.BUILDER, mutates_prompt_context=True), tools.plan),
        BoundTool(ToolSpec(apply, ToolCategory.BUILDER, mutates_prompt_context=True), tools.apply),
        BoundTool(ToolSpec(status, ToolCategory.BUILDER), tools.build_status),
    ])


__all__ = ["BuilderTools", "build_builder_tool_registry", "builder_tool_definitions"]
