"""Offline regression tests: python3 -m unittest discover -s scripts/downloads -v."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import zipfile


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "downloads"
PLUGIN_ID = "wordpress-ai-search"
SLUG = "innomight-ai-search"
SPEC = importlib.util.spec_from_file_location("plugins_manifest", SCRIPTS / "generate_plugins_manifest.py")
assert SPEC is not None and SPEC.loader is not None
manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest)


class PluginsPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scripts = self.root / "scripts" / "downloads"
        shutil.copytree(SCRIPTS, self.scripts, ignore=shutil.ignore_patterns("__pycache__"))
        self.plugin = self.root / "plugins" / "wordpress" / SLUG
        shutil.copytree(ROOT / "plugins" / "wordpress" / SLUG, self.plugin)
        self.build_root = self.root / "dist" / "downloads"
        self.output = self.build_root / PLUGIN_ID
        self.env = {key: value for key, value in os.environ.items() if not key.endswith("_PLUGIN_VERSION")}

    def package(self) -> dict:
        subprocess.run(
            ["bash", str(self.scripts / "package_wordpress_ai_search_plugin.sh")],
            check=True, capture_output=True, text=True, env=self.env, timeout=30,
        )
        return json.loads((self.output / "plugin-build.json").read_text())

    def generate(self, previous: dict | None = None, prefix: str = "artifacts/plugins") -> dict:
        existing = self.build_root / "existing-manifest.json"
        if previous is not None:
            existing.write_text(json.dumps(previous))
        output = self.build_root / "manifest.json"
        subprocess.run(
            ["python3", str(self.scripts / "generate_plugins_manifest.py"),
             "--build-root", str(self.build_root), "--existing-manifest", str(existing),
             "--output", str(output), "--prefix", prefix],
            check=True, capture_output=True, text=True, env=self.env, timeout=30,
        )
        return json.loads(output.read_text())

    def seed_other_builds(self) -> None:
        # Other plugins are fixtures, never rebuilt or written into the real dist directory.
        for plugin_id, stem, extension in (
            ("vscode", "innomightlabs-code-assist", ".vsix"),
            ("wordpress", "innomightlabs-ai-connector", ".zip"),
        ):
            directory = self.build_root / plugin_id
            directory.mkdir(parents=True)
            artifact = stem + extension
            payload = plugin_id.encode()
            (directory / artifact).write_bytes(payload)
            (directory / "README.md").write_text("# Fixture\n")
            (directory / "icon.svg").write_text("<svg/>\n")
            (directory / "plugin-build.json").write_text(json.dumps({
                "id": plugin_id, "name": plugin_id, "package_version": "0.2.3",
                "artifact_local_name": artifact, "artifact_stem": stem,
                "artifact_extension": extension, "artifact_content_type": "application/zip",
                "readme_local_name": "README.md", "icon_local_name": "icon.svg",
                "sha256": hashlib.sha256(payload).hexdigest(), "source_hash": plugin_id,
            }))

    def test_package_contents_version_checksum_readme_and_icon(self) -> None:
        for name in (".git", "node_modules", "vendor", "docs", "tests"):
            directory = self.plugin / name
            directory.mkdir(exist_ok=True)
            (directory / "excluded.txt").write_text("not shipped")
        (self.plugin / ".DS_Store").write_text("not shipped")
        build = self.package()
        self.assertEqual(build["id"], PLUGIN_ID)
        header = (self.plugin / f"{SLUG}.php").read_text()
        version = re.search(r"\*\s*Version:\s*(\S+)", header).group(1)
        self.assertEqual(build["package_version"], version)
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        plugin_uri = re.search(r"^\s*\*\s*Plugin URI:\s*(\S+)", header, re.M).group(1)
        author_uri = re.search(r"^\s*\*\s*Author URI:\s*(\S+)", header, re.M).group(1)
        self.assertEqual(plugin_uri, "https://innomightlabs.com/downloads/plugins/wordpress-ai-search")
        self.assertNotEqual(plugin_uri, author_uri)
        self.assertEqual(build["artifact_local_name"], f"{SLUG}.zip")
        artifact = self.output / build["artifact_local_name"]
        self.assertEqual(build["sha256"], hashlib.sha256(artifact.read_bytes()).hexdigest())
        self.assertRegex(build["source_hash"], r"^[0-9a-f]{64}$")
        excluded = {".git", "node_modules", "vendor", "docs", "tests", ".wordpress-org", ".DS_Store"}
        expected = {
            f"{SLUG}/{path.relative_to(self.plugin).as_posix()}": path.read_bytes()
            for path in self.plugin.rglob("*") if path.is_file()
            and not excluded.intersection(path.relative_to(self.plugin).parts)
        }
        with zipfile.ZipFile(artifact) as archive:
            actual = {item.filename: archive.read(item) for item in archive.infolist() if not item.is_dir()}
        self.assertEqual(actual, expected)
        self.assertIn(f"{SLUG}/block/editor.js", actual)
        self.assertIn(f"{SLUG}/assets/js/chat.js", actual)
        self.assertIn(f"{SLUG}/uninstall.php", actual)
        readme = (self.output / build["readme_local_name"]).read_text()
        self.assertTrue(readme.startswith("# Innomight AI Search\n"))
        self.assertIn("## Description\n", readme)
        self.assertIn("### Do I need an Innomight Labs account?\n", readme)
        self.assertIn("https://innomightlabs.com/", readme)
        self.assertEqual((self.output / build["icon_local_name"]).read_bytes(),
                         (self.plugin / ".wordpress-org" / "icon.svg").read_bytes())
        self.assertFalse((self.output / "staging").exists())

    def test_source_hash_tracks_published_icon_but_not_excluded_tests(self) -> None:
        original = self.package()["source_hash"]
        (self.plugin / "tests" / "ignored.txt").write_text("test-only change")
        self.assertEqual(self.package()["source_hash"], original)
        icon = self.plugin / ".wordpress-org" / "icon.svg"
        icon.write_text(icon.read_text() + "\n<!-- new icon -->\n")
        self.assertNotEqual(self.package()["source_hash"], original)

    def test_manifest_includes_all_plugins_and_versioned_keys(self) -> None:
        build = self.package()
        self.seed_other_builds()
        result = self.generate(prefix="custom/plugins/")
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual([item["id"] for item in result["plugins"]], list(manifest.PLUGIN_IDS))
        self.assertEqual(set(manifest.PLUGIN_IDS), {"vscode", "wordpress", PLUGIN_ID})
        plugin = result["plugins"][-1]
        version = build["package_version"]
        filename = f"{SLUG}-{version}.zip"
        prefix = f"custom/plugins/{PLUGIN_ID}"
        self.assertEqual(plugin["version"], version)
        self.assertEqual(plugin["platform"], "WordPress")
        self.assertEqual(plugin["name"], "Innomight AI Search")
        self.assertEqual(plugin["readme_key"], f"{prefix}/README.md")
        self.assertEqual(plugin["icon_key"], f"{prefix}/icon.svg")
        self.assertEqual(plugin["artifact"], {
            "key": f"{prefix}/{filename}", "filename": filename,
            "content_type": "application/zip", "size_bytes": (self.output / f"{SLUG}.zip").stat().st_size,
            "sha256": build["sha256"],
        })
        plugin["version"] = "2.3.4"
        plugin["updated_at"] = "2025-01-01T00:00:00Z"
        unchanged = self.generate(result)["plugins"][-1]
        self.assertEqual(unchanged["version"], "2.3.4")
        self.assertEqual(unchanged["updated_at"], plugin["updated_at"])
        build["source_hash"] = "changed"
        (self.output / "plugin-build.json").write_text(json.dumps(build))
        changed = self.generate(result)["plugins"][-1]
        self.assertEqual(changed["version"], "2.3.5")
        self.assertNotEqual(changed["updated_at"], plugin["updated_at"])
        self.env["WORDPRESS_AI_SEARCH_PLUGIN_VERSION"] = "4.5.6"
        self.assertEqual(self.generate(result)["plugins"][-1]["version"], "4.5.6")

    def test_missing_ai_search_build_is_rejected(self) -> None:
        self.seed_other_builds()
        with self.assertRaisesRegex(SystemExit, "Missing build metadata for plugin: wordpress-ai-search"):
            from argparse import Namespace
            manifest.build_manifest(Namespace(
                build_root=str(self.build_root), existing_manifest=str(self.build_root / "missing.json"),
                prefix="artifacts/plugins",
            ))

    def test_publisher_iterates_all_plugins_using_manifest_keys_offline(self) -> None:
        self.package()
        self.seed_other_builds()
        # Replace AWS at the process boundary: this test cannot contact S3.
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake_aws = bin_dir / "aws"
        fake_aws.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "with open(os.environ['AWS_TEST_LOG'], 'a') as log:\n"
            "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "if sys.argv[3].startswith('s3://'):\n"
            "    sys.exit(1)\n"
            "assert Path(sys.argv[3]).is_file()\n"
        )
        fake_aws.chmod(0o755)
        log = self.root / "aws.jsonl"
        env = {**self.env, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
               "AWS_TEST_LOG": str(log), "ARTIFACTS_BUCKET": "offline-test-bucket",
               "PLUGINS_PREFIX": "custom/plugins"}
        command = ["bash", str(self.scripts / "publish_plugins.sh")]
        subprocess.run(command, check=True, capture_output=True, text=True, env=env, timeout=30)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        result = json.loads((self.build_root / "manifest.json").read_text())
        self.assertEqual(len(calls), 11)  # One fetch, three files per plugin, manifest last.
        self.assertEqual(calls[0], ["s3", "cp", "s3://offline-test-bucket/custom/plugins/manifest.json",
                                    str(self.build_root / "existing-manifest.json")])
        uploads = calls[1:-1]
        for index, plugin in enumerate(result["plugins"]):
            build_dir = self.build_root / plugin["id"]
            build = json.loads((build_dir / "plugin-build.json").read_text())
            for call, local, key, content_type in zip(uploads[index * 3:index * 3 + 3],
                    [build["artifact_local_name"], build["readme_local_name"], build["icon_local_name"]],
                    [plugin["artifact"]["key"], plugin["readme_key"], plugin["icon_key"]],
                    [plugin["artifact"]["content_type"], "text/markdown; charset=utf-8", "image/svg+xml"]):
                self.assertEqual(call, ["s3", "cp", str(build_dir / local),
                                       f"s3://offline-test-bucket/{key}", "--content-type", content_type])
        self.assertEqual(calls[-1], ["s3", "cp", str(self.build_root / "manifest.json"),
                                   "s3://offline-test-bucket/custom/plugins/manifest.json",
                                   "--content-type", "application/json; charset=utf-8"])
        log.unlink()
        (self.output / "plugin-build.json").unlink()
        failed = subprocess.run(command, capture_output=True, text=True, env=env, timeout=30)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("Missing build output for wordpress-ai-search", failed.stderr)
        self.assertFalse(log.exists(), "Preflight must reject missing builds before any AWS call")

    def test_ci_packages_and_collects_every_manifest_plugin(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
        package_job = workflow.split("\n  package_plugins:\n", 1)[1].split("\n  publish_plugins:\n", 1)[0]
        ids = re.search(r"plugin: \[([^\]]+)\]", package_job).group(1)
        self.assertEqual({item.strip() for item in ids.split(",")}, set(manifest.PLUGIN_IDS))
        for plugin_id in manifest.PLUGIN_IDS:
            script = f"package_{plugin_id.replace('-', '_')}_plugin.sh"
            self.assertRegex(package_job, rf"if: matrix\.plugin == '{plugin_id}'\s+run: scripts/downloads/{script}")
            self.assertTrue(os.access(SCRIPTS / script, os.X_OK))
        self.assertIn("cp -R dist/downloads/${{ matrix.plugin }}/. artifact-root/${{ matrix.plugin }}/", package_job)
        self.assertIn("name: plugin-${{ matrix.plugin }}", package_job)
        self.assertIn("path: artifact-root", package_job)
        publish_job = workflow.split("\n  publish_plugins:\n", 1)[1].split("\n  deploy:\n", 1)[0]
        for setting in ("needs: package_plugins", "pattern: plugin-*", "path: dist/downloads",
                        "merge-multiple: true", "run: scripts/downloads/publish_plugins.sh"):
            self.assertIn(setting, publish_job)


if __name__ == "__main__":
    unittest.main()
