"""Structured prompt context primitives.

Keep the API tiny and focused. We'll evolve this incrementally as we refactor
krishna_memgpt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


SectionId = Literal[
    "identity",
    "persona",
    "core_memory",
    "memory_tools",
    "knowledge_base",
    "skills",
    "warnings",
]


DEFAULT_SECTION_ORDER: list[SectionId] = [
    "identity",
    "persona",
    "core_memory",
    "memory_tools",
    "knowledge_base",
    "skills",
    "warnings",
]


@dataclass(frozen=True)
class ContextBlock:
    section: SectionId
    content: str
    title: str | None = None


@dataclass
class PromptContext:
    """A structured system-prompt builder.

    Blocks are grouped into sections and later rendered in a stable order.
    """

    blocks: list[ContextBlock] = field(default_factory=list)

    def add(self, block: ContextBlock) -> None:
        self.blocks.append(block)

    def add_section(self, section: SectionId, content: str, *, title: str | None = None) -> None:
        self.add(ContextBlock(section=section, content=content, title=title))

    def render(self, *, section_order: list[SectionId] | None = None) -> str:
        order = section_order or DEFAULT_SECTION_ORDER

        by_section: dict[SectionId, list[ContextBlock]] = {sid: [] for sid in order}
        for b in self.blocks:
            by_section.setdefault(b.section, []).append(b)

        rendered: list[str] = []
        for sid in order:
            for b in by_section.get(sid, []):
                rendered.append(b.content.strip("\n"))

        # Keep final output predictable: sections separated by blank lines.
        return "\n\n".join([part for part in rendered if part.strip()])
