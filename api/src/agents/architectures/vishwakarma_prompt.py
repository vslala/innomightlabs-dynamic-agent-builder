"""Prompt construction for Vishwakarma, the architecture behind Ada the solution builder."""

from __future__ import annotations

from dataclasses import dataclass

from src.agents.book import Book, Page, pages_in_view, turns_left
from src.agents.prompts import render_system_prompt
from src.builder.models import BuilderSession

SYSTEM_PROMPT_TEMPLATE = "vishwakarma_system_prompt.j2"


@dataclass(frozen=True)
class OpenPage:
    page: Page
    #: Turns it stays in the prompt after this one, unless it's opened again.
    turns_left: int


def open_pages_for(book: Book, session: BuilderSession, retention: int) -> list[OpenPage]:
    return [
        OpenPage(page=page, turns_left=turns_left(session.opened_pages[page_id], session.turn, retention))
        for page_id in pages_in_view(session.opened_pages, session.turn, retention)
        if (page := book.get(page_id))
    ]


def build_vishwakarma_system_prompt(
    *,
    book: Book,
    session: BuilderSession,
    retention: int,
    conversation_context: str | None = None,
) -> str:
    """Renders data already loaded for this turn: the book's index and open pages, and the current draft."""
    return render_system_prompt(
        SYSTEM_PROMPT_TEMPLATE,
        has_memory_tools=False,
        conversation_context=conversation_context,
        chapters=book.chapters,
        open_pages=open_pages_for(book, session, retention),
        retention=retention,
        provider=session.provider,
        model=session.model,
        draft_yaml=session.draft_yaml,
        draft_params=session.draft_params,
        plan_id=session.plan_id,
        pending_input=session.pending_input,
        built=bool(session.deployment_id),
    )
