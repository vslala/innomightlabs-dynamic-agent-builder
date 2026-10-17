from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from src.infra_cli_runner.models import PythonExecutionRequest
from src.infra_cli_runner.service import CliRunnerService, ProcessOutcome, PYTHON_POLICY_DIRECTORY


def request(**overrides: object) -> PythonExecutionRequest:
    return PythonExecutionRequest.model_validate({
        "request_id": "browser-test", "script": "print('ok')",
        "commands": [{"operation": "run_script"}], **overrides,
    })


class BrowserValidationTests(unittest.TestCase):
    def test_pin_is_unconditional_and_names_are_normalized(self) -> None:
        for requirements in ("", "PlayWright>=1.60", "playwright==1.64.0; python_version < '1'"):
            with self.subTest(requirements=requirements):
                value = request(browser=True, requirements=requirements)
                self.assertIn("playwright==1.64.0", value.requirements.splitlines())

    def test_incompatible_pin_is_rejected_even_with_false_marker(self) -> None:
        for requirements in ("PlayWright<1.64", "playwright!=1.64.0; python_version < '1'"):
            with self.subTest(requirements=requirements), self.assertRaises(ValidationError):
                request(browser=True, requirements=requirements)

    def test_normal_requirements_are_unchanged(self) -> None:
        self.assertEqual(request(requirements="playwright==1.50.0").requirements, "playwright==1.50.0")

    def test_timeout_caps(self) -> None:
        with patch.dict(os.environ, {"CLI_RUNNER_MAX_TIMEOUT_SECONDS": "90"}):
            self.assertEqual(request(timeout_seconds=999).timeout_seconds, 90)
            self.assertEqual(request(browser=True, timeout_seconds=999).timeout_seconds, 300)
            self.assertEqual(request(browser=True, timeout_seconds=240).timeout_seconds, 240)
            self.assertEqual(request(browser=True).timeout_seconds, 60)
            self.assertEqual(request(browser=True, timeout_seconds=0).timeout_seconds, 1)


class BrowserServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_install_order_and_environment(self) -> None:
        cases = [
            (False, ["run_script"], ["create_environment", "run_script"]),
            (True, ["run_script", "run_script"], ["create_environment", "install_requirements", "run_script", "run_script"]),
            (True, ["install_requirements", "run_script"], ["create_environment", "install_requirements", "run_script"]),
            (True, ["run_script", "install_requirements"], ["create_environment", "install_requirements", "run_script", "install_requirements"]),
        ]
        for browser, commands, expected in cases:
            with self.subTest(browser=browser, commands=commands), tempfile.TemporaryDirectory(dir="/tmp") as root:
                service = CliRunnerService(python_work_root=Path(root))
                seen = []

                async def execute(argv: object, **kwargs: object) -> ProcessOutcome:
                    seen.append(kwargs)
                    return ProcessOutcome(0, "", "", 0, False, False, False)

                with patch.object(service, "_execute_with_deadline", side_effect=execute):
                    result = await service.run_python(request(browser=browser, commands=[{"operation": op} for op in commands]))
                self.assertTrue(result.ok)
                self.assertEqual([item.operation for item in result.commands], expected)
                self.assertEqual([item.index for item in result.commands], list(range(len(expected))))
                for call in seen:
                    self.assertEqual("PLAYWRIGHT_BROWSERS_PATH" in call["env"], browser)
                    self.assertEqual("INFRA_CLI_RUNNER_BROWSER_VENV" in call["env"], browser)

    async def test_automatic_install_failure_skips_scripts(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as root:
            service = CliRunnerService(python_work_root=Path(root))
            outcomes = [ProcessOutcome(0, "", "", 0, False, False, False), ProcessOutcome(1, "", "install failed", 0, False, False, False)]
            with patch.object(service, "_execute_with_deadline", side_effect=outcomes):
                result = await service.run_python(request(browser=True))
            self.assertFalse(result.ok)
            self.assertEqual(result.failed_command_index, 1)
            self.assertEqual(result.commands[2].status, "skipped")


class BrowserPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.venv = self.root / "run" / ".venv"
        self.node = self.venv / "lib/python3.13/site-packages/playwright/driver/node"
        self.node.parent.mkdir(parents=True)
        self.node.write_text("#!/bin/sh\necho approved-node\n")
        self.node.chmod(0o755)

    def run_policy(self, script: str, *, browser: bool = True) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(PYTHON_POLICY_DIRECTORY.resolve())
        env["INFRA_CLI_RUNNER_WRITE_ROOT"] = str(self.root)
        env.pop("INFRA_CLI_RUNNER_BROWSER_VENV", None)
        if browser:
            env["INFRA_CLI_RUNNER_BROWSER_VENV"] = str(self.venv)
        return subprocess.run([sys.executable, "-c", script], env=env, cwd=self.root, capture_output=True, text=True, timeout=15)

    def test_only_exact_node_is_allowed(self) -> None:
        result = self.run_policy(f"import subprocess; subprocess.run([{str(self.node)!r}], check=True)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("approved-node", result.stdout)
        for executable in ("/bin/echo", "node", str(self.node)):
            with self.subTest(executable=executable):
                result = self.run_policy(f"import subprocess; subprocess.run([{executable!r}])", browser=executable != str(self.node))
                self.assertNotEqual(result.returncode, 0)

    def test_node_symlink_escape_is_rejected(self) -> None:
        self.node.unlink()
        self.node.symlink_to("/bin/echo")
        result = self.run_policy(f"import subprocess; subprocess.run([{str(self.node)!r}])")
        self.assertIn("Child process execution is not allowed", result.stderr)

    def test_virtual_environment_and_ancestors_are_read_only(self) -> None:
        scripts = [
            f"open({str(self.node)!r}, 'w')",
            f"os.chmod({str(self.node)!r}, 0o777)",
            f"os.unlink({str(self.node)!r})",
            f"os.rename({str(self.venv)!r}, {str(self.root / 'moved')!r})",
            f"os.rename({str(self.venv.parent)!r}, {str(self.root / 'moved')!r})",
            f"os.rmdir({str(self.venv.parent)!r})",
            f"os.symlink('/tmp', {str(self.venv / 'escape')!r})",
            f"os.replace({str(self.root / 'other')!r}, {str(self.venv)!r})",
        ]
        for script in scripts:
            with self.subTest(script=script):
                result = self.run_policy("import os; " + script)
                self.assertIn("read-only", result.stderr)
        result = self.run_policy("open('output.txt', 'w').write('ok')")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_virtual_environment_symlink_entry_is_read_only(self) -> None:
        outside = self.root / "output.txt"
        outside.write_text("keep")
        link = self.venv / "linked-output"
        link.symlink_to(outside)
        result = self.run_policy(f"import os; os.unlink({str(link)!r})")
        self.assertIn("read-only", result.stderr)
        self.assertTrue(link.is_symlink())
        result = self.run_policy(f"print(open({str(link)!r}).read())")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "keep")

    def test_driver_directory_symlink_escape_is_rejected(self) -> None:
        driver = self.node.parent
        external = self.root / "external-driver"
        driver.rename(external)
        driver.symlink_to(external, target_is_directory=True)
        result = self.run_policy(f"import subprocess; subprocess.run([{str(self.node)!r}])")
        self.assertIn("Child process execution is not allowed", result.stderr)

    def test_process_primitives_remain_blocked(self) -> None:
        for event in ("os.exec", "os.fork", "os.forkpty", "os.posix_spawn", "os.spawn", "os.system"):
            with self.subTest(event=event):
                result = self.run_policy(f"import sys; sys.audit({event!r})")
                self.assertIn("Child process execution is not allowed", result.stderr)

    def test_low_level_import_is_browser_only(self) -> None:
        self.assertEqual(self.run_policy("import _posixsubprocess").returncode, 0)
        self.assertIn("Low-level process execution", self.run_policy("import _posixsubprocess", browser=False).stderr)


class ChromiumIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_chromium_page_and_screenshot(self) -> None:
        if importlib.util.find_spec("playwright") is None:
            self.skipTest("Playwright is not installed")
        from importlib.metadata import version
        if version("playwright") != "1.64.0":
            self.skipTest("Playwright 1.64.0 is not installed")
        from playwright.async_api import async_playwright
        with patch.dict(os.environ, {"PLAYWRIGHT_BROWSERS_PATH": os.getenv("PLAYWRIGHT_BROWSERS_PATH", "/opt/ms-playwright")}):
            async with async_playwright() as playwright:
                if not Path(playwright.chromium.executable_path).is_file():
                    self.skipTest("Playwright Chromium is not installed")
        with tempfile.TemporaryDirectory(dir="/tmp") as root:
            service = CliRunnerService(python_work_root=Path(root))
            # Reuse the installed wheel offline, while exercising real venv setup and policy.
            original = service._python_command_argv

            def argv(command, **kwargs):
                if command.operation == "install_requirements":
                    import playwright
                    target = kwargs["virtual_env_python"].parent.parent / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
                    source = Path(playwright.__file__).parent.parent
                    for name in ("playwright", "greenlet", "pyee", "typing_extensions.py"):
                        path = source / name
                        if path.is_dir():
                            shutil.copytree(path, target / name)
                        elif path.is_file():
                            shutil.copy2(path, target / name)
                    return ["/usr/bin/true"]
                return original(command, **kwargs)

            script = """from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.set_content('<title>browser-test</title><h1>Hello</h1>')
    assert page.title() == 'browser-test'
    page.screenshot(path='page.png')
    browser.close()
print('chromium-ok')
"""
            with patch.object(service, "_python_command_argv", side_effect=argv):
                result = await service.run_python(request(browser=True, script=script))
            self.assertTrue(result.ok, result.stderr)
            self.assertIn("chromium-ok", result.stdout)
