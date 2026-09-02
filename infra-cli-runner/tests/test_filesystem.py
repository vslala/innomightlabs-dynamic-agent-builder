from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path
from uuid import uuid4

from src.infra_cli_runner.filesystem import FileSystemService
from src.infra_cli_runner.models import FileSystemActionRequest, PythonExecutionRequest
from src.infra_cli_runner.service import CliRunnerService
from main import app


WORKSPACE_ID = "a" * 48


class FileSystemTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.test_root = Path("/tmp") / f"filesystem-runner-tests-{uuid4()}"
        self.workspace_root = self.test_root / "workspaces"
        self.service = FileSystemService(
            workspace_root=self.workspace_root,
            max_read_bytes=1024,
            max_write_bytes=1024,
            workspace_quota_bytes=4096,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.test_root, ignore_errors=True)

    def test_blocks_traversal_encoded_traversal_unicode_and_symlink_escape(self) -> None:
        for path in ("../outside", "..%2Foutside", "/etc/passwd"):
            with self.subTest(path=path):
                result = self.call("stat", {"path": path})
                self.assertEqual(result.status, "error")
                self.assertIn(result.error_code, {"invalid_path", "sandbox_violation"})

        decomposed = "cafe\u0301.txt"
        result = self.call("stat", {"path": decomposed})
        self.assertEqual(result.error_code, "invalid_path")

        workspace = self.service.workspace(WORKSPACE_ID)
        (workspace / "escape").symlink_to("/tmp")
        result = self.call("stat", {"path": "escape"})
        self.assertEqual(result.error_code, "sandbox_violation")

    def test_chunked_reads_return_cursor_and_binary_is_rejected(self) -> None:
        content = "".join(f"line-{index:04d}\n" for index in range(300))
        self.assertEqual(self.call("write_file", {"path": "report.txt", "content": content[:1000]}).status, "success")
        first = self.call("read_chunk", {"path": "report.txt", "max_bytes": 100, "max_lines": 5})
        self.assertEqual(first.status, "success")
        self.assertTrue(first.payload["has_more"])
        self.assertIsNotNone(first.next_cursor)
        second = self.call("read_chunk", {"path": "report.txt", "cursor": first.next_cursor, "max_bytes": 100})
        self.assertEqual(second.payload["byte_offset"], first.payload["bytes_returned"])

        workspace = self.service.workspace(WORKSPACE_ID)
        (workspace / "binary.bin").write_bytes(b"abc\x00def")
        result = self.call("read_chunk", {"path": "binary.bin"})
        self.assertEqual(result.error_code, "binary_file")

    def test_write_limits_quota_and_atomic_modes(self) -> None:
        oversized = self.call("write_file", {"path": "large.txt", "content": "x" * 1025})
        self.assertEqual(oversized.error_code, "write_limit_exceeded")

        created = self.call("write_file", {"path": "a.txt", "content": "first"})
        self.assertEqual(created.status, "success")
        duplicate = self.call("write_file", {"path": "a.txt", "content": "second"})
        self.assertEqual(duplicate.error_code, "already_exists")
        overwritten = self.call(
            "write_file",
            {"path": "a.txt", "content": "second", "mode": "overwrite"},
        )
        self.assertEqual(overwritten.status, "success")
        self.assertEqual((self.service.workspace(WORKSPACE_ID) / "a.txt").read_text(), "second")

        quota_service = FileSystemService(
            workspace_root=self.test_root / "quota",
            max_write_bytes=1024,
            workspace_quota_bytes=1024,
        )
        first = quota_service.execute(self.request("write_file", {"path": "one", "content": "x" * 800}))
        second = quota_service.execute(self.request("write_file", {"path": "two", "content": "y" * 800}))
        self.assertEqual(first.status, "success")
        self.assertEqual(second.error_code, "workspace_quota_exceeded")

    def test_preview_patch_conflict_search_and_compact_listing(self) -> None:
        self.call("mkdir", {"path": "reports"})
        self.call("write_file", {"path": "reports/data.txt", "content": "alpha\nbeta\n"})
        patch = "--- a/reports/data.txt\n+++ b/reports/data.txt\n@@ -1,2 +1,2 @@\n alpha\n-beta\n+gamma\n"
        preview = self.call("preview_diff", {"path": "reports/data.txt", "patch": patch})
        self.assertEqual(preview.status, "success")
        self.assertIn("+gamma", preview.payload["diff"])
        self.assertEqual((self.service.workspace(WORKSPACE_ID) / "reports/data.txt").read_text(), "alpha\nbeta\n")

        applied = self.call("patch_file", {"path": "reports/data.txt", "patch": patch})
        self.assertEqual(applied.status, "success")
        conflict = self.call("patch_file", {"path": "reports/data.txt", "patch": patch})
        self.assertEqual(conflict.error_code, "patch_conflict")
        self.assertIn("actual", conflict.payload)

        search = self.call("search", {"path": "reports", "glob": "**/*", "query": "gamma"})
        self.assertEqual(search.status, "success")
        self.assertEqual(search.payload["matches"][0]["path"], "reports/data.txt")
        listing = self.call("list_dir", {"path": "", "recursive": True})
        self.assertEqual([entry["path"] for entry in listing.payload["entries"]], ["reports", "reports/data.txt"])

    def test_copy_move_delete_and_batch_execute_without_approval_policy(self) -> None:
        self.call("mkdir", {"path": "source"})
        self.call("write_file", {"path": "source/a.txt", "content": "a"})
        copied = self.call("copy", {"source": "source", "destination": "copy"})
        self.assertEqual(copied.status, "success")
        self.assertEqual(self.call("move", {"source": "copy", "destination": "moved"}).status, "success")
        self.assertEqual(self.call("delete", {"path": "moved", "recursive": True}).status, "success")

        batch = self.call(
            "batch",
            {
                "operations": [
                    {"action": "write_file", "arguments": {"path": "one.txt", "content": "1"}},
                    {"action": "read_chunk", "arguments": {"path": "one.txt"}},
                ]
            },
        )
        self.assertEqual(batch.status, "success")
        self.assertEqual(batch.payload["completed"], 2)

        destructive_batch = self.call(
            "batch",
            {
                "operations": [
                    {"action": "write_file", "arguments": {"path": "must-not-exist.txt", "content": "no"}},
                    {"action": "delete", "arguments": {"path": "one.txt"}},
                ]
            },
        )
        self.assertEqual(destructive_batch.status, "success")
        self.assertTrue((self.service.workspace(WORKSPACE_ID) / "must-not-exist.txt").exists())
        self.assertFalse((self.service.workspace(WORKSPACE_ID) / "one.txt").exists())

    async def test_python_outputs_are_available_to_filesystem_workflow(self) -> None:
        python_service = CliRunnerService(
            python_work_root=self.test_root / "python",
            workspace_root=self.workspace_root,
            python_executable=sys.executable,
        )
        response = await python_service.run_python(
            PythonExecutionRequest.model_validate(
                {
                    "request_id": "shared-workspace",
                    "workspace_id": WORKSPACE_ID,
                    "script": "from pathlib import Path\nPath('report.csv').write_text('name,value\\nalpha,1\\n')",
                    "commands": [{"operation": "run_script"}],
                }
            )
        )
        self.assertTrue(response.ok, response.stderr)
        result = self.call("read_chunk", {"path": "report.csv"})
        self.assertEqual(result.status, "success")
        self.assertEqual(result.payload["content"], "name,value\nalpha,1\n")
        self.assertFalse((self.service.workspace(WORKSPACE_ID) / ".runs").exists())

    def test_filesystem_endpoint_is_in_openapi_contract(self) -> None:
        operation = app.openapi()["paths"]["/v1/filesystem/actions"]["post"]
        response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        self.assertEqual(response_schema["$ref"], "#/components/schemas/FileSystemActionResponse")

    def call(self, action: str, arguments: dict[str, object]):
        return self.service.execute(self.request(action, arguments))

    def request(
        self,
        action: str,
        arguments: dict[str, object],
    ) -> FileSystemActionRequest:
        return FileSystemActionRequest.model_validate(
            {
                "request_id": "test-request",
                "workspace_id": WORKSPACE_ID,
                "action": action,
                "arguments": arguments,
            }
        )


if __name__ == "__main__":
    unittest.main()
