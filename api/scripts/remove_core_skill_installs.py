#!/usr/bin/env python3
"""
Removes agents' installs of skills that are now core (`core: true` in their manifest, served as core tools by a tool
family): today `documents`. The runtime already ignores them (`SkillRegistry.get` doesn't find a core skill); this
takes the rows out of the agents' skill lists. See docs/LLD-message-references-and-tool-families.md, section 6.

Usage:
    uv run python scripts/remove_core_skill_installs.py           # dry run: lists what would go
    uv run python scripts/remove_core_skill_installs.py --apply   # delete

Uses the API's own settings (DYNAMODB_TABLE, DYNAMODB_ENDPOINT, AWS credentials). Against production, run it through
`railway run` so they come from the service, never from a file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from boto3.dynamodb.conditions import Attr  # noqa: E402

from src.config import settings  # noqa: E402
from src.db import get_dynamodb_resource  # noqa: E402
from src.skills.registry import get_skill_registry  # noqa: E402
from src.skills.repository import AgentSkillRepository  # noqa: E402


def core_installs() -> list[dict[str, Any]]:
    core_ids = [skill.manifest.id for skill in get_skill_registry().core_skills()]
    if not core_ids:
        return []
    table = get_dynamodb_resource().Table(settings.dynamodb_table)
    scan: dict[str, Any] = {"FilterExpression": Attr("entity_type").eq("AgentSkill") & Attr("skill_id").is_in(core_ids)}
    rows: list[dict[str, Any]] = []
    while True:
        response = table.scan(**scan)
        rows.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            return rows
        scan["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="delete (default: dry run)")
    args = parser.parse_args()

    rows = core_installs()
    repository = AgentSkillRepository()
    failed = 0
    for row in rows:
        agent_id = str(row["pk"]).removeprefix("Agent#")
        installed_skill_id = str(row["sk"]).removeprefix("Skill#")
        print(f"{'delete' if args.apply else 'would delete'}: agent {agent_id} skill {installed_skill_id}")
        if args.apply and not repository.delete(agent_id, installed_skill_id):
            failed += 1
    print(f"{len(rows)} install(s) of core skills{'' if args.apply else ' (dry run)'}; {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
