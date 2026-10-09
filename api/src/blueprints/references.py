"""Where one resource in a blueprint names another.

A reference is a field marked `x-ref-kind` (an agent's `knowledge_bases`, a widget key's `agent`), or a skill
setting whose manifest says it names an agent (`agent_invocation`'s `target_agent_id`). Each kind lists its
references (`ResourceKind.references`), and everything that follows them reads that one list: the validator
checks them and orders the resources, the drawing wires them, and apply resolves their names to ids.
"""

from dataclasses import dataclass
from typing import Iterator, Optional

from pydantic import BaseModel

from src.blueprints.parser import join_path
from src.blueprints.skills_schema import skill_variants
from src.blueprints.spec import REF_KIND, SkillEntry


@dataclass(frozen=True)
class Reference:
    #: Where the name is written, for issues: "resources.lead.skills[0].config.target_agent_id".
    path: str
    #: The name written there: a resource in the blueprint, or for some references an id from the account.
    target: str
    #: The kind the target must be.
    kind: str
    #: How the place it's written reads in a sentence: "`knowledge_bases`", "this skill".
    where: str
    #: An id from the person's account is fine too; the plan checks it against the account.
    may_be_id: bool = False
    #: Set when the drawing's wire runs from the resource naming the target, with this label ("hands work to").
    #: Otherwise it runs from the target, labelled with what the target's kind feeds.
    outward_wire: Optional[str] = None


def field_references(name: str, spec: BaseModel) -> Iterator[Reference]:
    """Every field of the spec marked `x-ref-kind`, one reference per name it holds."""
    for field_name, info in type(spec).model_fields.items():
        extra = info.json_schema_extra
        if not isinstance(extra, dict) or REF_KIND not in extra:
            continue
        value = getattr(spec, field_name)
        path = f"resources.{name}.{field_name}"
        targets = [(join_path(path, index), item) for index, item in enumerate(value)] if isinstance(value, list) else [
            (path, value)
        ]
        for target_path, target in targets:
            yield Reference(
                path=target_path,
                target=target,
                kind=str(extra[REF_KIND]),
                where=f"`{field_name}`",
            )


def skill_references(name: str, skills: list[SkillEntry]) -> Iterator[Reference]:
    """Skill settings that name an agent, as the skill's manifest marks them."""
    variants = skill_variants()
    for index, entry in enumerate(skills):
        variant = variants.get(entry.id)
        for setting, kind in (variant.reference_fields if variant else {}).items():
            value = (entry.config or {}).get(setting)
            if isinstance(value, str) and value:
                yield Reference(
                    path=f"resources.{name}.skills[{index}].config.{setting}",
                    target=value,
                    kind=kind,
                    where="this skill",
                    may_be_id=True,
                    outward_wire="hands work to",
                )
