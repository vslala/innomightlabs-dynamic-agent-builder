from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from main import app
from src.infra_cli_runner.models import PythonExecutionRequest
from src.infra_cli_runner.service import CliRunnerService, CommandExecutionError


class PythonExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.work_root = Path("/tmp") / f"infra-cli-runner-tests-{uuid4()}"
        self.service = CliRunnerService(
            python_work_root=self.work_root,
            python_executable=sys.executable,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.work_root, ignore_errors=True)

    async def test_success_uses_internal_tmp_working_directory(self) -> None:
        response = await self.service.run_python(
            self.request(
                script=(
                    "from pathlib import Path\n"
                    "import sys\n"
                    "Path('result.txt').write_text('ok')\n"
                    "print(Path.cwd())\n"
                    "print(Path(sys.prefix).name)"
                )
            )
        )

        self.assertTrue(response.ok)
        self.assertEqual(response.exit_code, 0)
        self.assertEqual(response.commands[0].status, "succeeded")
        self.assertEqual(response.commands[0].operation, "create_environment")
        self.assertEqual(response.commands[1].status, "succeeded")
        self.assertTrue(response.stdout.splitlines()[0].startswith(str(self.work_root.resolve())))
        self.assertEqual(response.stdout.splitlines()[1], ".venv")
        self.assertEqual(list(self.work_root.iterdir()), [])

    async def test_requirements_install_then_script(self) -> None:
        response = await self.service.run_python(
            self.request(
                script="print('installed then ran')",
                requirements="typing-extensions==4.15.0; python_version < '1'",
                commands=[
                    {"operation": "install_requirements"},
                    {"operation": "run_script"},
                ],
            )
        )

        self.assertTrue(response.ok, response.stderr)
        self.assertEqual(
            [result.status for result in response.commands],
            ["succeeded", "succeeded", "succeeded"],
        )
        self.assertIn("installed then ran", response.commands[2].stdout)

    async def test_commands_execute_sequentially_in_one_run(self) -> None:
        script = """
from pathlib import Path
import sys
state = Path("state.txt")
if sys.argv[1] == "write":
    state.write_text("first")
else:
    print(state.read_text() + "-second")
"""
        response = await self.service.run_python(
            self.request(
                script=script,
                commands=[
                    {"operation": "run_script", "args": ["write"]},
                    {"operation": "run_script", "args": ["read"]},
                ],
            )
        )

        self.assertTrue(response.ok)
        self.assertEqual(response.commands[2].stdout, "first-second\n")

    async def test_failure_is_reported_and_later_commands_are_skipped(self) -> None:
        script = """
import sys
print(sys.argv[1])
if sys.argv[1] == "fail":
    print("failure details", file=sys.stderr)
    raise SystemExit(7)
"""
        response = await self.service.run_python(
            self.request(
                script=script,
                commands=[
                    {"operation": "run_script", "args": ["fail"]},
                    {"operation": "run_script", "args": ["must-not-run"]},
                ],
            )
        )

        self.assertFalse(response.ok)
        self.assertEqual(response.exit_code, 7)
        self.assertEqual(response.failed_command_index, 1)
        self.assertEqual(response.commands[0].status, "succeeded")
        self.assertEqual(response.commands[1].status, "failed")
        self.assertEqual(response.commands[1].stdout, "fail\n")
        self.assertEqual(response.commands[1].stderr, "failure details\n")
        self.assertEqual(response.commands[2].status, "skipped")
        self.assertIsNone(response.commands[2].exit_code)

    async def test_timeout_terminates_process_and_skips_later_commands(self) -> None:
        response = await self.service.run_python(
            self.request(
                script="import time\ntime.sleep(10)",
                commands=[
                    {"operation": "run_script"},
                    {"operation": "run_script"},
                ],
                timeout_seconds=1,
            )
        )

        self.assertFalse(response.ok)
        self.assertTrue(response.timed_out)
        self.assertEqual(response.failed_command_index, 1)
        self.assertEqual(response.commands[0].status, "succeeded")
        self.assertEqual(response.commands[1].status, "timed_out")
        self.assertTrue(response.commands[1].timed_out)
        self.assertEqual(response.commands[2].status, "skipped")
        self.assertLess(response.duration_ms, 4000)

    async def test_python_policy_rejects_write_outside_managed_tmp_directory(self) -> None:
        response = await self.service.run_python(
            self.request(script="open('/var/tmp/not-allowed.txt', 'w').write('no')")
        )

        self.assertFalse(response.ok)
        self.assertEqual(response.commands[1].status, "failed")
        self.assertIn("Writes are restricted", response.stderr)

    async def test_python_policy_rejects_directory_fd_write_escape(self) -> None:
        script = """
import os
directory = os.open("/var/tmp", os.O_RDONLY)
os.open("not-allowed.txt", os.O_WRONLY | os.O_CREAT, dir_fd=directory)
"""
        response = await self.service.run_python(self.request(script=script))

        self.assertFalse(response.ok)
        self.assertIn("Relative low-level writes are not allowed", response.stderr)

    async def test_python_policy_rejects_child_processes(self) -> None:
        response = await self.service.run_python(
            self.request(script="import subprocess\nsubprocess.run(['echo', 'no'])")
        )

        self.assertFalse(response.ok)
        self.assertIn("process execution is not allowed", response.stderr)

    async def test_python_policy_allows_native_library_loading(self) -> None:
        response = await self.service.run_python(
            self.request(
                script=(
                    "import ctypes\n"
                    "library = ctypes.CDLL(None)\n"
                    "print(type(library).__name__)"
                )
            )
        )

        self.assertTrue(response.ok, response.stderr)
        self.assertEqual(response.commands[1].status, "succeeded")
        self.assertEqual(response.stdout, "CDLL\n")

    async def test_work_root_outside_tmp_is_rejected(self) -> None:
        service = CliRunnerService(python_work_root=Path("/var/tmp/not-managed"))

        with self.assertRaisesRegex(CommandExecutionError, "must resolve under /tmp"):
            await service.run_python(self.request(script="print('no')"))

    async def test_environment_failure_skips_requested_commands(self) -> None:
        service = CliRunnerService(
            python_work_root=self.work_root,
            python_executable=sys.executable,
            uv_executable="/usr/bin/false",
        )

        response = await service.run_python(self.request(script="print('no')"))

        self.assertFalse(response.ok)
        self.assertEqual(response.failed_command_index, 0)
        self.assertEqual(response.commands[0].operation, "create_environment")
        self.assertEqual(response.commands[0].status, "failed")
        self.assertEqual(response.commands[1].status, "skipped")

    def test_request_defaults_to_sixty_seconds(self) -> None:
        self.assertEqual(self.request(script="print('ok')").timeout_seconds, 60)

    def test_python_execution_endpoint_is_in_openapi_contract(self) -> None:
        operation = app.openapi()["paths"]["/v1/python/executions"]["post"]

        response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        self.assertEqual(
            response_schema["$ref"],
            "#/components/schemas/PythonExecutionResponse",
        )

    def test_requirements_reject_options_urls_and_local_paths(self) -> None:
        for requirements in (
            "-r /etc/passwd",
            "example @ https://example.com/example.whl",
            "../local-package",
        ):
            with self.subTest(requirements=requirements), self.assertRaises(ValidationError):
                self.request(script="print('no')", requirements=requirements)

    def request(self, **overrides: object) -> PythonExecutionRequest:
        payload: dict[str, object] = {
            "request_id": "test-run",
            "script": "print('ok')",
            "requirements": "",
            "commands": [{"operation": "run_script"}],
        }
        payload.update(overrides)
        return PythonExecutionRequest.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
