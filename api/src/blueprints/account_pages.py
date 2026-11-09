"""The book's "Your account" branch: what the person already has, as pages Ila opens to read.

Every page comes from the resource kinds (`existing`, `read`, `observe`), so a new kind is readable here with no change:

- `account/<Kind>`: the owner's resources of that kind, one line each.
- `account/<Kind>/<id>`: one of them, as a blueprint writes it, with its id and what it links to.
- `account/<Kind>/<id>/<field>`: a long text of it in full, such as an agent's instructions.
- `account/models`: the providers set up in Settings (named in its index line, read from the settings only) and the
  models each lists now, asked of the providers only when the page is opened.

Pages are made when they're opened (a `PageResolver`), so a turn reads only the account data Ila asks for. Reading is
all they do: `add_to_draft` puts one of them in the draft to change it.
"""

from __future__ import annotations

from typing import Any, Optional

import yaml  # type: ignore[import-untyped,unused-ignore]

from src.accounts.owner import Owner
from src.agents.book import Chapter, Page
from src.agents.image_generation.capabilities import ImageCapability
from src.blueprints.kinds import RESOURCE_KINDS, ResourceKind
from src.blueprints.kinds.base import Found, is_long_text
from src.form_options import FormOptionsContext, configured_providers, load_agent_model_choices

ACCOUNT = "account"
MODELS_PAGE = f"{ACCOUNT}/models"


def account_page_id(kind: str, resource_id: Optional[str] = None, field_name: Optional[str] = None) -> str:
    return "/".join(part for part in (ACCOUNT, kind, resource_id, field_name) if part)


def account_resource(page_id: str) -> Optional[tuple[ResourceKind[Any], str]]:
    """The kind and id an `account/<Kind>/<id>` page shows, or None for any other id."""
    parts = page_id.strip().split("/")
    kind = _kind(parts[1]) if len(parts) == 3 and parts[0] == ACCOUNT else None
    return (kind, parts[2]) if kind else None


def _kind(name: str) -> Optional[ResourceKind[Any]]:
    return next((kind for kind in RESOURCE_KINDS if kind.kind == name), None)


def named(kind: ResourceKind[Any], count: int = 2) -> str:
    """The kind as said in a sentence: "agents", "knowledge base", "MCP connections"."""
    label = kind.label if kind.label.split()[0].isupper() else kind.label[0].lower() + kind.label[1:]
    return label if count == 1 else f"{label}s"


def _line(kind: ResourceKind[Any], found: Found) -> Page:
    """A resource's index line: what lists and search show. Opening it makes the page itself."""
    return Page(id=account_page_id(kind.kind, found.id), title=found.name, summary=f"{kind.label}: {found.summary}", body="")


class AccountPages:
    """A page source for the index lines and a resolver for the pages themselves, for one owner."""

    prefix = f"{ACCOUNT}/"

    def __init__(self, owner: Owner):
        self.owner = owner

    def chapter(self) -> Chapter:
        return Chapter(
            title="Your account",
            intro=(
                "What the person already has, read from their account when you open a page. Open a kind to list "
                "them, then one to read it as a blueprint writes it; its long texts are pages under it. To change "
                "one, call add_to_draft with its page id."
            ),
            pages=(
                self._models_line(),
                *(
                    Page(
                        id=account_page_id(kind.kind),
                        title=f"{kind.label}s in your account",
                        summary=f"Every one of the person's {named(kind)}, by name. Open it to list them.",
                        body="",
                        use_when=f"The person asks about, or wants to change, one of the {named(kind)} they already have.",
                    )
                    for kind in RESOURCE_KINDS
                ),
            ),
        )

    def resolve(self, page_id: str) -> Optional[Page]:
        if page_id == MODELS_PAGE:
            return self._models()
        parts = page_id.split("/")
        kind = _kind(parts[1]) if len(parts) > 1 else None
        if kind is None or len(parts) > 4:
            return None
        if len(parts) == 2:
            return self._list(kind)
        found = kind.read(self.owner, parts[2])
        if found is None:
            return None
        return self._resource(kind, found) if len(parts) == 3 else self._text(kind, found, parts[3])

    def searchable(self, prefix: str) -> list[Page]:
        """Each resource's index line, of the kinds `prefix` reaches: `account/Agent` reads only agents."""
        reached = [
            kind for kind in RESOURCE_KINDS
            if account_page_id(kind.kind).startswith(prefix) or prefix.startswith(f"{account_page_id(kind.kind)}/")
        ]
        return [_line(kind, found) for kind in reached for found in kind.existing(self.owner)]

    def _models_line(self) -> Page:
        """Always in the index, so the providers' names are too; the models are listed only when it's opened."""
        providers = configured_providers(FormOptionsContext(owner=self.owner))
        return Page(
            id=MODELS_PAGE,
            title="Providers and models",
            summary=(
                f"Providers set up in Settings: {', '.join(providers)}. Open it for the models each one offers."
                if providers else "No provider is set up in Settings yet, so no agent can be built."
            ),
            body="",
            use_when="An agent should use a model other than yours, or the person asks which models they can use.",
        )

    def _models(self) -> Page:
        choices = load_agent_model_choices(FormOptionsContext(owner=self.owner))
        body = [
            "The models an agent's `model` can be, read from the providers now. Write the id exactly as shown, with "
            "its `provider`; leave `model` out to use the provider's default.",
        ]
        for provider in choices.providers:
            body += ["", f"## {provider}"]
            models = [model for listed_by, model in choices.catalog if listed_by == provider]
            if provider in choices.unlisted:
                body.append("Its models couldn't be listed just now. Leave `model` out, or open this page again later.")
            elif not models:
                body.append("It lists no models. Leave `model` out to use its default.")
            body += [f"- `{model.model_name}`: {model.display_name}{_reads_images(model.capabilities)}" for model in models]
        if not choices.providers:
            body += ["", "No provider is set up. An account admin adds one in Settings > Provider Configuration."]
        return Page(
            id=MODELS_PAGE,
            title="Providers and models",
            summary=f"{len(choices.catalog)} models from {len(choices.providers)} providers.",
            body="\n".join(body),
        )

    def _list(self, kind: ResourceKind[Any]) -> Page:
        found = kind.existing(self.owner)
        return Page(
            id=account_page_id(kind.kind),
            title=f"{kind.label}s in your account",
            summary=f"{len(found)} {named(kind, len(found))}.",
            body=(
                f"The person has {len(found)} {named(kind, len(found))}. Open one to read it."
                if found else f"The person has no {named(kind)} yet."
            ),
            children=tuple(_line(kind, item) for item in found),
        )

    def _resource(self, kind: ResourceKind[Any], found: Found) -> Page:
        page_id = account_page_id(kind.kind, found.id)
        # What it links to is written by id: their pages are named below.
        observed = kind.observe(found.record, {linked_id: linked_id for linked_id in found.links})
        long_fields = [name for name, value in observed.items() if is_long_text(value)]
        shown = {
            name: f"({len(str(value).strip().splitlines())} lines: open {page_id}/{name})" if name in long_fields else value
            for name, value in observed.items()
        }
        body = [*found.facts, *([""] if found.facts else [])]
        body += ["As a blueprint writes it now:", "```yaml", yaml.safe_dump(shown, sort_keys=False, allow_unicode=True, width=100).rstrip(), "```"]
        if found.links:
            body += ["", "It links to:", *(f"- `{account_page_id(linked_kind, linked_id)}`" for linked_id, linked_kind in found.links.items())]
        body += ["", f"To change it, call add_to_draft with `{page_id}`."]
        return Page(
            id=page_id,
            title=found.name,
            summary=found.summary,
            body="\n".join(body),
            children=tuple(
                Page(
                    id=f"{page_id}/{name}",
                    title=f"{found.name}: {name}",
                    summary=f"{len(str(observed[name]).strip().splitlines())} lines, {len(str(observed[name]))} characters.",
                    body="",
                )
                for name in long_fields
            ),
        )

    def _text(self, kind: ResourceKind[Any], found: Found, field_name: str) -> Optional[Page]:
        value = kind.observe(found.record, {}).get(field_name)
        if not isinstance(value, str):
            return None
        return Page(
            id=account_page_id(kind.kind, found.id, field_name),
            title=f"{found.name}: {field_name}",
            summary=f"The whole of its `{field_name}`.",
            body=f"The {named(kind, 1)}'s `{field_name}` as it is now, in full.\n\n```text\n{value.strip()}\n```",
        )


def _reads_images(capabilities: list[str]) -> str:
    return " (reads images)" if ImageCapability.UNDERSTANDING.value in capabilities else ""
