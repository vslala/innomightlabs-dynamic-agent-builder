"""Every skill folder's manifest loads: the registry skips an invalid one with only a warning, so a broken manifest
would otherwise leave its skill silently missing."""

from pathlib import Path

from src.skills.registry import SkillRegistry

SKILLS_DIR = Path(__file__).resolve().parents[1] / "src" / "skills"


def test_every_skill_folder_with_a_manifest_is_loaded():
    folders = {path.parent.name for path in SKILLS_DIR.glob("*/manifest.yml")}

    registry = SkillRegistry(SKILLS_DIR)
    loaded = {skill.folder_name for skill in [*registry.list(), *registry.core_skills()]}

    assert folders - loaded == set()
