"""Exercise the production deploy script against a local fake Railway, never real infrastructure.

Run: python3 -m unittest discover -s scripts -p 'test_*.py' -v
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("deploy_prod_railway.sh")
SERVICES = ["infra-cli-runner", "ollama-embeddings", "InnomightLabs API"]

MOCK_RAILWAY = r'''
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
state_path = Path(os.environ["MOCK_RAILWAY_STATE"])
state = json.loads(state_path.read_text())
service = args[args.index("--service") + 1] if "--service" in args else None
if args[:2] == ["service", "list"]:
    print(json.dumps([{"name": name} for name in state["variables"]]))
elif args[:2] == ["variable", "list"]:
    if os.environ.get("MOCK_VARIABLE_ERROR"):
        print("mock variable lookup failed", file=sys.stderr)
        sys.exit(1)
    if os.environ.get("MOCK_VARIABLE_BAD_JSON"):
        print("invalid json")
    else:
        print(json.dumps(state["variables"][service]))
elif args[:2] == ["variable", "set"]:
    assert "--skip-deploys" in args
    for arg in args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            state["variables"][service][key] = value
elif args[:2] == ["deployment", "list"]:
    print(json.dumps(state["deployments"].get(service, [])))
elif args[0] == "up":
    state["uploads"].append(service)
    state["deployments"][service] = [{
        "id": str(len(state["uploads"])),
        "status": "SUCCESS",
    }]
else:
    raise AssertionError(args)
state_path.write_text(json.dumps(state))
'''


class DeployProductionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.root / "scripts" / SCRIPT.name)
        self.executable("scripts/generate_tfvars.sh", "#!/bin/sh\nexit 0\n")
        self.executable(
            "scripts/next_version.sh",
            f"#!{sys.executable}\nfrom pathlib import Path\n"
            "p = Path('version-counter')\n"
            "n = int(p.read_text()) + 1 if p.exists() else 1\n"
            "p.write_text(str(n))\nprint('1.0.' + str(n))\n",
        )
        (self.root / ".envrc").write_text("export PROD_API_BASE_URL=https://example.invalid\n")
        for directory in ["api", "infra-cli-runner", "ollama-embeddings"]:
            (self.root / directory).mkdir()
            (self.root / directory / "app.txt").write_text("unchanged\n")
        self.real_git = shutil.which("git")
        subprocess.run([self.real_git, "init", "-q", str(self.root)], check=True)
        (self.root / "bin").mkdir()
        self.executable("bin/railway", f"#!{sys.executable}\n" + MOCK_RAILWAY)
        self.executable("bin/sleep", "#!/bin/sh\nexit 0\n")
        # Do not create/push real release tags during tests.
        self.executable(
            "bin/git",
            f"#!{sys.executable}\nimport subprocess, sys\n"
            "if 'tag' not in sys.argv[1:] and 'push' not in sys.argv[1:]:\n"
            f"    sys.exit(subprocess.call([{self.real_git!r}] + sys.argv[1:]))\n",
        )
        self.state_path = self.root / "railway-state.json"
        self.save_state({"variables": {s: {} for s in SERVICES}, "deployments": {}, "uploads": []})
        self.env = {k: v for k, v in os.environ.items() if k in {"HOME", "LANG", "TMPDIR"}}
        self.env.update(
            PATH=str(self.root / "bin") + os.pathsep + os.environ["PATH"],
            MOCK_RAILWAY_STATE=str(self.state_path),
        )

    def executable(self, name: str, content: str) -> None:
        path = self.root / name
        path.write_text(content)
        path.chmod(0o755)

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())

    def save_state(self, state: dict) -> None:
        self.state_path.write_text(json.dumps(state))

    def deploy(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["bash", "scripts/deploy_prod_railway.sh"],
            cwd=self.root,
            env={**self.env, **overrides},
            input="yes\n",
            text=True,
            capture_output=True,
            timeout=60,
        )
        return result

    def successful_deploy(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        result = self.deploy(**overrides)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_initial_token_is_reused_and_second_run_deploys_nothing(self) -> None:
        first = self.successful_deploy()
        state = self.state()
        self.assertEqual(state["uploads"], SERVICES)
        token = state["variables"]["infra-cli-runner"]["CLI_RUNNER_SHARED_TOKEN"]
        self.assertTrue(token)
        self.assertEqual(state["variables"]["InnomightLabs API"]["CLI_RUNNER_SHARED_TOKEN"], token)
        second = self.successful_deploy()
        self.assertEqual(self.state()["uploads"], SERVICES)
        self.assertEqual(self.state()["variables"]["infra-cli-runner"]["CLI_RUNNER_SHARED_TOKEN"], token)
        self.assertNotIn(token, first.stdout + first.stderr + second.stdout + second.stderr)
        self.assertEqual((self.root / "version-counter").read_text(), "2")

    def test_existing_railway_token_is_preserved(self) -> None:
        state = self.state()
        state["variables"]["infra-cli-runner"]["CLI_RUNNER_SHARED_TOKEN"] = "existing-test-token"
        self.save_state(state)
        self.successful_deploy()
        self.assertEqual(self.state()["variables"]["InnomightLabs API"]["CLI_RUNNER_SHARED_TOKEN"], "existing-test-token")

    def test_explicit_token_rotation_redeploys_only_runner_and_api(self) -> None:
        self.successful_deploy()
        self.successful_deploy(PROD_CLI_RUNNER_SHARED_TOKEN="rotated-test-token")
        self.assertEqual(self.state()["uploads"][3:], ["infra-cli-runner", "InnomightLabs API"])
        self.successful_deploy(PROD_CLI_RUNNER_SHARED_TOKEN="rotated-test-token")
        self.assertEqual(len(self.state()["uploads"]), 5)

    def test_changed_files_deploy_only_the_affected_service(self) -> None:
        self.successful_deploy()
        for directory, service in [("infra-cli-runner", "infra-cli-runner"), ("api", "InnomightLabs API"), ("ollama-embeddings", "ollama-embeddings")]:
            with self.subTest(service=service):
                before = len(self.state()["uploads"])
                (self.root / directory / "app.txt").write_text("changed\n")
                self.successful_deploy()
                self.assertEqual(self.state()["uploads"][before:], [service])

    def test_force_deploy_still_redeploys_all_services(self) -> None:
        self.successful_deploy()
        self.successful_deploy(FORCE_DEPLOY="true")
        self.assertEqual(self.state()["uploads"], SERVICES * 2)

    def test_lookup_failure_aborts_without_rotating_or_deploying(self) -> None:
        state = self.state()
        state["variables"]["infra-cli-runner"]["CLI_RUNNER_SHARED_TOKEN"] = "existing-test-token"
        self.save_state(state)
        for error in ["MOCK_VARIABLE_ERROR", "MOCK_VARIABLE_BAD_JSON"]:
            with self.subTest(error=error):
                result = self.deploy(**{error: "1"})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.state(), state)
                self.assertNotIn("Generated an initial", result.stdout)


if __name__ == "__main__":
    unittest.main()
