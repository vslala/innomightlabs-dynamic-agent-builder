"""
Tests for the skills registry and schema loading.
"""

import json
from pathlib import Path

import pytest

from src.skills.registry import FileSystemSkillsRegistry
from src.skills.schema_loader import parse_form_schema
from src.skills.models import SkillPackageConfig, SkillRegistryEntry


@pytest.fixture
def skills_root(tmp_path):
    """Create a temporary skills directory with a sample skill."""
    skill_dir = tmp_path / "sample-skill"
    skill_dir.mkdir()
    (skill_dir / "config.json").write_text(
        json.dumps({
            "skill_id": "sample-skill",
            "name": "Sample Skill",
            "description": "A test skill",
            "version": "1.0.0",
        }),
        encoding="utf-8",
    )
    (skill_dir / "schema.json").write_text(
        json.dumps({
            "form_name": "Sample Config",
            "submit_path": "/skills/enable",
            "form_inputs": [
                {"input_type": "text", "name": "api_key", "label": "API Key"},
            ],
        }),
        encoding="utf-8",
    )
    return tmp_path


def test_registry_list_skills(skills_root):
    registry = FileSystemSkillsRegistry(skills_root)
    skills = registry.list_skills()
    assert len(skills) == 1
    assert skills[0].skill_id == "sample-skill"
    assert skills[0].name == "Sample Skill"
    assert skills[0].has_schema is True


def test_registry_get_schema(skills_root):
    registry = FileSystemSkillsRegistry(skills_root)
    schema = registry.get_schema("sample-skill")
    assert schema is not None
    assert schema["form_name"] == "Sample Config"
    assert len(schema["form_inputs"]) == 1


def test_registry_get_config(skills_root):
    registry = FileSystemSkillsRegistry(skills_root)
    config = registry.get_config("sample-skill")
    assert config is not None
    assert config.skill_id == "sample-skill"
    assert config.name == "Sample Skill"


def test_registry_missing_skill_returns_none(skills_root):
    registry = FileSystemSkillsRegistry(skills_root)
    assert registry.get_schema("nonexistent") is None
    assert registry.get_config("nonexistent") is None


def test_parse_form_schema_valid():
    raw = {
        "form_name": "Test Form",
        "submit_path": "/skills/enable",
        "form_inputs": [
            {"input_type": "text", "name": "field1", "label": "Field 1"},
            {"input_type": "password", "name": "secret", "label": "Secret"},
        ],
    }
    form = parse_form_schema(raw)
    assert form is not None
    assert form.form_name == "Test Form"
    assert len(form.form_inputs) == 2
    assert form.form_inputs[0].name == "field1"
    assert form.form_inputs[1].input_type.value == "password"


def test_parse_form_schema_invalid_returns_none():
    assert parse_form_schema({}) is None
    assert parse_form_schema({"form_name": "X"}) is None
    assert parse_form_schema(None) is None
