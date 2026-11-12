"""What a skill needs set up in the account before it can be installed, declared in its manifest as `requires`.

A requirement is a name the platform knows, a test of whether an account has it, and where the person sets it up.
The install check, the catalog (as `available` and `requirements`) and blueprint plans all ask the same list, so a
skill states what it depends on in one line of its manifest, and a new kind of dependency is one more entry here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.skills.models import SkillManifest, SkillRequirementStatus


@dataclass(frozen=True)
class SkillRequirement:
    name: str
    #: Finishes "<Skill> needs ...": what is missing, in words the person acts on.
    needs: str
    #: The dashboard page where it is set up.
    setup_path: str
    is_met: Callable[[str], bool]


def _image_generation_is_set_up(account_id: str) -> bool:
    from src.agents.image_generation.settings import ImageGenerationSettingsRepository

    saved = ImageGenerationSettingsRepository().find_in_account(account_id)
    return bool(saved and saved.is_configured)


SKILL_REQUIREMENTS: tuple[SkillRequirement, ...] = (
    SkillRequirement(
        name="image_generation",
        needs="image generation set up first. An admin can do that in Settings > Image Generation",
        setup_path="/dashboard/settings",
        is_met=_image_generation_is_set_up,
    ),
)


def requirement_named(name: str) -> SkillRequirement | None:
    return next((requirement for requirement in SKILL_REQUIREMENTS if requirement.name == name), None)


def unknown_requirements(manifest: SkillManifest) -> list[str]:
    """Names in a manifest's `requires` that the platform doesn't know: a typo would otherwise never be met."""
    return [name for name in manifest.requires if requirement_named(name) is None]


def requirement_statuses(manifest: SkillManifest, account_id: str | None) -> list[SkillRequirementStatus]:
    """Each requirement of the skill and whether the account has it (unmet when there is no account to ask)."""
    statuses = []
    for name in manifest.requires:
        requirement = requirement_named(name)
        if requirement is None:
            continue
        statuses.append(SkillRequirementStatus(
            name=requirement.name,
            needs=requirement.needs,
            setup_path=requirement.setup_path,
            met=bool(account_id and requirement.is_met(account_id)),
        ))
    return statuses


def unmet_requirements(manifest: SkillManifest, account_id: str) -> list[SkillRequirementStatus]:
    return [status for status in requirement_statuses(manifest, account_id) if not status.met]
