#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLUGIN_IDS = ("vscode", "wordpress")
PLUGIN_METADATA = {
    "vscode": {
        "kind": "Editor plugin",
        "platform": "VS Code",
        "tagline": "Build and test Innomight agents without leaving your editor.",
        "description": "Open agent workflows, run quick checks, and move from code to automation with a VS Code extension built for day-to-day development.",
    },
    "wordpress": {
        "kind": "Website plugin",
        "platform": "WordPress",
        "tagline": "Connect your WordPress site to Innomight agents and automations.",
        "description": "Add Innomight-powered chat and workflow hooks to WordPress so site visitors can interact with your agents from the pages they already use.",
    },
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_version(value: str) -> tuple[int, int, int]:
    parts = value.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return (0, 1, 0)
    return int(parts[0]), int(parts[1]), int(parts[2])


def bump_patch(value: str) -> str:
    major, minor, patch = parse_version(value)
    return f"{major}.{minor}.{patch + 1}"


def choose_version(plugin_id: str, build: dict[str, Any], previous: dict[str, Any] | None) -> str:
    env_name = f"{plugin_id.upper()}_PLUGIN_VERSION"
    if os.getenv(env_name):
        return str(os.environ[env_name]).strip()

    package_version = str(build.get("package_version") or "0.1.0")
    if not previous:
        return package_version

    if previous.get("source_hash") == build.get("source_hash"):
        return str(previous.get("version") or package_version)

    return bump_patch(str(previous.get("version") or package_version))


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    existing = load_json(Path(args.existing_manifest))
    previous_by_id = {
        str(item.get("id")): item
        for item in existing.get("plugins", [])
        if isinstance(item, dict) and item.get("id")
    }

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    plugins: list[dict[str, Any]] = []
    build_root = Path(args.build_root)

    for plugin_id in PLUGIN_IDS:
        plugin_dir = build_root / plugin_id
        build = load_json(plugin_dir / "plugin-build.json")
        if not build:
            raise SystemExit(f"Missing build metadata for plugin: {plugin_id}")

        previous = previous_by_id.get(plugin_id)
        version = choose_version(plugin_id, build, previous)
        artifact_name = f"{build['artifact_stem']}-{version}{build['artifact_extension']}"
        plugin_prefix = f"{args.prefix.rstrip('/')}/{plugin_id}"
        metadata = PLUGIN_METADATA[plugin_id]
        artifact_path = plugin_dir / build["artifact_local_name"]
        artifact_key = f"{plugin_prefix}/{artifact_name}"

        plugins.append(
            {
                "id": plugin_id,
                "name": build["name"],
                "version": version,
                "kind": metadata["kind"],
                "platform": metadata["platform"],
                "tagline": metadata["tagline"],
                "description": metadata["description"],
                "icon_key": f"{plugin_prefix}/icon.svg",
                "readme_key": f"{plugin_prefix}/README.md",
                "artifact": {
                    "key": artifact_key,
                    "filename": artifact_name,
                    "content_type": build["artifact_content_type"],
                    "size_bytes": artifact_path.stat().st_size,
                    "sha256": build["sha256"],
                },
                "source_hash": build["source_hash"],
                "updated_at": generated_at if not previous or previous.get("source_hash") != build.get("source_hash") else previous.get("updated_at", generated_at),
            }
        )

    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "plugins": plugins,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate plugin downloads manifest.")
    parser.add_argument("--build-root", default="dist/downloads")
    parser.add_argument("--existing-manifest", default="dist/downloads/existing-manifest.json")
    parser.add_argument("--output", default="dist/downloads/manifest.json")
    parser.add_argument("--prefix", default="artifacts/plugins")
    args = parser.parse_args()

    manifest = build_manifest(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
