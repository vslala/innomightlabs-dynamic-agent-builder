from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.form_models import Form


class SkillEditFormResponse(BaseModel):
    form_schema: Form
    initial_values: dict[str, Any]
