"""Ila's tools: read the blueprint book, ask with forms, plan a blueprint, apply it once approved, and report how
the build is doing.

The book's index is always in Ila's prompt; `open_pages` puts whole pages there for a few turns, and issues from a
plan open the pages that explain them.

Forms come from the Lead Capture skill (`lead_capture`), so the chat renders them like any other
skill's forms. The blueprint tools keep the draft on the BuilderSession, which Ila's prompt shows every
turn, so a plan made in one turn can be approved and applied in the next.
"""

import json
from typing import Any, Callable, Optional

from src.agents.book import Book, open_pages
from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime import BoundTool, ToolCategory, ToolRegistry, ToolSpec
from src.blueprints.approval import approves
from src.blueprints.book import blueprint_book, page_for_issue
from src.blueprints.draft import Draft
from src.blueprints.account_pages import account_page_id, account_resource, named
from src.blueprints.export import export_agent, new_document, numbered
from src.blueprints.issues import BlueprintInvalid, BlueprintIssue
from src.blueprints.kinds import ResourceKind, kind_for
from src.blueprints.models import DeploymentStatus
from src.blueprints.kits import KitError, KitRepository, active_kit, declared, pin
from src.blueprints.repository import DeploymentRepository
from src.blueprints.service import Blocked, Deployed, Invalid, RateLimited, deploy_blueprint
from src.blueprints.validator import validate_blueprint
from src.builder.canvas import drawing_for, save_blueprint_canvas
from src.builder.models import BuilderSession
from src.builder.plan_gates import PLAN_GATES, PlanAttempt
from src.builder.requirements import REQUIREMENTS
from src.builder.repository import BuilderSessionRepository
from src.config import settings
from src.knowledge.repository import CrawlJobRepository
from src.messages.repositories import MessageRepository, get_message_repository
from src.skills.lead_capture.actions import render_custom_form
from src.skills.registry import get_skill_registry

#: Pages one open_pages call may open, so a turn can't fill the prompt with the whole book.
MAX_PAGES_PER_OPEN = 6

def _forms_schema() -> dict[str, Any]:
    """The Lead Capture skill's own schema for a custom form, so there's one definition of it."""
    loaded = get_skill_registry().get("lead_capture")
    action = loaded.manifest.find_action("render_custom_form") if loaded else None
    if action is None:
        raise RuntimeError("Ila needs the Lead Capture skill (lead_capture) to be installed on the platform")
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
                "Search the blueprint book, including what the person already has under Your account (their "
                "agents, lead forms, automations and so on, by name). Use it when the index doesn't make clear which "
                "page covers what they want, or to find one of their resources by name. Returns page ids to open."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to look for, in a few words: what the person wants, or a resource's name.",
                    },
                    "prefix": {
                        "type": "string",
                        "description": (
                            "Search only pages whose ids start with this: account/Agent for their agents, "
                            "account/ for everything they have, skill/, kind/ or recipe/. A narrow prefix is faster "
                            "and surer. With a prefix and no query, lists the pages under it."
                        ),
                    },
                },
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
            "name": "add_to_draft",
            "description": (
                "Put one of the person's resources in the draft, written as a blueprint writes it with its id, so "
                "planning changes it rather than building another. Name it by its page under Your account, such as "
                "account/LeadForm/<id>. An agent becomes the whole draft, with its knowledge, skills and widgets: "
                "what the draft held is set aside. Anything else joins what the draft holds."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The resource's page, account/<Kind>/<id>."},
                },
                "required": ["page_id"],
            },
        },
        {
            "name": "get_build_status",
            "description": "How the last build is doing: whether the website crawl has finished, and where to try things.",
            "parameters": {"type": "object", "properties": {}},
        },
    ]


def _free_name(base: str, draft: Draft) -> str:
    """`base`, or `base_2`, `base_3`... when the draft already has a resource by that name."""
    return next(name for index in range(len(draft.resources) + 1) if (name := numbered(base, index)) not in draft.resources)


def _issue(issue: BlueprintIssue) -> dict[str, Any]:
    """An issue as Ila reads it. Who owns it is the system's business: she only sees her own."""
    return issue.model_dump(exclude_none=True, exclude={"owner"})


def _not_deployed(outcome: Invalid | Blocked | RateLimited) -> dict[str, Any]:
    match outcome:
        case Invalid(issues=issues):
            return {"issues": [_issue(issue) for issue in issues]}
        case Blocked(plan=plan):
            # The account changed since the plan: a name was taken, or a limit was reached.
            return {"blockers": [_issue(issue) for issue in plan.blockers]}
        case RateLimited():
            return {"reason": "Too many builds in the last hour. Try again later."}


class BuilderTools:
    def __init__(
        self,
        sessions: Optional[BuilderSessionRepository] = None,
        messages: Optional[MessageRepository] = None,
        #: Called with `owner=` for the book with their account branch; with nothing for the reference pages alone.
        book: Optional[Callable[..., Book]] = None,
    ) -> None:
        self.sessions = sessions or BuilderSessionRepository()
        self.messages = messages or get_message_repository()
        self.book = book or blueprint_book

    def _session(self, state: AgentTurnState) -> BuilderSession:
        session = self.sessions.find(state.owner.member_pk, state.conversation_id)
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
        opened = self.book(owner=state.owner).open(str(page_id) for page_id in page_ids[:MAX_PAGES_PER_OPEN])
        session.opened_pages = open_pages(session.opened_pages, [page.id for page in opened.pages], session.turn)
        self.sessions.save(session)
        return json.dumps({
            "opened": [page.id for page in opened.pages],
            **({"unknown": opened.unknown} if opened.unknown else {}),
            **({"did_you_mean": opened.suggestions} if opened.suggestions else {}),
            "next": (
                f"The opened pages are in your prompt under <open_pages> for the next "
                f"{settings.ila_page_retention_turns} turns, this one included."
            ),
        })

    async def search_book(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        query = str(tool_input.get("query") or "").strip()
        prefix = str(tool_input.get("prefix") or "").strip()
        if not query and not prefix:
            raise ValueError("search_book needs a `query`, a `prefix`, or both.")
        pages = self.book(owner=state.owner).search(query, prefix=prefix)
        return json.dumps({
            "pages": [
                {"id": page.id, "title": page.title, "summary": page.summary, **({"note": page.note} if page.note else {})}
                for page in pages
            ],
            "next": "Open the pages you need with open_pages." if pages else "Nothing matches; check the book index.",
        })

    def pointing_at_pages(
        self, session: BuilderSession, issues: list[BlueprintIssue], draft: Draft
    ) -> list[dict[str, Any]]:
        """Each issue with the page that explains it. Those pages are opened, so the fix has them to hand."""
        book = self.book()
        described, pages = [], []
        for issue in issues:
            row = _issue(issue)
            page_id = page_for_issue(issue.path, draft, book)
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
        # The person's answers to earlier skill forms, whatever Ila's YAML says; and the kit's ids, whatever names
        # she wrote them under.
        try:
            kit = active_kit(state.owner.account_id, session.kit_id) if session.kit_id else None
            before = declared(kit, session.baseline_yaml)
        except KitError as e:
            return json.dumps({"ok": False, "reason": str(e), "next": "Tell the person plainly; this kit can't change."})
        draft = Draft(pin(Draft(yaml).with_skill_settings(session.skill_inputs).text, kit))
        session.draft_yaml, session.draft_params, session.plan_id = draft.text, params, None
        needs = [(requirement, requirement.missing(draft, session, state.owner_email)) for requirement in REQUIREMENTS]
        for requirement, missing in needs:
            requirement.settle(session, missing)
        try:
            validated, issues = validate_blueprint(draft.text, params), []
        except BlueprintInvalid as e:
            validated, issues = None, e.issues

        attempt = PlanAttempt(self, session, state, draft, params, validated, issues, needs, before)
        result = next(answer for gate in PLAN_GATES if (answer := gate.check(attempt)) is not None)
        self.sessions.save(session)
        return json.dumps(result)

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

        outcome = deploy_blueprint(
            session.draft_yaml, session.draft_params, state.owner,
            kit_id=session.kit_id, baseline=session.baseline_yaml, conversation_id=state.conversation_id,
        )
        if not isinstance(outcome, Deployed):
            return json.dumps({"applied": False, **_not_deployed(outcome)})
        validated, plan, deployment = outcome.validated, outcome.plan, outcome.deployment
        if outcome.kit is not None:
            # From now on the draft is that kit's next version.
            session.kit_id, session.baseline_yaml = outcome.kit.kit_id, None
        if deployment.status != DeploymentStatus.APPLIED:
            return json.dumps({
                "applied": False,
                "status": deployment.status.value,
                "error": deployment.error,
                **({"removed": deployment.removed} if deployment.removed else {}),
            })

        session.deployment_id, session.plan_id = deployment.deployment_id, None
        # The next change in this conversation updates what was just built, rather than building it again.
        session.draft_yaml = Draft(session.draft_yaml).pinned({name: res.id for name, res in deployment.resources.items()}).text
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

    async def add_to_draft(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        session = self._session(state)
        page_id = str(tool_input.get("page_id") or "").strip()
        target = account_resource(page_id)
        if target is None:
            return json.dumps({
                "added": False,
                "reason": "That isn't one of the person's resources. Use its page id, account/<Kind>/<id>, from Your account.",
            })
        kind, resource_id = target
        if kind.drafted_whole:
            return self._load_whole(session, state, kind, resource_id)
        found = kind.read(state.owner, resource_id)
        if found is None:
            return json.dumps({"added": False, "reason": f"There's no such {named(kind, 1)}. Open {account_page_id(kind.kind)}."})

        draft = Draft(session.draft_yaml or new_document(found.name))
        in_draft = {str(spec["id"]): name for name, spec in draft.resources.items() if spec.get("id")}
        # What it links to is named as the draft names it, or by id when the draft doesn't hold it.
        resource = kind.observe(found.record, {linked_id: in_draft.get(linked_id, linked_id) for linked_id in found.links})
        name = in_draft.get(found.id) or _free_name(kind.draft_name(found.record), draft)
        session.draft_yaml, session.plan_id = draft.with_resource(name, resource).text, None
        self.sessions.save(session)
        return json.dumps({
            "added": True,
            "resource": name,
            "next": (
                f"It's in the draft as `{name}`, with its id. Keep the id and the name, change only what the person "
                "asked, then call plan_blueprint with the whole YAML."
            ),
        })

    def _load_whole(self, session: BuilderSession, state: AgentTurnState, kind: ResourceKind[Any], resource_id: str) -> str:
        """The draft becomes the resource with all it uses: its kit's last version, or else written out as it is."""
        kit = KitRepository().holding(state.owner.account_id, resource_id)
        current = (
            DeploymentRepository().find_by_id(state.owner.account_id, kit.current_deployment_id)
            if kit and kit.current_deployment_id else None
        )
        if kit is not None and current is not None:
            # In a kit: the draft is the kit's last version, so changing it is the kit's next one.
            session.draft_yaml = pin(Draft(current.blueprint_yaml).without_ids().text, kit)
            session.draft_params, session.kit_id, session.baseline_yaml = dict(current.params), kit.kit_id, None
        else:
            # Agents are the one kind drafted whole, and `export_agent` writes one out.
            yaml = export_agent(resource_id, state.owner)
            if yaml is None:
                return json.dumps({"added": False, "reason": f"There's no such {named(kind, 1)}. Open {account_page_id(kind.kind)}."})
            # Not in a kit yet: what it is now is the baseline, and its first apply here starts a kit.
            session.draft_yaml, session.draft_params, session.kit_id, session.baseline_yaml = yaml, {}, None, yaml
        session.plan_id = None
        # Answers to skill forms belonged to the old draft's resources.
        session.skill_inputs, session.pending_input = {}, None
        self.sessions.save(session)
        return json.dumps({
            "added": True,
            "replaced_draft": True,
            **({"kit": kit.title} if kit else {}),
            "next": (
                f"The {named(kind, 1)} is now the whole draft, in your prompt. Keep every `id` and resource name. Change only "
                "what the person asked for: add new resources without an id, and leave out anything they want gone. "
                "Then call plan_blueprint with the whole YAML."
            ),
        })

    async def build_status(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        session = self._session(state)
        deployment = (
            DeploymentRepository().find_by_id(state.owner.account_id, session.deployment_id) if session.deployment_id else None
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
        described = {}
        for name, resource in resources.items():
            path = kind_for(resource.kind).dashboard_path
            described[name] = {
                "kind": resource.kind,
                "id": resource.id,
                **({"dashboard_url": settings.frontend_url + path.format(id=resource.id)} if path else {}),
            }
        return described


def build_builder_tool_registry(tools: Optional[BuilderTools] = None) -> ToolRegistry:
    tools = tools or BuilderTools()
    open_book, search, show_form, plan, apply, add, status = builder_tool_definitions()
    return ToolRegistry([
        # Opening pages changes the pages Ila's prompt shows.
        BoundTool(ToolSpec(open_book, ToolCategory.BUILDER, mutates_prompt_context=True), tools.open_book_pages),
        BoundTool(ToolSpec(search, ToolCategory.BUILDER), tools.search_book),
        BoundTool(ToolSpec(show_form, ToolCategory.BUILDER), tools.show_form),
        # Planning and applying change the draft that Ila's prompt shows.
        BoundTool(ToolSpec(plan, ToolCategory.BUILDER, mutates_prompt_context=True), tools.plan),
        BoundTool(ToolSpec(apply, ToolCategory.BUILDER, mutates_prompt_context=True), tools.apply),
        # Adding to the draft changes the draft the prompt shows.
        BoundTool(ToolSpec(add, ToolCategory.BUILDER, mutates_prompt_context=True), tools.add_to_draft),
        BoundTool(ToolSpec(status, ToolCategory.BUILDER), tools.build_status),
    ])


__all__ = ["BuilderTools", "build_builder_tool_registry", "builder_tool_definitions"]
