"""Macros in an agent's instructions, such as `{{ lead_form:demo-request }}`, expanded into its system prompt.

They let an owner keep something in one place (a lead form) and have every agent that names it see the current
version. Only the stored instructions are expanded, once per turn: what a visitor types is never read for macros.
Instructions are plain text to Jinja (`agents/prompts.py` passes them as a variable), so the braces are ours alone.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from src.leads.macro import render_lead_form

MACRO = re.compile(r"\{\{\s*([a-z_]+):([a-z0-9-]+)\s*\}\}")
MAX_MACROS = 5


@dataclass(frozen=True)
class MacroContext:
    account_id: str
    #: The skills this turn may use, so a macro can say when its skill is missing
    skill_ids: frozenset[str]


@dataclass(frozen=True)
class InstructionMacro:
    prefix: str
    render: Callable[[str, MacroContext], str]


MACROS = [InstructionMacro("lead_form", render_lead_form)]


def expand_instructions(instructions: str, context: MacroContext) -> str:
    """The instructions with every known macro replaced. Unknown prefixes stay as written."""
    by_prefix = {macro.prefix: macro for macro in MACROS}
    expanded = 0

    def expand(match: re.Match[str]) -> str:
        nonlocal expanded
        macro = by_prefix.get(match.group(1))
        if macro is None:
            return match.group(0)
        expanded += 1
        if expanded > MAX_MACROS:
            return f"[{macro.prefix} skipped: at most {MAX_MACROS} macros are expanded]"
        return macro.render(match.group(2), context)

    return MACRO.sub(expand, instructions)


def macro_arguments(instructions: str, prefix: str) -> list[str]:
    """What the instructions name with `prefix`, e.g. the lead form slugs, for checks before the agent runs."""
    return [match.group(2) for match in MACRO.finditer(instructions) if match.group(1) == prefix]
