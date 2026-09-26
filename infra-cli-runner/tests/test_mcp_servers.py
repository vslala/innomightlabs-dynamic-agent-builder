from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from src.infra_cli_runner import mcp_servers, router
from src.infra_cli_runner.mcp_servers import (
    PoolFullError,
    ServerNotRunningError,
    StdioMCPServerPool,
    UnknownPackageError,
    load_packages,
)
from src.infra_cli_runner.models import EnsureHostedMCPServerRequest, HostedMCPServerSpec
from src.infra_cli_runner.service import CliRunnerService

FAKE_SERVER = Path(__file__).with_name("fake_mcp_server.py")
TOKEN = "Bearer test-token"


def make_package_roots(root: Path) -> tuple[Path, Path]:
    """Lay out mcp_packages/fake and a venv whose entrypoint runs the fake server."""
    packages_root = root / "mcp_packages"
    (packages_root / "fake").mkdir(parents=True)
    (packages_root / "fake" / "package.toml").write_text('entrypoint = "fake-mcp"\n', encoding="utf-8")
    venv_root = root / "venvs"
    entrypoint = venv_root / "fake" / "bin" / "fake-mcp"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text(f"#!{sys.executable}\nexec(open({str(FAKE_SERVER)!r}).read())\n", encoding="utf-8")
    entrypoint.chmod(0o755)
    return packages_root, venv_root


def tool_call(name: str, arguments: dict[str, Any] | None = None, request_id: Any = 1) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }


def text_of(response: dict[str, Any] | None) -> str:
    assert response is not None
    return str(response["result"]["content"][0]["text"])


class HostedMCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.root = Path("/tmp") / f"infra-cli-runner-mcp-tests-{uuid4()}"
        packages_root, venv_root = make_package_roots(self.root)
        self.pool = StdioMCPServerPool(
            packages_root=packages_root,
            venv_root=venv_root,
            servers_root=self.root / "servers",
        )

    async def asyncTearDown(self) -> None:
        await self.pool.close()
        shutil.rmtree(self.root, ignore_errors=True)

    async def start(self, server_id: str | None = None, **spec: Any) -> str:
        server_id = server_id or str(uuid4())
        status = await self.pool.ensure(server_id, HostedMCPServerSpec(package="fake", **spec), wait_seconds=10)
        self.assertEqual(status.state, "running", status.error)
        return server_id

    async def test_packages_are_read_from_the_package_directory(self) -> None:
        packages = load_packages(self.root / "mcp_packages", self.root / "venvs")

        self.assertEqual(list(packages), ["fake"])
        self.assertTrue(self.pool.list_packages()[0].installed)

    async def test_handshake_runs_once_and_initialize_is_answered_from_cache(self) -> None:
        server_id = await self.start()

        initialize = await self.pool.forward(server_id, {"jsonrpc": "2.0", "id": "caller-1", "method": "initialize"})
        initialized = await self.pool.forward(server_id, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = await self.pool.forward(server_id, {"jsonrpc": "2.0", "id": 9, "method": "tools/list", "params": {}})

        assert initialize is not None and tools is not None
        self.assertEqual(initialize["id"], "caller-1")
        self.assertEqual(initialize["result"]["serverInfo"], {"name": "fake-mcp", "version": "1.2.3"})
        self.assertIsNone(initialized)
        self.assertEqual(tools["id"], 9)
        self.assertEqual([tool["name"] for tool in tools["result"]["tools"]], ["echo", "env"])
        status = self.pool.status(server_id)
        assert status is not None
        self.assertEqual(status.server_info, {"name": "fake-mcp", "version": "1.2.3"})
        self.assertIn("stderr log line", status.stderr_tail)

    async def test_concurrent_callers_reusing_ids_get_their_own_responses(self) -> None:
        server_id = await self.start()

        slow, fast = await asyncio.gather(
            self.pool.forward(server_id, tool_call("echo", {"text": "slow", "delay": 0.3}, request_id=1)),
            self.pool.forward(server_id, tool_call("echo", {"text": "fast"}, request_id=1)),
        )

        self.assertEqual(text_of(slow), "slow")
        self.assertEqual(text_of(fast), "fast")
        assert slow is not None and fast is not None
        self.assertEqual((slow["id"], fast["id"]), (1, 1))

    async def test_server_to_client_requests_are_refused(self) -> None:
        server_id = await self.start()

        response = await self.pool.forward(server_id, tool_call("ask_client"))

        self.assertEqual(json.loads(text_of(response))["error"]["code"], -32601)

    async def test_crash_fails_pending_requests_and_reports_why(self) -> None:
        server_id = await self.start()

        with self.assertRaises(ServerNotRunningError):
            await self.pool.forward(server_id, tool_call("crash"))

        status = self.pool.status(server_id)
        assert status is not None
        self.assertEqual(status.state, "failed")
        self.assertEqual(status.exit_code, 7)
        self.assertIn("crashing on purpose", status.stderr_tail)
        with self.assertRaises(ServerNotRunningError):
            await self.pool.forward(server_id, tool_call("echo"))

    async def test_failed_start_is_reported(self) -> None:
        status = await self.pool.ensure(
            str(uuid4()),
            HostedMCPServerSpec(package="fake", env={"FAKE_EXIT_AT_START": "1"}),
            wait_seconds=10,
        )

        self.assertEqual(status.state, "failed")
        self.assertEqual(status.exit_code, 3)
        self.assertIn("refusing to start", status.stderr_tail)

    async def test_same_spec_reuses_the_process_and_a_new_spec_restarts_it(self) -> None:
        server_id = await self.start(env={"TOKEN": "one"})
        first = self.pool._servers[server_id]

        await self.start(server_id, env={"TOKEN": "one"})
        self.assertIs(self.pool._servers[server_id], first)

        await self.start(server_id, env={"TOKEN": "two"})
        second = self.pool._servers[server_id]
        self.assertIsNot(second, first)
        self.assertEqual(first.state, "stopped")
        env = json.loads(text_of(await self.pool.forward(server_id, tool_call("env"))))
        self.assertEqual(env["TOKEN"], "two")

    async def test_restart_waits_for_in_flight_requests(self) -> None:
        server_id = await self.start(env={"TOKEN": "one"})

        in_flight = asyncio.create_task(
            self.pool.forward(server_id, tool_call("echo", {"text": "finished", "delay": 0.5}))
        )
        await asyncio.sleep(0.1)
        await self.start(server_id, env={"TOKEN": "two"})

        self.assertEqual(text_of(await in_flight), "finished")

    async def test_child_env_is_sanitized_and_isolated(self) -> None:
        with mock.patch.dict(os.environ, {"CLI_RUNNER_SHARED_TOKEN": "runner-secret"}):
            server_id = await self.start(env={"GOOGLE_ADS_DEVELOPER_TOKEN": "dev-token"})

        env = json.loads(text_of(await self.pool.forward(server_id, tool_call("env"))))

        self.assertNotIn("CLI_RUNNER_SHARED_TOKEN", env)
        self.assertEqual(env["GOOGLE_ADS_DEVELOPER_TOKEN"], "dev-token")
        self.assertEqual(env["HOME"], str(self.root / "servers" / server_id / "home"))
        self.assertTrue(env["PATH"].startswith(str(self.root / "venvs" / "fake" / "bin")))

    async def test_credential_files_are_private_and_removed_on_delete(self) -> None:
        server_id = await self.start(files={"GOOGLE_APPLICATION_CREDENTIALS": '{"type": "authorized_user"}'})

        read = json.loads(
            text_of(await self.pool.forward(server_id, tool_call("read_file", {"env": "GOOGLE_APPLICATION_CREDENTIALS"})))
        )
        await self.pool.delete(server_id)

        self.assertEqual(read, {"content": '{"type": "authorized_user"}', "mode": "0o600"})
        self.assertIsNone(self.pool.status(server_id))
        self.assertFalse((self.root / "servers" / server_id).exists())

    async def test_idle_servers_are_reaped(self) -> None:
        server_id = await self.start()
        self.pool.idle_timeout_seconds = 0

        await self.pool.reap_idle()

        self.assertIsNone(self.pool.status(server_id))

    async def test_full_pool_evicts_the_least_recently_used_idle_server(self) -> None:
        self.pool.max_running = 1
        first = await self.start()

        second = await self.start()

        self.assertIsNone(self.pool.status(first))
        status = self.pool.status(second)
        assert status is not None
        self.assertEqual(status.state, "running")

    async def test_full_pool_refuses_when_every_server_is_busy(self) -> None:
        self.pool.max_running = 1
        first = await self.start()
        busy = asyncio.create_task(self.pool.forward(first, tool_call("echo", {"delay": 1})))
        await asyncio.sleep(0.1)

        with self.assertRaises(PoolFullError):
            await self.pool.ensure(str(uuid4()), HostedMCPServerSpec(package="fake"), wait_seconds=1)
        await busy

    async def test_unknown_packages_are_rejected(self) -> None:
        with self.assertRaises(UnknownPackageError):
            await self.pool.ensure(str(uuid4()), HostedMCPServerSpec(package="missing"), wait_seconds=0)

    async def test_oversized_messages_fail_the_server_clearly(self) -> None:
        with mock.patch.object(mcp_servers, "MAX_MESSAGE_BYTES", 64 * 1024):
            server_id = await self.start()

            with self.assertRaises(ServerNotRunningError):
                await self.pool.forward(server_id, tool_call("big", {"size": 200_000}))

        status = self.pool.status(server_id)
        assert status is not None
        self.assertEqual(status.state, "failed")
        self.assertIn("larger than", status.error or "")


class HostedMCPSpecTests(unittest.TestCase):
    def test_reserved_and_invalid_env_names_are_rejected(self) -> None:
        for name in ("PATH", "LD_PRELOAD", "PYTHONPATH", "CLI_RUNNER_SHARED_TOKEN", "node_options", "1BAD"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                HostedMCPServerSpec(package="fake", env={name: "x"})

    def test_env_and_files_cannot_set_the_same_name(self) -> None:
        with self.assertRaises(ValidationError):
            HostedMCPServerSpec(package="fake", env={"CREDS": "a"}, files={"CREDS": "b"})

    def test_shell_tokens_in_args_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            HostedMCPServerSpec(package="fake", args=["--flag", "&&"])

    def test_fingerprint_changes_with_credentials(self) -> None:
        one = HostedMCPServerSpec(package="fake", env={"TOKEN": "one"})
        two = HostedMCPServerSpec(package="fake", env={"TOKEN": "two"})

        self.assertEqual(one.fingerprint(), HostedMCPServerSpec(package="fake", env={"TOKEN": "one"}).fingerprint())
        self.assertNotEqual(one.fingerprint(), two.fingerprint())


class HostedMCPRouterTests(unittest.IsolatedAsyncioTestCase):
    """Route functions called directly: the runner has no HTTP test client dependency."""

    async def asyncSetUp(self) -> None:
        self.root = Path("/tmp") / f"infra-cli-runner-mcp-router-{uuid4()}"
        packages_root, venv_root = make_package_roots(self.root)
        self.pool = StdioMCPServerPool(
            packages_root=packages_root, venv_root=venv_root, servers_root=self.root / "servers"
        )
        self.runner = CliRunnerService()
        self.env = mock.patch.dict(os.environ, {"CLI_RUNNER_SHARED_TOKEN": "test-token"})
        self.env.start()

    async def asyncTearDown(self) -> None:
        self.env.stop()
        await self.pool.close()
        shutil.rmtree(self.root, ignore_errors=True)

    async def assert_status(self, awaitable: Any, status_code: int) -> None:
        with self.assertRaises(HTTPException) as raised:
            await awaitable
        self.assertEqual(raised.exception.status_code, status_code)

    async def test_routes_require_the_runner_token(self) -> None:
        await self.assert_status(router.list_mcp_packages(self.runner, self.pool, "Bearer wrong"), 401)
        await self.assert_status(router.list_mcp_packages(self.runner, self.pool, None), 401)

    async def test_packages_are_listed(self) -> None:
        packages = await router.list_mcp_packages(self.runner, self.pool, TOKEN)

        self.assertEqual([package.key for package in packages], ["fake"])

    async def test_facade_rejects_batches_and_servers_that_are_not_running(self) -> None:
        server_id = str(uuid4())

        await self.assert_status(
            router.mcp_server_facade(server_id, self.runner, self.pool, [{"jsonrpc": "2.0"}], TOKEN), 400
        )
        await self.assert_status(
            router.mcp_server_facade(
                server_id, self.runner, self.pool, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, TOKEN
            ),
            409,
        )
        await self.assert_status(router.get_mcp_server(server_id, self.runner, self.pool, TOKEN), 404)

    async def test_unknown_package_is_a_bad_request(self) -> None:
        request = EnsureHostedMCPServerRequest(spec=HostedMCPServerSpec(package="missing"))

        await self.assert_status(router.ensure_mcp_server(str(uuid4()), request, self.runner, self.pool, TOKEN), 400)

    async def test_facade_serves_a_running_server(self) -> None:
        server_id = str(uuid4())
        request = EnsureHostedMCPServerRequest(spec=HostedMCPServerSpec(package="fake"), wait_seconds=10)
        status = await router.ensure_mcp_server(server_id, request, self.runner, self.pool, TOKEN)

        initialized = await router.mcp_server_facade(
            server_id, self.runner, self.pool, {"jsonrpc": "2.0", "method": "notifications/initialized"}, TOKEN
        )
        listed = await router.mcp_server_facade(
            server_id, self.runner, self.pool, {"jsonrpc": "2.0", "id": "a", "method": "tools/list"}, TOKEN
        )
        deleted = await router.delete_mcp_server(server_id, self.runner, self.pool, TOKEN)

        self.assertEqual(status.state, "running")
        self.assertEqual(initialized.status_code, 202)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(json.loads(listed.body)["id"], "a")
        self.assertEqual(deleted.status_code, 204)


if __name__ == "__main__":
    unittest.main()
