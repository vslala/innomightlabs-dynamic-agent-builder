from __future__ import annotations

import hashlib
import json
from typing import Any

from src.skills.models import SkillManifest


def installed_skill_id_for(
    manifest: SkillManifest,
    normalized_config: dict[str, Any],
) -> str:
    if not manifest.repeatable:
        return manifest.id

    identity_fields = manifest.repeatable_identity_fields or sorted(normalized_config.keys())
    identity_values = {
        field_name: normalized_config.get(field_name)
        for field_name in identity_fields
    }
    identity_json = json.dumps(
        identity_values,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(identity_json.encode("utf-8")).hexdigest()[:16]
    return f"{manifest.id}:{digest}"
